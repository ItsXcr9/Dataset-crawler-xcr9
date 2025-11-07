#!/usr/bin/env python3
"""
Data Processing Pipeline for LLM Training Dataset
Handles cleaning, deduplication, language detection, and quality filtering.
"""

import json
import os
import hashlib
from typing import List, Dict, Set, Tuple
from pathlib import Path
import structlog
from dataclasses import dataclass, asdict
from datetime import datetime
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

# NLP imports
from langdetect import detect, detect_langs
from datasketch import MinHash, MinHashLSH
import textstat
from transformers import pipeline
import pandas as pd

# Metrics
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger()

# Metrics
DOCS_PROCESSED = Counter('processor_docs_total', 'Total documents processed')
DOCS_FILTERED = Counter('processor_docs_filtered', 'Documents filtered out')
QUALITY_SCORES = Histogram('processor_quality_scores', 'Quality scores distribution')
PROCESSING_TIME = Histogram('processor_batch_seconds', 'Time spent processing batches')


@dataclass
class ProcessedDocument:
    """Represents a processed document ready for training"""
    id: str
    original_url: str
    domain: str
    title: str
    content: str
    language: str
    language_confidence: float
    quality_score: float
    content_length: int
    token_estimate: int
    content_hash: str
    duplicate_hash: str
    timestamp: str
    source: str = "web_crawl"
    license: str = "unknown"
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class DataProcessor:
    """Professional data processing pipeline"""

    def __init__(self, config_path: str = "config/processor_config.yaml"):
        self.config = self.load_config(config_path)

        # Initialize models
        self.lang_detector = self.init_language_detector()
        self.quality_model = self.init_quality_model()

        # Deduplication structures
        self.exact_duplicates: Set[str] = set()
        self.fuzzy_deduper = MinHashLSH(
            threshold=self.config['deduplication']['fuzzy_threshold'],
            num_perm=self.config['deduplication']['num_perm']
        )

        # Quality thresholds
        self.min_content_length = self.config['quality']['min_content_length']
        self.max_content_length = self.config['quality']['max_content_length']
        self.min_quality_score = self.config['quality']['min_quality_score']

        logger.info("Data processor initialized")

    def load_config(self, config_path: str) -> Dict:
        """Load processor configuration"""
        default_config = {
            'deduplication': {
                'fuzzy_threshold': 0.8,
                'num_perm': 128
            },
            'quality': {
                'min_content_length': 500,
                'max_content_length': 100000,
                'min_quality_score': 0.6
            },
            'language': {
                'supported_languages': ['en', 'zh', 'es', 'fr', 'de', 'ja', 'ko', 'ru'],
                'min_confidence': 0.7
            },
            'processing': {
                'batch_size': 1000,
                'max_workers': 4
            }
        }

        if os.path.exists(config_path):
            import yaml
            with open(config_path, 'r') as f:
                user_config = yaml.safe_load(f)
            default_config.update(user_config)

        return default_config

    def init_language_detector(self):
        """Initialize language detection models"""
        # Use langdetect for reliable language detection (pure Python, no compilation)
        logger.info("Using langdetect for language detection")
        return True

    def init_quality_model(self):
        """Initialize quality assessment model"""
        try:
            # Use a small BERT model for quality scoring
            return pipeline(
                "text-classification",
                model="microsoft/DialoGPT-small",
                device=-1  # CPU
            )
        except:
            logger.warning("Could not load quality model, using heuristics")
            return None

    def process_dataset(self, raw_dir: str, output_dir: str) -> Dict[str, int]:
        """Process entire dataset from raw to cleaned"""
        logger.info("Starting dataset processing", raw_dir=raw_dir, output_dir=output_dir)

        # Create output directories
        cleaned_dir = os.path.join(output_dir, "cleaned")
        metadata_dir = os.path.join(output_dir, "metadata")
        os.makedirs(cleaned_dir, exist_ok=True)
        os.makedirs(metadata_dir, exist_ok=True)

        # Find all raw data files
        raw_files = list(Path(raw_dir).glob("*.jsonl"))
        logger.info("Found raw files", count=len(raw_files))

        all_processed_docs = []
        stats = {
            'total_docs': 0,
            'processed_docs': 0,
            'filtered_docs': 0,
            'duplicate_docs': 0,
            'language_filtered': 0,
            'quality_filtered': 0
        }

        # Process files in parallel
        with ProcessPoolExecutor(max_workers=self.config['processing']['max_workers']) as executor:
            futures = []
            for raw_file in raw_files:
                future = executor.submit(self.process_file, str(raw_file))
                futures.append((raw_file, future))

            for raw_file, future in tqdm(futures, desc="Processing files"):
                try:
                    processed_docs, file_stats = future.result()
                    all_processed_docs.extend(processed_docs)
                    self.update_stats(stats, file_stats)
                except Exception as e:
                    logger.error("Failed to process file", file=str(raw_file), error=str(e))

        # Save processed data
        self.save_processed_data(all_processed_docs, cleaned_dir, metadata_dir)

        logger.info("Dataset processing completed", stats=stats)
        return stats

    def process_file(self, file_path: str) -> Tuple[List[ProcessedDocument], Dict[str, int]]:
        """Process a single raw data file"""
        processed_docs = []
        stats = {
            'total_docs': 0,
            'processed_docs': 0,
            'filtered_docs': 0,
            'duplicate_docs': 0,
            'language_filtered': 0,
            'quality_filtered': 0
        }

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    raw_doc = json.loads(line.strip())
                    stats['total_docs'] += 1

                    processed_doc = self.process_document(raw_doc)
                    if processed_doc:
                        processed_docs.append(processed_doc)
                        stats['processed_docs'] += 1
                    else:
                        stats['filtered_docs'] += 1

                except json.JSONDecodeError as e:
                    logger.warning("Invalid JSON line", file=file_path, error=str(e))
                    continue

        return processed_docs, stats

    @PROCESSING_TIME.time()
    def process_document(self, raw_doc: Dict) -> ProcessedDocument:
        """Process a single document through the pipeline"""
        DOCS_PROCESSED.inc()

        # Extract content
        content = raw_doc.get('content', '').strip()
        if not content:
            return None

        # Basic filtering
        if len(content) < self.min_content_length:
            DOCS_FILTERED.labels(reason='too_short').inc()
            return None

        if len(content) > self.max_content_length:
            DOCS_FILTERED.labels(reason='too_long').inc()
            return None

        # Language detection
        language, confidence = self.detect_language(content)
        if language not in self.config['language']['supported_languages']:
            DOCS_FILTERED.labels(reason='unsupported_language').inc()
            return None

        if confidence < self.config['language']['min_confidence']:
            DOCS_FILTERED.labels(reason='low_language_confidence').inc()
            return None

        # Quality assessment
        quality_score = self.assess_quality(content)
        QUALITY_SCORES.observe(quality_score)

        if quality_score < self.min_quality_score:
            DOCS_FILTERED.labels(reason='low_quality').inc()
            return None

        # Check for duplicates
        if self.is_duplicate(content):
            DOCS_FILTERED.labels(reason='duplicate').inc()
            return None

        # Create processed document
        doc = ProcessedDocument(
            id=raw_doc['id'],
            original_url=raw_doc['url'],
            domain=raw_doc['domain'],
            title=raw_doc.get('title', 'No Title'),
            content=self.clean_content(content),
            language=language,
            language_confidence=confidence,
            quality_score=quality_score,
            content_length=len(content),
            token_estimate=self.estimate_tokens(content),
            content_hash=raw_doc['content_hash'],
            duplicate_hash=self.generate_fuzzy_hash(content),
            timestamp=raw_doc['timestamp']
        )

        return doc

    def detect_language(self, text: str) -> Tuple[str, float]:
        """Detect language of text"""
        try:
            # Use langdetect for reliable language detection
            if self.lang_detector:
                # detect_langs returns list of languages with probabilities
                results = detect_langs(text[:1000])
                if results and len(results) > 0:
                    # Get the most probable language
                    return results[0].lang, results[0].prob
            return 'unknown', 0.0
        except Exception as e:
            logger.warning("Language detection failed", error=str(e))
            return 'unknown', 0.0

    def assess_quality(self, text: str) -> float:
        """Assess text quality using multiple heuristics"""
        try:
            if self.quality_model:
                # Use ML model for quality
                result = self.quality_model(text[:512], truncation=True)
                return result[0]['score']
            else:
                # Use heuristic scoring
                scores = []

                # Readability score (inverse, lower is better)
                readability = textstat.flesch_reading_ease(text)
                readability_score = max(0, min(1, readability / 100))
                scores.append(readability_score)

                # Text entropy (information density)
                entropy = self.calculate_entropy(text)
                entropy_score = max(0, min(1, entropy / 5))  # Normalize
                scores.append(entropy_score)

                # Length diversity (sentence variation)
                sentences = re.split(r'[.!?]+', text)
                avg_sentence_len = sum(len(s.split()) for s in sentences) / len(sentences)
                length_diversity = 1 - abs(avg_sentence_len - 20) / 50  # Prefer ~20 words/sentence
                scores.append(max(0, length_diversity))

                return sum(scores) / len(scores)

        except Exception as e:
            logger.warning("Quality assessment failed", error=str(e))
            return 0.5

    def calculate_entropy(self, text: str) -> float:
        """Calculate text entropy (information density)"""
        from collections import Counter
        import math

        if not text:
            return 0.0

        # Count character frequencies
        char_counts = Counter(text.lower())
        total_chars = len(text)

        entropy = 0
        for count in char_counts.values():
            p = count / total_chars
            entropy -= p * math.log2(p)

        return entropy

    def is_duplicate(self, content: str) -> bool:
        """Check if content is duplicate"""
        # Exact duplicate check
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        if content_hash in self.exact_duplicates:
            return True
        self.exact_duplicates.add(content_hash)

        # Fuzzy duplicate check
        fuzzy_hash = self.generate_fuzzy_hash(content)
        if fuzzy_hash in self.fuzzy_deduper:
            return True

        # Add to fuzzy deduper
        minhash = MinHash(num_perm=self.config['deduplication']['num_perm'])
        words = re.findall(r'\b\w+\b', content.lower())
        for word in words[:1000]:  # Limit to prevent memory issues
            minhash.update(word.encode('utf-8'))
        self.fuzzy_deduper.insert(fuzzy_hash, minhash)

        return False

    def generate_fuzzy_hash(self, content: str) -> str:
        """Generate fuzzy hash for near-duplicate detection"""
        minhash = MinHash(num_perm=self.config['deduplication']['num_perm'])
        words = re.findall(r'\b\w+\b', content.lower())
        for word in words[:1000]:
            minhash.update(word.encode('utf-8'))
        return str(minhash.hashvalues.tobytes())

    def clean_content(self, content: str) -> str:
        """Clean and normalize content"""
        # Remove excessive whitespace
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'\n+', '\n', content)

        # Remove URLs
        content = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', content)

        # Remove email addresses
        content = re.sub(r'\S+@\S+', '', content)

        # Remove excessive punctuation
        content = re.sub(r'[.!?]{2,}', '.', content)

        return content.strip()

    def estimate_tokens(self, content: str) -> int:
        """Estimate token count (rough approximation)"""
        # Rough estimate: 1 token per word + punctuation
        words = len(re.findall(r'\b\w+\b', content))
        punctuation = len(re.findall(r'[.!?]', content))
        return words + punctuation

    def save_processed_data(self, docs: List[ProcessedDocument], cleaned_dir: str, metadata_dir: str):
        """Save processed documents and metadata"""
        # Save cleaned documents
        cleaned_file = os.path.join(cleaned_dir, f"cleaned_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl")
        with open(cleaned_file, 'w', encoding='utf-8') as f:
            for doc in docs:
                f.write(json.dumps(asdict(doc), ensure_ascii=False) + '\n')

        # Save metadata manifest
        manifest_file = os.path.join(metadata_dir, "manifest.jsonl")
        with open(manifest_file, 'w', encoding='utf-8') as f:
            for doc in docs:
                metadata = {
                    'id': doc.id,
                    'source': doc.source,
                    'language': doc.language,
                    'quality_score': doc.quality_score,
                    'tokens': doc.token_estimate,
                    'license': doc.license,
                    'timestamp': doc.timestamp
                }
                f.write(json.dumps(metadata, ensure_ascii=False) + '\n')

        # Save statistics
        stats_df = pd.DataFrame([asdict(doc) for doc in docs])
        stats_file = os.path.join(metadata_dir, "dataset_stats.csv")
        stats_df.to_csv(stats_file, index=False)

        logger.info("Saved processed data",
                   cleaned_file=cleaned_file,
                   manifest_file=manifest_file,
                   total_docs=len(docs))

    def update_stats(self, global_stats: Dict, file_stats: Dict):
        """Update global statistics"""
        for key in global_stats:
            global_stats[key] += file_stats[key]


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Process crawled data for LLM training')
    parser.add_argument('--raw-dir', default='dataset/raw', help='Raw data directory')
    parser.add_argument('--output-dir', default='dataset', help='Output directory')
    parser.add_argument('--config', default='config/processor_config.yaml', help='Config file')

    args = parser.parse_args()

    processor = DataProcessor(args.config)
    stats = processor.process_dataset(args.raw_dir, args.output_dir)

    print("Processing completed!")
    print(f"Total docs: {stats['total_docs']}")
    print(f"Processed docs: {stats['processed_docs']}")
    print(f"Filtered docs: {stats['filtered_docs']}")


if __name__ == '__main__':
    main()
