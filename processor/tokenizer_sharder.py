#!/usr/bin/env python3
"""
Tokenization and Sharding Pipeline for LLM Training Dataset
Converts cleaned text data into tokenized shards ready for training.
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Iterator, Optional
import structlog
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from transformers import AutoTokenizer
import hashlib
from datetime import datetime

# Metrics
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger()

# Metrics
TOKENS_PROCESSED = Counter('tokenizer_tokens_total', 'Total tokens processed')
SHARDS_CREATED = Counter('tokenizer_shards_total', 'Total shards created')
TOKENIZATION_TIME = Histogram('tokenizer_batch_seconds', 'Time spent tokenizing batches')


@dataclass
class TokenizedDocument:
    """Represents a tokenized document"""
    id: str
    tokens: List[int]
    attention_mask: List[int]
    token_count: int
    language: str
    quality_score: float
    original_length: int


@dataclass
class DatasetShard:
    """Represents a dataset shard"""
    shard_id: str
    documents: List[TokenizedDocument]
    total_tokens: int
    language_distribution: Dict[str, int]
    avg_quality_score: float
    created_at: str


class TokenizerSharder:
    """Professional tokenization and sharding pipeline"""

    def __init__(self, model_name: str = "microsoft/DialoGPT-medium",
                 max_length: int = 2048, shard_size_mb: int = 512):
        self.model_name = model_name
        self.max_length = max_length
        self.shard_size_mb = shard_size_mb  # Target shard size in MB

        # Initialize tokenizer
        self.tokenizer = self.init_tokenizer()

        # Shard tracking
        self.shard_counter = 0
        self.current_shard_docs = []
        self.current_shard_size = 0

        logger.info("Tokenizer initialized",
                   model=model_name,
                   max_length=max_length,
                   shard_size_mb=shard_size_mb)

    def init_tokenizer(self):
        """Initialize the tokenizer"""
        try:
            tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                use_fast=True
            )

            # Set pad token if not present
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            logger.info("Tokenizer loaded successfully")
            return tokenizer

        except Exception as e:
            logger.error("Failed to load tokenizer", error=str(e))
            raise

    def process_dataset(self, cleaned_dir: str, shards_dir: str,
                       val_split: float = 0.05) -> Dict[str, any]:
        """Process cleaned dataset into training shards"""
        logger.info("Starting tokenization and sharding",
                   cleaned_dir=cleaned_dir,
                   shards_dir=shards_dir,
                   val_split=val_split)

        # Create shard directories
        train_dir = os.path.join(shards_dir, "train")
        val_dir = os.path.join(shards_dir, "val")
        os.makedirs(train_dir, exist_ok=True)
        os.makedirs(val_dir, exist_ok=True)

        # Find cleaned files
        cleaned_files = list(Path(cleaned_dir).glob("*.jsonl"))
        logger.info("Found cleaned files", count=len(cleaned_files))

        all_docs = []
        stats = {
            'total_docs': 0,
            'total_tokens': 0,
            'train_shards': 0,
            'val_shards': 0,
            'avg_doc_length': 0,
            'language_dist': {}
        }

        # Process all documents
        for file_path in tqdm(cleaned_files, desc="Tokenizing files"):
            docs, file_stats = self.process_file(str(file_path))
            all_docs.extend(docs)
            self.update_stats(stats, file_stats)

        # Shuffle documents
        np.random.shuffle(all_docs)

        # Split train/val
        val_size = int(len(all_docs) * val_split)
        val_docs = all_docs[:val_size]
        train_docs = all_docs[val_size:]

        # Create shards
        train_shards = self.create_shards(train_docs, train_dir, "train")
        val_shards = self.create_shards(val_docs, val_dir, "val")

        stats['train_shards'] = len(train_shards)
        stats['val_shards'] = len(val_shards)

        # Save shard manifests
        self.save_manifest(train_shards, os.path.join(shards_dir, "train_manifest.json"))
        self.save_manifest(val_shards, os.path.join(shards_dir, "val_manifest.json"))

        # Save tokenizer config
        self.save_tokenizer_config(shards_dir)

        logger.info("Tokenization and sharding completed", stats=stats)
        return stats

    def process_file(self, file_path: str) -> tuple[List[TokenizedDocument], Dict]:
        """Process a single cleaned file"""
        docs = []
        stats = {
            'docs': 0,
            'tokens': 0,
            'languages': {}
        }

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    doc_data = json.loads(line.strip())
                    tokenized_doc = self.tokenize_document(doc_data)

                    if tokenized_doc:
                        docs.append(tokenized_doc)
                        stats['docs'] += 1
                        stats['tokens'] += tokenized_doc.token_count

                        lang = tokenized_doc.language
                        stats['languages'][lang] = stats['languages'].get(lang, 0) + 1

                except json.JSONDecodeError as e:
                    logger.warning("Invalid JSON line", file=file_path, error=str(e))
                    continue

        return docs, stats

    @TOKENIZATION_TIME.time()
    def tokenize_document(self, doc_data: Dict) -> Optional[TokenizedDocument]:
        """Tokenize a single document"""
        try:
            content = doc_data.get('content', '').strip()
            if not content:
                return None

            # Tokenize
            encoding = self.tokenizer(
                content,
                truncation=True,
                padding=False,
                max_length=self.max_length,
                return_attention_mask=True,
                return_tensors=None  # Return lists, not tensors
            )

            tokens = encoding['input_ids']
            attention_mask = encoding['attention_mask']

            # Skip very short documents
            if len(tokens) < 10:
                return None

            tokenized_doc = TokenizedDocument(
                id=doc_data['id'],
                tokens=tokens,
                attention_mask=attention_mask,
                token_count=len(tokens),
                language=doc_data.get('language', 'unknown'),
                quality_score=doc_data.get('quality_score', 0.5),
                original_length=doc_data.get('content_length', 0)
            )

            TOKENS_PROCESSED.inc(len(tokens))
            return tokenized_doc

        except Exception as e:
            logger.warning("Failed to tokenize document",
                          doc_id=doc_data.get('id', 'unknown'),
                          error=str(e))
            return None

    def create_shards(self, docs: List[TokenizedDocument], output_dir: str,
                     split_name: str) -> List[DatasetShard]:
        """Create shards from tokenized documents"""
        shards = []
        current_shard_docs = []
        current_size_bytes = 0

        # Estimate bytes per document (rough approximation)
        avg_doc_size = 2048  # tokens * ~2 bytes + metadata

        for doc in tqdm(docs, desc=f"Creating {split_name} shards"):
            current_shard_docs.append(doc)
            current_size_bytes += avg_doc_size

            # Check if shard is full
            if current_size_bytes >= self.shard_size_mb * 1024 * 1024:
                shard = self.create_shard(current_shard_docs, split_name)
                self.save_shard(shard, output_dir)
                shards.append(shard)

                current_shard_docs = []
                current_size_bytes = 0
                SHARDS_CREATED.inc()

        # Save remaining documents
        if current_shard_docs:
            shard = self.create_shard(current_shard_docs, split_name)
            self.save_shard(shard, output_dir)
            shards.append(shard)
            SHARDS_CREATED.inc()

        return shards

    def create_shard(self, docs: List[TokenizedDocument], split_name: str) -> DatasetShard:
        """Create a dataset shard from documents"""
        shard_id = "04d"

        total_tokens = sum(doc.token_count for doc in docs)

        # Language distribution
        lang_dist = {}
        for doc in docs:
            lang_dist[doc.language] = lang_dist.get(doc.language, 0) + 1

        # Average quality score
        avg_quality = sum(doc.quality_score for doc in docs) / len(docs) if docs else 0

        shard = DatasetShard(
            shard_id=shard_id,
            documents=docs,
            total_tokens=total_tokens,
            language_distribution=lang_dist,
            avg_quality_score=avg_quality,
            created_at=datetime.utcnow().isoformat()
        )

        return shard

    def save_shard(self, shard: DatasetShard, output_dir: str):
        """Save shard to disk in Arrow/Parquet format"""
        # Create Arrow schema
        schema = pa.schema([
            ('doc_id', pa.string()),
            ('tokens', pa.list_(pa.int32())),
            ('attention_mask', pa.list_(pa.int32())),
            ('language', pa.string()),
            ('quality_score', pa.float32()),
            ('token_count', pa.int32()),
        ])

        # Prepare data
        doc_ids = []
        tokens_list = []
        attention_masks = []
        languages = []
        quality_scores = []
        token_counts = []

        for doc in shard.documents:
            doc_ids.append(doc.id)
            tokens_list.append(doc.tokens)
            attention_masks.append(doc.attention_mask)
            languages.append(doc.language)
            quality_scores.append(doc.quality_score)
            token_counts.append(doc.token_count)

        # Create Arrow table
        table = pa.table({
            'doc_id': doc_ids,
            'tokens': tokens_list,
            'attention_mask': attention_masks,
            'language': languages,
            'quality_score': quality_scores,
            'token_count': token_counts,
        }, schema=schema)

        # Save as Parquet
        shard_file = os.path.join(output_dir, f"{shard.shard_id}.parquet")
        pq.write_table(table, shard_file, compression='snappy')

        # Save shard metadata
        metadata_file = os.path.join(output_dir, f"{shard.shard_id}_meta.json")
        metadata = {
            'shard_id': shard.shard_id,
            'total_documents': len(shard.documents),
            'total_tokens': shard.total_tokens,
            'language_distribution': shard.language_distribution,
            'avg_quality_score': shard.avg_quality_score,
            'created_at': shard.created_at,
            'file_size_mb': os.path.getsize(shard_file) / (1024 * 1024)
        }

        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info("Saved shard",
                   shard_id=shard.shard_id,
                   documents=len(shard.documents),
                   tokens=shard.total_tokens,
                   file=shard_file)

    def save_manifest(self, shards: List[DatasetShard], manifest_file: str):
        """Save shard manifest"""
        manifest = {
            'version': '1.0',
            'created_at': datetime.utcnow().isoformat(),
            'total_shards': len(shards),
            'total_documents': sum(len(s.documents) for s in shards),
            'total_tokens': sum(s.total_tokens for s in shards),
            'shards': []
        }

        for shard in shards:
            shard_info = {
                'shard_id': shard.shard_id,
                'documents': len(shard.documents),
                'tokens': shard.total_tokens,
                'languages': shard.language_distribution,
                'avg_quality': shard.avg_quality_score,
                'created_at': shard.created_at
            }
            manifest['shards'].append(shard_info)

        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)

        logger.info("Saved manifest", file=manifest_file, shards=len(shards))

    def save_tokenizer_config(self, shards_dir: str):
        """Save tokenizer configuration"""
        config = {
            'model_name': self.model_name,
            'vocab_size': self.tokenizer.vocab_size,
            'max_length': self.max_length,
            'pad_token': self.tokenizer.pad_token,
            'eos_token': self.tokenizer.eos_token,
            'bos_token': self.tokenizer.bos_token,
            'unk_token': self.tokenizer.unk_token,
        }

        config_file = os.path.join(shards_dir, "tokenizer_config.json")
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        # Save tokenizer files
        tokenizer_dir = os.path.join(shards_dir, "tokenizer")
        os.makedirs(tokenizer_dir, exist_ok=True)
        self.tokenizer.save_pretrained(tokenizer_dir)

        logger.info("Saved tokenizer config", config_file=config_file)

    def update_stats(self, global_stats: Dict, file_stats: Dict):
        """Update global statistics"""
        global_stats['total_docs'] += file_stats['docs']
        global_stats['total_tokens'] += file_stats['tokens']

        for lang, count in file_stats['languages'].items():
            global_stats['language_dist'][lang] = global_stats['language_dist'].get(lang, 0) + count

    def load_shard_for_training(self, shard_path: str) -> Iterator[Dict]:
        """Load a shard for training (iterator)"""
        table = pq.read_table(shard_path)

        for batch in table.to_batches():
            for row in batch.to_pylist():
                yield {
                    'input_ids': row['tokens'],
                    'attention_mask': row['attention_mask'],
                    'labels': row['tokens'],  # For causal LM training
                }


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Tokenize and shard dataset for LLM training')
    parser.add_argument('--cleaned-dir', default='dataset/cleaned', help='Cleaned data directory')
    parser.add_argument('--shards-dir', default='dataset/shards', help='Output shards directory')
    parser.add_argument('--model-name', default='microsoft/DialoGPT-medium', help='Tokenizer model name')
    parser.add_argument('--max-length', type=int, default=2048, help='Maximum sequence length')
    parser.add_argument('--shard-size-mb', type=int, default=512, help='Target shard size in MB')
    parser.add_argument('--val-split', type=float, default=0.05, help='Validation split ratio')

    args = parser.parse_args()

    sharder = TokenizerSharder(
        model_name=args.model_name,
        max_length=args.max_length,
        shard_size_mb=args.shard_size_mb
    )

    stats = sharder.process_dataset(
        args.cleaned_dir,
        args.shards_dir,
        args.val_split
    )

    print("Tokenization and sharding completed!")
    print(f"Total docs: {stats['total_docs']}")
    print(f"Total tokens: {stats['total_tokens']}")
    print(f"Train shards: {stats['train_shards']}")
    print(f"Val shards: {stats['val_shards']}")


if __name__ == '__main__':
    main()
