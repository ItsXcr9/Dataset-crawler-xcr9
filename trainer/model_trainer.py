#!/usr/bin/env python3
"""
Model Training Script
Trains language models on the crawled dataset using Hugging Face Transformers
"""

import os
import json
import argparse
from pathlib import Path
from typing import Optional, Dict, Any
import structlog
from datetime import datetime

import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
    EarlyStoppingCallback
)
from datasets import load_dataset
import pyarrow.parquet as pq
import numpy as np
from tqdm import tqdm

logger = structlog.get_logger()


class ParquetDataset(Dataset):
    """Dataset loader for Parquet shards"""
    
    def __init__(self, shard_dir: str, tokenizer, max_length: int = 2048):
        self.shard_dir = Path(shard_dir)
        self.tokenizer = tokenizer
        self.max_length = max_length
        
        # Find all parquet files
        self.shard_files = sorted(list(self.shard_dir.glob("*.parquet")))
        
        if not self.shard_files:
            raise ValueError(f"No parquet files found in {shard_dir}")
        
        logger.info("Found shard files", count=len(self.shard_files), dir=str(shard_dir))
        
        # Load all data into memory (for small datasets) or use lazy loading
        self.data = []
        self._load_shards()
    
    def _load_shards(self):
        """Load all shards into memory"""
        logger.info("Loading shards into memory...")
        for shard_file in tqdm(self.shard_files, desc="Loading shards"):
            try:
                table = pq.read_table(shard_file)
                for batch in table.to_batches():
                    for row in batch.to_pylist():
                        # Convert tokens to proper format
                        tokens = row['tokens']
                        attention_mask = row['attention_mask']
                        
                        # Ensure proper length
                        if len(tokens) > self.max_length:
                            tokens = tokens[:self.max_length]
                            attention_mask = attention_mask[:self.max_length]
                        elif len(tokens) < self.max_length:
                            # Pad if needed (though shards should already be padded)
                            pad_length = self.max_length - len(tokens)
                            pad_token_id = self.tokenizer.pad_token_id or self.tokenizer.eos_token_id
                            tokens = tokens + [pad_token_id] * pad_length
                            attention_mask = attention_mask + [0] * pad_length
                        
                        self.data.append({
                            'input_ids': torch.tensor(tokens, dtype=torch.long),
                            'attention_mask': torch.tensor(attention_mask, dtype=torch.long),
                            'labels': torch.tensor(tokens, dtype=torch.long)  # For causal LM
                        })
            except Exception as e:
                logger.warning("Failed to load shard", shard=str(shard_file), error=str(e))
                continue
        
        logger.info("Loaded documents", count=len(self.data))
    
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, idx):
        return self.data[idx]


