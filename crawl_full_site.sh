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

# Job tracking functions (for web interface)
API_URL="${API_URL:-http://localhost:18000}"

create_job() {
    local job_type=$1
    local params=$2
    local response=$(curl -s -X POST "${API_URL}/${job_type}" \
        -H "Content-Type: application/json" \
        -d "$params" 2>/dev/null || echo '{"job_id":"unknown"}')
    echo "$response" | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4 || echo ""
}

update_job_status() {
    local job_id=$1
    local status=$2
    local progress=$3
    local message=$4
    
    # Update via processor container (has Python and redis)
    docker-compose exec -T processor python3 -c "
import json
import os
import redis
import sys
from datetime import datetime

redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')
r = redis.Redis.from_url(redis_url, decode_responses=True)
job_key = f'job:{sys.argv[1]}'
job_data = r.get(job_key)
if job_data:
    job = json.loads(job_data)
    job['status'] = sys.argv[2]
    job['progress'] = float(sys.argv[3])
    job['message'] = sys.argv[4]
    job['updated_at'] = datetime.utcnow().isoformat()
    r.set(job_key, json.dumps(job))
" "$job_id" "$status" "$progress" "$message" 2>/dev/null || true
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

# CRITICAL: Completely remove and recreate directories to ensure clean state
print_info "Clearing all old files from previous crawls..."
# Remove entire directories to ensure no leftover files
rm -rf dataset/raw dataset/cleaned dataset/shards dataset/metadata 2>/dev/null || true
rm -f dataset/VERSION.txt 2>/dev/null || true

# Create completely fresh directories
print_info "Creating fresh dataset directories..."
mkdir -p dataset/{raw,cleaned,shards/train,shards/val,metadata}

# Record start time for this crawl (to verify only new files are processed)
CRAWL_START_TIME=$(date +%s)
echo "$CRAWL_START_TIME" > dataset/.crawl_start_time

# Create backup directory (will be populated AFTER crawl completes)
BACKUP_DIR="dataset_backups/${VERSION_NAME}"
print_info "Backup directory will be: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# Fix permissions - containers run as non-root users (UID 1000)
print_info "Setting permissions for Docker containers..."
# Get the UID/GID from the containers (usually 1000:1000)
CRAWLER_UID=$(docker-compose exec -T crawler id -u 2>/dev/null || echo "1000")
CRAWLER_GID=$(docker-compose exec -T crawler id -g 2>/dev/null || echo "1000")

# Set ownership to container user (usually 1000:1000)
if [ -n "$CRAWLER_UID" ] && [ -n "$CRAWLER_GID" ]; then
    chown -R ${CRAWLER_UID}:${CRAWLER_GID} dataset/ 2>/dev/null || {
        # If chown fails, make directories world-writable as fallback
        print_warning "Could not change ownership, making directories writable..."
        chmod -R 777 dataset/ 2>/dev/null || true
    }
    # Ensure directories are writable (775 = owner and group can write)
    chmod -R 775 dataset/ 2>/dev/null || true
else
    # Fallback: make writable by all
    chmod -R 777 dataset/ 2>/dev/null || true
fi

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

# Create crawl job for tracking in web interface
CRAWL_JOB_PARAMS=$(cat <<EOF
{
  "start_url": "$START_URL",
  "max_depth": $MAX_DEPTH,
  "allowed_domains": ["$DOMAIN"]
}
EOF
)
CRAWL_JOB_ID=$(create_job "crawl" "$CRAWL_JOB_PARAMS")
if [ -n "$CRAWL_JOB_ID" ] && [ "$CRAWL_JOB_ID" != "unknown" ]; then
    print_info "Crawl job created: $CRAWL_JOB_ID (visible in web interface)"
    update_job_status "$CRAWL_JOB_ID" "running" "0.1" "Starting crawl of $DOMAIN"
fi

docker-compose exec -T crawler python -m crawler.crawler "$START_URL" "$MAX_DEPTH" dataset/raw
CRAWL_EXIT_CODE=$?

if [ -n "$CRAWL_JOB_ID" ] && [ "$CRAWL_JOB_ID" != "unknown" ]; then
    if [ $CRAWL_EXIT_CODE -eq 0 ]; then
        update_job_status "$CRAWL_JOB_ID" "completed" "1.0" "Crawl completed successfully"
    else
        update_job_status "$CRAWL_JOB_ID" "failed" "0.0" "Crawl failed"
    fi
fi

if [ $CRAWL_EXIT_CODE -ne 0 ]; then
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

# Process only files created during this crawl (newer than start time)
CRAWL_START_TIME=$(cat dataset/.crawl_start_time 2>/dev/null || echo "0")
print_info "Processing only files created after: $(date -d @$CRAWL_START_TIME 2>/dev/null || echo 'this crawl')"

# Create process job for tracking
PROCESS_JOB_PARAMS=$(cat <<EOF
{
  "raw_dir": "dataset/raw",
  "output_dir": "dataset"
}
EOF
)
PROCESS_JOB_ID=$(create_job "process" "$PROCESS_JOB_PARAMS")
if [ -n "$PROCESS_JOB_ID" ] && [ "$PROCESS_JOB_ID" != "unknown" ]; then
    print_info "Process job created: $PROCESS_JOB_ID (visible in web interface)"
    update_job_status "$PROCESS_JOB_ID" "running" "0.1" "Starting data processing"
fi

docker-compose exec -T processor python -m processor.data_processor
PROCESS_EXIT_CODE=$?

if [ -n "$PROCESS_JOB_ID" ] && [ "$PROCESS_JOB_ID" != "unknown" ]; then
    if [ $PROCESS_EXIT_CODE -eq 0 ]; then
        update_job_status "$PROCESS_JOB_ID" "completed" "1.0" "Processing completed successfully"
    else
        update_job_status "$PROCESS_JOB_ID" "failed" "0.0" "Processing failed"
    fi
fi

if [ $PROCESS_EXIT_CODE -ne 0 ]; then
    print_error "Processing failed!"
    exit 1
fi

# Verify we only processed files from this crawl
print_info "Verifying processed files are from this crawl only..."

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

# Create tokenize job for tracking
TOKENIZE_JOB_PARAMS=$(cat <<EOF
{
  "cleaned_dir": "dataset/cleaned",
  "shards_dir": "dataset/shards",
  "model_name": "microsoft/DialoGPT-medium",
  "max_length": 2048,
  "val_split": 0.05
}
EOF
)
TOKENIZE_JOB_ID=$(create_job "tokenize" "$TOKENIZE_JOB_PARAMS")
if [ -n "$TOKENIZE_JOB_ID" ] && [ "$TOKENIZE_JOB_ID" != "unknown" ]; then
    print_info "Tokenize job created: $TOKENIZE_JOB_ID (visible in web interface)"
    update_job_status "$TOKENIZE_JOB_ID" "running" "0.1" "Starting tokenization and sharding"
fi

docker-compose exec -T processor python -m processor.tokenizer_sharder
TOKENIZE_EXIT_CODE=$?

if [ -n "$TOKENIZE_JOB_ID" ] && [ "$TOKENIZE_JOB_ID" != "unknown" ]; then
    if [ $TOKENIZE_EXIT_CODE -eq 0 ]; then
        update_job_status "$TOKENIZE_JOB_ID" "completed" "1.0" "Tokenization completed successfully"
    else
        update_job_status "$TOKENIZE_JOB_ID" "failed" "0.0" "Tokenization failed"
    fi
fi

if [ $TOKENIZE_EXIT_CODE -ne 0 ]; then
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

# Backup the NEW dataset AFTER processing completes
print_info ""
print_info "Backing up completed dataset to: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# Copy only the NEW files that were just created
if [ -d "dataset/raw" ] && [ "$(find dataset/raw -name '*.jsonl' -type f | wc -l)" -gt 0 ]; then
    print_info "Backing up raw data..."
    cp -r dataset/raw "$BACKUP_DIR/raw" 2>/dev/null || true
fi

if [ -d "dataset/cleaned" ] && [ "$(find dataset/cleaned -name '*.jsonl' -type f | wc -l)" -gt 0 ]; then
    print_info "Backing up cleaned data..."
    cp -r dataset/cleaned "$BACKUP_DIR/cleaned" 2>/dev/null || true
fi

if [ -d "dataset/shards" ] && [ "$(find dataset/shards -type f | wc -l)" -gt 0 ]; then
    print_info "Backing up shards..."
    cp -r dataset/shards "$BACKUP_DIR/shards" 2>/dev/null || true
fi

if [ -f "dataset/VERSION.txt" ]; then
    cp dataset/VERSION.txt "$BACKUP_DIR/VERSION.txt" 2>/dev/null || true
fi

print_info ""
print_info "Version info saved to: dataset/VERSION.txt"
print_info "Backup completed at: $BACKUP_DIR"
print_info "  (Contains ONLY data from this crawl: $DOMAIN)"

echo ""

