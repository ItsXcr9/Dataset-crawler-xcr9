#!/bin/bash
# Quick training test with small model and dataset

set -e

echo "============================================"
echo "  QUICK TRAINING TEST"
echo "============================================"
echo ""

# Use test_v1 dataset and phi-2 model (small, fast)
DATASET_VERSION="dataset_backups/test_v1"
MODEL="microsoft/phi-2"
OUTPUT_NAME="test_phi2_quick"

echo "Configuration:"
echo "  Dataset: test_v1"
echo "  Model: $MODEL (small, fast)"
echo "  Epochs: 1 (quick test)"
echo "  Batch Size: 2"
echo "  Output: models/$OUTPUT_NAME"
echo ""

# Check if dataset exists
if [ ! -d "$DATASET_VERSION/shards/train" ]; then
    echo "Error: Dataset not found: $DATASET_VERSION"
    exit 1
fi

echo "Starting training..."
docker-compose exec -T processor python3 << EOF
import sys
sys.path.insert(0, '/app')
from trainer.model_trainer import train_model

train_model(
    model_name="$MODEL",
    train_dir="$DATASET_VERSION/shards/train",
    val_dir="$DATASET_VERSION/shards/val",
    output_dir="models/$OUTPUT_NAME",
    epochs=1,
    batch_size=2,
    learning_rate=2e-5,
    max_length=512,  # Smaller for quick test
    save_steps=10,
    eval_steps=10,
    logging_steps=5
)
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Training completed!"
    echo "Testing model..."
    echo ""
    docker-compose exec -T processor python3 /app/test_model.py models/$OUTPUT_NAME --prompt "What is" --max_length 50
else
    echo "❌ Training failed!"
    exit 1
fi

