#!/bin/bash

# Full Site Crawler Script
# This script crawls an entire website domain and creates LLM training dataset
# It automatically stays within the same domain and creates versioned datasets

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

# Check if URL is provided
if [ -z "$1" ]; then
    print_error "Usage: ./crawl_full_site.sh <start_url> [max_depth] [version_name]"
    echo ""
    echo "Examples:"
    echo "  ./crawl_full_site.sh https://kubernetes.io/docs/"
    echo "  ./crawl_full_site.sh https://kubernetes.io/docs/ 6"
    echo "  ./crawl_full_site.sh https://kubernetes.io/docs/ 6 kubernetes_v1"
    echo ""
    echo "Parameters:"
    echo "  start_url     - The URL to start crawling from (required)"
    echo "  max_depth     - Maximum crawl depth (default: 6)"
    echo "  version_name  - Name for this dataset version (default: auto-generated)"
    echo ""
    echo "Domain Restriction:"
    echo "  The crawler automatically stays within the same domain as the start_url"
    echo "  Example: Starting from kubernetes.io will only crawl kubernetes.io pages"
    exit 1
fi

START_URL="$1"
MAX_DEPTH="${2:-6}"
VERSION_NAME="${3:-$(date +%Y%m%d_%H%M%S)}"

# Extract domain from URL
DOMAIN=$(echo "$START_URL" | awk -F[/:] '{print $4}')

print_info "============================================"
print_info "  Full Site Crawler for LLM Datasets"
print_info "============================================"
print_info "Start URL:     $START_URL"
print_info "Domain:        $DOMAIN (restricted to this domain only)"
print_info "Max Depth:     $MAX_DEPTH"
print_info "Version:       $VERSION_NAME"
print_info "============================================"
echo ""

# Confirm before starting
read -p "$(echo -e ${YELLOW}Do you want to continue? [y/N]:${NC} )" -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_info "Cancelled by user"
    exit 0
fi

# Create backup directory
BACKUP_DIR="dataset_backups/${VERSION_NAME}"
print_info "Creating backup directory: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# Backup existing datasets if they exist
if [ -d "dataset/raw" ] && [ "$(ls -A dataset/raw 2>/dev/null)" ]; then
    print_info "Backing up existing raw data..."
    mv dataset/raw "$BACKUP_DIR/raw"
fi

if [ -d "dataset/cleaned" ] && [ "$(ls -A dataset/cleaned 2>/dev/null)" ]; then
    print_info "Backing up existing cleaned data..."
    mv dataset/cleaned "$BACKUP_DIR/cleaned"
fi

if [ -d "dataset/shards" ] && [ "$(ls -A dataset/shards 2>/dev/null)" ]; then
    print_info "Backing up existing shards..."
    mv dataset/shards "$BACKUP_DIR/shards"
fi

# Create fresh directories
print_info "Creating fresh dataset directories..."
mkdir -p dataset/{raw,cleaned,shards/train,shards/val,metadata}

# Start crawling
print_info ""
print_info "============================================"
print_info "  STEP 1/3: CRAWLING"
print_info "============================================"
print_info "This may take 10-60 minutes depending on site size..."
print_info "Crawler will automatically:"
print_info "  - Stay within $DOMAIN domain"
print_info "  - Respect robots.txt"
print_info "  - Rate limit requests"
print_info "  - Extract only text content"
echo ""

docker-compose exec -T crawler python -m crawler.crawler "$START_URL" "$MAX_DEPTH" dataset/raw

if [ $? -ne 0 ]; then
    print_error "Crawling failed!"
    exit 1
fi

# Count crawled documents
RAW_COUNT=$(find dataset/raw -name "*.jsonl" -exec wc -l {} + 2>/dev/null | tail -1 | awk '{print $1}' || echo "0")
print_success "Crawling completed! Raw documents: $RAW_COUNT"

# Process data
print_info ""
print_info "============================================"
print_info "  STEP 2/3: PROCESSING & CLEANING"
print_info "============================================"
print_info "Applying filters:"
print_info "  - Minimum length: 500 characters"
print_info "  - Language: English only"
print_info "  - Quality score: > 0.6"
print_info "  - Deduplication: Exact + Fuzzy"
echo ""

