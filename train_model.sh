#!/bin/bash

# Model Training Script
# Trains a language model on the crawled dataset

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to list and return available dataset versions
list_dataset_versions() {
    local versions=()
    local count=1
    
    # Check current dataset
    if [ -d "dataset/shards/train" ] && [ -n "$(ls -A dataset/shards/train/*.parquet 2>/dev/null)" ]; then
        versions+=("dataset")
        echo "  $count. Current dataset (dataset/shards/)" >&2
        count=$((count + 1))
    fi
    
    # Check backup versions
    if [ -d "dataset_backups" ]; then
        for version_dir in dataset_backups/*/; do
            if [ -d "$version_dir/shards/train" ] && [ -n "$(ls -A $version_dir/shards/train/*.parquet 2>/dev/null)" ]; then
                version_name=$(basename "$version_dir")
                versions+=("$version_dir")
                echo "  $count. $version_name ($version_dir)" >&2
                count=$((count + 1))
            fi
        done
    fi
    
    # Return array (one per line for easy parsing)
    printf '%s\n' "${versions[@]}"
}

# Select dataset version
print_info ""
print_info "============================================"
print_info "  DATASET VERSION SELECTION"
print_info "============================================"
print_info ""
print_info "Available Dataset Versions:"

# Get versions array
mapfile -t VERSIONS_ARRAY < <(list_dataset_versions)
VERSION_COUNT=${#VERSIONS_ARRAY[@]}

if [ $VERSION_COUNT -eq 0 ]; then
    print_error "No training datasets found!"
    print_info "Please run a crawl first: ./crawl_full_site.sh <url>"
    exit 1
fi

print_info ""
read -p "Select dataset version (1-$VERSION_COUNT): " VERSION_CHOICE

if [ -z "$VERSION_CHOICE" ] || [ "$VERSION_CHOICE" -lt 1 ] || [ "$VERSION_CHOICE" -gt $VERSION_COUNT ]; then
    print_error "Invalid selection!"
    exit 1
fi

SELECTED_VERSION="${VERSIONS_ARRAY[$((VERSION_CHOICE - 1))]}"
TRAIN_DIR="$SELECTED_VERSION/shards/train"
VAL_DIR="$SELECTED_VERSION/shards/val"

if [ "$SELECTED_VERSION" == "dataset" ]; then
    TRAIN_DIR="dataset/shards/train"
    VAL_DIR="dataset/shards/val"
    VERSION_NAME="current"
else
    VERSION_NAME=$(basename "$SELECTED_VERSION")
fi

print_info "Selected dataset: $VERSION_NAME"
print_info "Training directory: $TRAIN_DIR"

# Verify dataset exists
if [ ! -d "$TRAIN_DIR" ] || [ -z "$(ls -A $TRAIN_DIR/*.parquet 2>/dev/null)" ]; then
    print_error "Training dataset not found in $TRAIN_DIR"
    exit 1
fi

# Available models
declare -A MODELS
MODELS["1"]="meta-llama/Llama-2-7b-hf"
MODELS["2"]="meta-llama/Llama-2-13b-hf"
MODELS["3"]="meta-llama/Llama-3-8B"
MODELS["4"]="Qwen/Qwen2-7B"
MODELS["5"]="Qwen/Qwen2-7B-Instruct"
MODELS["6"]="Qwen/Qwen2.5-7B"
MODELS["7"]="microsoft/phi-2"
MODELS["8"]="mistralai/Mistral-7B-v0.1"
MODELS["9"]="google/gemma-7b"
MODELS["10"]="custom"

print_info ""
print_info "============================================"
print_info "  MODEL TRAINING SETUP"
print_info "============================================"
print_info ""
print_info "Available Models:"
print_info "  1.  Llama 2 7B (meta-llama/Llama-2-7b-hf)"
print_info "  2.  Llama 2 13B (meta-llama/Llama-2-13b-hf)"
print_info "  3.  Llama 3 8B (meta-llama/Llama-3-8B)"
print_info "  4.  Qwen2 7B (Qwen/Qwen2-7B)"
print_info "  5.  Qwen2 7B Instruct (Qwen/Qwen2-7B-Instruct)"
print_info "  6.  Qwen2.5 7B (Qwen/Qwen2.5-7B)"
print_info "  7.  Phi-2 (microsoft/phi-2)"
print_info "  8.  Mistral 7B (mistralai/Mistral-7B-v0.1)"
print_info "  9.  Gemma 7B (google/gemma-7b)"
print_info "  10. Custom model (enter HuggingFace model ID)"
print_info ""

# Get model selection
read -p "Select model (1-10): " MODEL_CHOICE

if [ -z "${MODELS[$MODEL_CHOICE]}" ]; then
    print_error "Invalid selection!"
    exit 1
fi

if [ "$MODEL_CHOICE" == "10" ]; then
    read -p "Enter HuggingFace model ID (e.g., microsoft/DialoGPT-medium): " CUSTOM_MODEL
    MODEL_NAME="$CUSTOM_MODEL"
else
    MODEL_NAME="${MODELS[$MODEL_CHOICE]}"
fi

print_info ""
print_info "Selected model: $MODEL_NAME"
print_info ""

# Get training parameters
read -p "Number of epochs (default: 3): " EPOCHS
EPOCHS=${EPOCHS:-3}

read -p "Batch size (default: 4): " BATCH_SIZE
BATCH_SIZE=${BATCH_SIZE:-4}

read -p "Learning rate (default: 2e-5): " LEARNING_RATE
LEARNING_RATE=${LEARNING_RATE:-2e-5}

read -p "Output model name (default: ${VERSION_NAME}_$(basename $MODEL_NAME | tr '/' '_')): " OUTPUT_NAME
if [ -z "$OUTPUT_NAME" ]; then
    OUTPUT_NAME="${VERSION_NAME}_$(basename $MODEL_NAME | tr '/' '_')"
fi

print_info ""
print_info "Training Configuration:"
print_info "  Dataset: $VERSION_NAME"
print_info "  Model: $MODEL_NAME"
print_info "  Epochs: $EPOCHS"
print_info "  Batch Size: $BATCH_SIZE"
print_info "  Learning Rate: $LEARNING_RATE"
print_info "  Output: models/$OUTPUT_NAME"
print_info ""

read -p "Start training? (y/N): " CONFIRM
if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
    print_info "Cancelled"
    exit 0
fi

# Create models directory
mkdir -p models

# Check if running in Docker or locally
if command -v docker-compose &> /dev/null && docker-compose ps processor &> /dev/null; then
    print_info "Running training in Docker container..."
    
    # Create training script in container
    docker-compose exec -T processor python3 << EOF
import sys
sys.path.insert(0, '/app')
from trainer.model_trainer import train_model

train_model(
    model_name="$MODEL_NAME",
    train_dir="$TRAIN_DIR",
    val_dir="$VAL_DIR",
    output_dir="models/$OUTPUT_NAME",
    epochs=$EPOCHS,
    batch_size=$BATCH_SIZE,
    learning_rate="$LEARNING_RATE"
)
EOF
else
    print_info "Running training locally..."
    python3 -m trainer.model_trainer \
        --model "$MODEL_NAME" \
        --train_dir "$TRAIN_DIR" \
        --val_dir "$VAL_DIR" \
        --output_dir "models/$OUTPUT_NAME" \
        --epochs $EPOCHS \
        --batch_size $BATCH_SIZE \
        --learning_rate "$LEARNING_RATE"
fi

if [ $? -eq 0 ]; then
    print_success ""
    print_success "============================================"
    print_success "  TRAINING COMPLETED!"
    print_success "============================================"
    print_success ""
    print_success "Trained model saved to: models/$OUTPUT_NAME"
    print_success ""
    print_info "To use the model:"
    print_info "  from transformers import AutoModelForCausalLM, AutoTokenizer"
    print_info "  model = AutoModelForCausalLM.from_pretrained('models/$OUTPUT_NAME')"
    print_info "  tokenizer = AutoTokenizer.from_pretrained('models/$OUTPUT_NAME')"
    print_success ""
else
    print_error "Training failed!"
    exit 1
fi