def train_model(
    model_name: str,
    train_dir: str,
    val_dir: str,
    output_dir: str,
    epochs: int = 3,
    batch_size: int = 4,
    learning_rate: float = 2e-5,
    max_length: int = 2048,
    gradient_accumulation_steps: int = 4,
    warmup_steps: int = 100,
    save_steps: int = 500,
    eval_steps: int = 500,
    logging_steps: int = 100,
    fp16: bool = True,
    dataloader_num_workers: int = 4
):
    """Train a language model on the dataset"""
    
    logger.info("Starting model training",
                model=model_name,
                train_dir=train_dir,
                output_dir=output_dir)
    
    # Check for GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Using device", device=device)
    
    if device == "cpu":
        logger.warning("No GPU detected. Training will be slow on CPU.")
        fp16 = False  # FP16 requires GPU
    
    # Load tokenizer
    logger.info("Loading tokenizer", model=model_name)
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        
        # Set padding token if not set
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            tokenizer.pad_token_id = tokenizer.eos_token_id
        
    except Exception as e:
        logger.error("Failed to load tokenizer", error=str(e))
        raise
    
    # Load model
    logger.info("Loading model", model=model_name)
    try:
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            trust_remote_code=True,
            torch_dtype=torch.float16 if fp16 and device == "cuda" else torch.float32,
            device_map="auto" if device == "cuda" else None,
            low_cpu_mem_usage=True
        )
        
        # Resize token embeddings if needed
        model.resize_token_embeddings(len(tokenizer))
        
    except Exception as e:
        logger.error("Failed to load model", error=str(e))
        raise
    
    # Load datasets
    logger.info("Loading training dataset", dir=train_dir)
    train_dataset = ParquetDataset(train_dir, tokenizer, max_length=max_length)
    
    val_dataset = None
    if os.path.exists(val_dir) and os.listdir(val_dir):
        logger.info("Loading validation dataset", dir=val_dir)
        try:
            val_dataset = ParquetDataset(val_dir, tokenizer, max_length=max_length)
        except Exception as e:
            logger.warning("Failed to load validation dataset", error=str(e))
            val_dataset = None
    
    # Data collator
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,  # Causal LM, not masked LM
    )
    
    # Training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        learning_rate=learning_rate,
        weight_decay=0.01,
        warmup_steps=warmup_steps,
        logging_steps=logging_steps,
        save_steps=save_steps,
        eval_steps=eval_steps if val_dataset else None,
        eval_strategy="steps" if val_dataset else "no",
        save_total_limit=3,
        load_best_model_at_end=True if val_dataset else False,
        metric_for_best_model="loss",
        greater_is_better=False,
        fp16=fp16 and device == "cuda",
        bf16=False,
        dataloader_num_workers=0,  # Set to 0 to avoid multiprocessing issues
        report_to="none",  # Disable wandb/tensorboard by default
        remove_unused_columns=False,
        ddp_find_unused_parameters=False,
    )
    
    # Initialize trainer
    callbacks = []
    if val_dataset:
        callbacks.append(EarlyStoppingCallback(early_stopping_patience=3))
    
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
        callbacks=callbacks,
    )
    
    # Train
    logger.info("Starting training...")
    try:
        train_result = trainer.train()
        
        # Save final model
        logger.info("Saving final model", output_dir=output_dir)
        trainer.save_model()
        tokenizer.save_pretrained(output_dir)
        
        # Save training info
        training_info = {
            'model_name': model_name,
            'base_model': model_name,
            'trained_at': datetime.utcnow().isoformat(),
            'epochs': epochs,
            'batch_size': batch_size,
            'learning_rate': learning_rate,
            'max_length': max_length,
            'train_samples': len(train_dataset),
            'val_samples': len(val_dataset) if val_dataset else 0,
            'final_loss': train_result.training_loss,
            'device': device,
        }
        
        info_file = os.path.join(output_dir, "training_info.json")
        with open(info_file, 'w') as f:
            json.dump(training_info, f, indent=2)
        
        logger.info("Training completed successfully",
                   output_dir=output_dir,
                   final_loss=train_result.training_loss)
        
        print(f"\n✅ Training completed!")
        print(f"📁 Model saved to: {output_dir}")
        print(f"📊 Final training loss: {train_result.training_loss:.4f}")
        
    except Exception as e:
        logger.error("Training failed", error=str(e))
        raise


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="Train a language model on crawled dataset")
    parser.add_argument("--model", required=True, help="HuggingFace model name")
    parser.add_argument("--train_dir", required=True, help="Training shards directory")
    parser.add_argument("--val_dir", help="Validation shards directory")
    parser.add_argument("--output_dir", required=True, help="Output directory for trained model")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=4, help="Batch size")
    parser.add_argument("--learning_rate", type=float, default=2e-5, help="Learning rate")
    parser.add_argument("--max_length", type=int, default=2048, help="Max sequence length")
    parser.add_argument("--gradient_accumulation_steps", type=int, default=4, help="Gradient accumulation steps")
    parser.add_argument("--warmup_steps", type=int, default=100, help="Warmup steps")
    parser.add_argument("--save_steps", type=int, default=500, help="Save checkpoint every N steps")
    parser.add_argument("--eval_steps", type=int, default=500, help="Evaluate every N steps")
    parser.add_argument("--logging_steps", type=int, default=100, help="Log every N steps")
    parser.add_argument("--fp16", action="store_true", help="Use FP16 precision")
    parser.add_argument("--dataloader_num_workers", type=int, default=4, help="DataLoader workers")
    
    args = parser.parse_args()
    
    train_model(
        model_name=args.model,
        train_dir=args.train_dir,
        val_dir=args.val_dir or "",
        output_dir=args.output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        max_length=args.max_length,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        warmup_steps=args.warmup_steps,
        save_steps=args.save_steps,
        eval_steps=args.eval_steps,
        logging_steps=args.logging_steps,
        fp16=args.fp16,
        dataloader_num_workers=args.dataloader_num_workers
    )


if __name__ == "__main__":
    main()