docker-compose exec -T processor python -m processor.data_processor

if [ $? -ne 0 ]; then
    print_error "Processing failed!"
    exit 1
fi

# Count processed documents
CLEANED_COUNT=$(find dataset/cleaned -name "*.jsonl" -exec wc -l {} + 2>/dev/null | tail -1 | awk '{print $1}' || echo "0")
print_success "Processing completed! Cleaned documents: $CLEANED_COUNT"

# Tokenize and shard
print_info ""
print_info "============================================"
print_info "  STEP 3/3: TOKENIZATION & SHARDING"
print_info "============================================"
print_info "Creating training-ready shards..."
print_info "  - Tokenizer: microsoft/DialoGPT-medium"
print_info "  - Max length: 2048 tokens"
print_info "  - Shard size: 512 MB"
print_info "  - Train/Val split: 95/5"
echo ""

docker-compose exec -T processor python -m processor.tokenizer_sharder

if [ $? -ne 0 ]; then
    print_error "Tokenization failed!"
    exit 1
fi

# Show final statistics
print_success ""
print_success "============================================"
print_success "  DATASET CREATION COMPLETED!"
print_success "============================================"

if [ -f dataset/shards/train_manifest.json ]; then
    TRAIN_SHARDS=$(jq '.shards | length' dataset/shards/train_manifest.json 2>/dev/null || echo "0")
    TRAIN_TOKENS=$(jq '.total_tokens' dataset/shards/train_manifest.json 2>/dev/null || echo "0")
    TRAIN_DOCS=$(jq '.total_documents' dataset/shards/train_manifest.json 2>/dev/null || echo "0")
fi

if [ -f dataset/shards/val_manifest.json ]; then
    VAL_SHARDS=$(jq '.shards | length' dataset/shards/val_manifest.json 2>/dev/null || echo "0")
    VAL_TOKENS=$(jq '.total_tokens' dataset/shards/val_manifest.json 2>/dev/null || echo "0")
    VAL_DOCS=$(jq '.total_documents' dataset/shards/val_manifest.json 2>/dev/null || echo "0")
fi

echo ""
print_info "Dataset Version: $VERSION_NAME"
print_info "Source Domain:   $DOMAIN"
print_info ""
print_info "Raw Data:"
print_info "  Documents:     $RAW_COUNT"
print_info "  Location:      $BACKUP_DIR/raw"
print_info ""
print_info "Cleaned Data:"
print_info "  Documents:     $CLEANED_COUNT"
print_info "  Filter rate:   $(awk "BEGIN {printf \"%.1f\", (($RAW_COUNT-$CLEANED_COUNT)/$RAW_COUNT)*100}")%"
print_info "  Location:      dataset/cleaned/"
print_info ""
print_info "Training Shards:"
print_info "  Documents:     ${TRAIN_DOCS:-0}"
print_info "  Tokens:        ${TRAIN_TOKENS:-0}"
print_info "  Shards:        ${TRAIN_SHARDS:-0}"
print_info "  Location:      dataset/shards/train/"
print_info ""
print_info "Validation Shards:"
print_info "  Documents:     ${VAL_DOCS:-0}"
print_info "  Tokens:        ${VAL_TOKENS:-0}"
print_info "  Shards:        ${VAL_SHARDS:-0}"
print_info "  Location:      dataset/shards/val/"
print_info ""
print_success "============================================"
print_success "Dataset is ready for LLM training!"
print_success "Location: dataset/shards/"
print_success "============================================"

# Save version info
cat > "dataset/VERSION.txt" <<EOF
Dataset Version: $VERSION_NAME
Created: $(date)
Source URL: $START_URL
Domain: $DOMAIN
Max Depth: $MAX_DEPTH
Raw Documents: $RAW_COUNT
Cleaned Documents: $CLEANED_COUNT
Training Documents: ${TRAIN_DOCS:-0}
Training Tokens: ${TRAIN_TOKENS:-0}
Validation Documents: ${VAL_DOCS:-0}
Validation Tokens: ${VAL_TOKENS:-0}
EOF

print_info ""
print_info "Version info saved to: dataset/VERSION.txt"
print_info "Backup saved to: $BACKUP_DIR"

echo ""

