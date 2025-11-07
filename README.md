# Professional Web Crawler Dataset Creator

A comprehensive system for crawling websites and creating high-quality datasets for Large Language Model (LLM) training, similar to professional crawlers like Google's.

## Features

- **Professional Web Crawler**: Recursive crawling with respect for robots.txt, rate limiting, and distributed architecture
- **Advanced Data Processing**: Deduplication, language detection, quality filtering, and content cleaning
- **Tokenization & Sharding**: Convert cleaned data into training-ready shards using modern tokenizers
- **Dataset Versioning**: Git-based versioning system for reproducible datasets
- **Monitoring & Observability**: Prometheus metrics, Grafana dashboards, and comprehensive logging
- **Scalable Architecture**: Docker Compose setup with PostgreSQL, Redis, MinIO, and distributed workers
- **Web UI**: User-friendly interface for managing crawls and monitoring progress

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Crawler   │ -> │ Data Processor  │ -> │ Tokenizer       │
│                 │    │                 │    │ & Sharder       │
│ - Scrapy-based  │    │ - Deduplication │    │                 │
│ - Recursive     │    │ - Quality       │    │ - BPE/Tokenizers│
│ - Rate limited  │    │ - Language det  │    │ - Arrow/Parquet │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         v                       v                       v
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Raw Data      │    │  Cleaned Data   │    │   Training      │
│                 │    │                 │    │   Shards        │
│ - JSONL format  │    │ - Deduplicated  │    │                 │
│ - Full content  │    │ - Quality > 0.6 │    │ - Tokenized     │
│ - Metadata      │    │ - Multi-lingual │    │ - Sharded       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- At least 16GB RAM recommended
- 100GB+ free disk space for large crawls

### Installation

1. **Clone and setup**:
```bash
git clone <repository>
cd crawler-dataset
```

2. **Start all services**:
```bash
docker-compose up -d
```

3. **Access the services**:
- **Web UI**: http://localhost:13000
- **API**: http://localhost:18000
- **MinIO Console**: http://localhost:19001 (admin/admin)
- **Grafana**: http://localhost:13001 (admin/admin)
- **Prometheus**: http://localhost:19090

### Basic Usage

#### 🚀 **Recommended: Using the Full Site Crawler Script**

The easiest way to crawl an entire website domain and create a complete dataset:

```bash
# Make the script executable
chmod +x crawl_full_site.sh

# Crawl entire Kubernetes documentation
./crawl_full_site.sh https://kubernetes.io/docs/

# Crawl with custom depth and version name
./crawl_full_site.sh https://kubernetes.io/docs/ 7 kubernetes_full_v1

# Other examples
./crawl_full_site.sh https://docs.python.org/ 6 python_docs_v1
./crawl_full_site.sh https://reactjs.org/docs/ 5 react_docs_v1
```

**What the script does:**
1. ✅ Automatically restricts crawling to the same domain
2. ✅ Backs up existing datasets with versioning
3. ✅ Crawls all pages up to specified depth
4. ✅ Processes and cleans the data
5. ✅ Creates training-ready shards
6. ✅ Shows detailed statistics
7. ✅ Saves version info for reproducibility

**Domain Restriction (Includes All Subdomains):**
- The crawler automatically extracts the **root domain** from your start URL
- **Example**: Starting from `https://kubernetes.io/docs/` will crawl:
  - ✅ `kubernetes.io` (main domain)
  - ✅ `docs.kubernetes.io` (subdomain)
  - ✅ `blog.kubernetes.io` (subdomain)
  - ✅ Any other `*.kubernetes.io` subdomain
- It will **never** follow links to external domains like github.com, twitter.com, etc.
- **Subdomain Examples:**
  - `https://docs.python.org/` → crawls all `*.python.org` subdomains
  - `https://blog.example.com/` → crawls all `*.example.com` subdomains
  - `https://kubernetes.io/docs/` → crawls all `*.kubernetes.io` subdomains

**Depth Recommendations:**
- **Depth 3-4**: Small sites, quick testing (~100-1000 pages)
- **Depth 5-6**: Medium documentation sites (~1000-10000 pages)
- **Depth 7-8**: Large documentation sites (~10000+ pages)
- **Depth 9+**: Very large sites (may take hours)

#### Using the Web UI

1. Open http://localhost:13000
2. Click "Start New Crawl"
3. Enter starting URL (e.g., `https://kubernetes.io/docs/`)
4. Set crawl parameters:
   - Max depth: 6 (recommended for complete docs)
   - Domains: auto-detected from start URL
5. Click "Start Crawl"
6. Monitor progress in real-time
7. Process data when crawl completes

#### Using the API

```bash
# Start a crawl
curl -X POST http://localhost:18000/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "start_url": "https://kubernetes.io/docs/",
    "max_depth": 6
  }'

# Check job status
curl http://localhost:18000/jobs/{job_id}

# Process crawled data
curl -X POST http://localhost:18000/process \
  -H "Content-Type: application/json" \
  -d '{
    "raw_dir": "dataset/raw",
    "output_dir": "dataset"
  }'

# Create training shards
curl -X POST http://localhost:18000/tokenize \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "microsoft/DialoGPT-medium",
    "max_length": 2048
  }'
```

#### Using the Command Line (Manual Steps)

```bash
# Step 1: Crawl (depth 6 for complete documentation)
docker-compose exec crawler python -m crawler.crawler https://kubernetes.io/docs/ 6 dataset/raw

# Step 2: Process and clean data
docker-compose exec processor python -m processor.data_processor

# Step 3: Tokenize and create training shards
docker-compose exec processor python -m processor.tokenizer_sharder
```

#### 📊 Checking Dataset Quality

```bash
# View dataset statistics
cat dataset/VERSION.txt

# Check training manifest
cat dataset/shards/train_manifest.json | jq .

# Count documents
wc -l dataset/cleaned/*.jsonl

# View a sample document
head -1 dataset/cleaned/*.jsonl | jq .
```

## Dataset Structure

```
dataset/
├── raw/                    # Raw crawled data (JSONL)
├── cleaned/               # Processed and cleaned data
├── metadata/              # Dataset metadata and statistics
│   ├── manifest.jsonl     # Document manifest
│   └── dataset_stats.csv  # Statistics
├── shards/                # Training-ready shards (USE THESE FOR TRAINING)
│   ├── train/            # Training shards (*.parquet files)
│   │   ├── shard_001.parquet
│   │   └── shard_002.parquet
│   ├── val/              # Validation shards
│   │   └── shard_001.parquet
│   ├── train_manifest.json   # Training metadata
│   ├── val_manifest.json     # Validation metadata
│   └── tokenizer_config.json # Tokenizer configuration
├── VERSION.txt            # Current dataset version info
│
dataset_versions/          # Saved versions (managed by manage_versions.sh)
├── kubernetes_v1/         # Version 1
│   └── shards/
├── kubernetes_v2/         # Version 2  
│   └── shards/
└── python_docs_v1/        # Another dataset
    └── shards/

dataset_registry.json      # Version tracking and training status
trained_versions.log       # Training history
```

## Dataset Versioning & Training

### Version Management

The system includes a powerful versioning system for managing multiple datasets and tracking training status:

```bash
# List all versions
./manage_versions.sh list

# Save current dataset as a version
./manage_versions.sh save kubernetes_v1 "Complete Kubernetes docs"

# Load a specific version for training
./manage_versions.sh load kubernetes_v1

# Mark version as trained after training
./manage_versions.sh trained kubernetes_v1

# Find untrained versions
./manage_versions.sh untrained

# Compare two versions (see what changed)
./manage_versions.sh compare kubernetes_v1 kubernetes_v2
```

### Training Workflow

**Step 1: Create Dataset Version**
```bash
# Crawl and save as version
./crawl_full_site.sh https://kubernetes.io/docs/ 7 k8s_v1
./manage_versions.sh save k8s_v1 "Initial Kubernetes docs"
```

**Step 2: Train Your Model**

Use the parquet files in `dataset/shards/` for training:

```python
# Example: PyTorch DataLoader
from datasets import load_dataset

train_dataset = load_dataset('parquet', 
    data_files='dataset/shards/train/*.parquet',
    split='train'
)

val_dataset = load_dataset('parquet',
    data_files='dataset/shards/val/*.parquet', 
    split='train'
)

# Use with Hugging Face Trainer
from transformers import Trainer, TrainingArguments

training_args = TrainingArguments(
    output_dir="./results",
    per_device_train_batch_size=8,
    num_train_epochs=3,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=val_dataset,
)

trainer.train()
```

**Step 3: Mark as Trained**
```bash
./manage_versions.sh trained k8s_v1
```

### Incremental Training (Update with New Data)

```bash
# Later, when documentation is updated...
./crawl_full_site.sh https://kubernetes.io/docs/ 7 k8s_v2
./manage_versions.sh save k8s_v2 "Updated Q2 2024"

# See what changed
./manage_versions.sh compare k8s_v1 k8s_v2

# Train on new version
./manage_versions.sh load k8s_v2
# ... train your model ...
./manage_versions.sh trained k8s_v2
```

### Parquet File Structure

Each shard contains these columns:
- `input_ids`: Tokenized input (ready for training)
- `attention_mask`: Attention masks
- `labels`: Training labels
- `content`: Original text
- `language`: Detected language
- `url`: Source URL
- `title`: Page title
- `domain`: Source domain

## Configuration

### Crawler Settings

Edit `config/crawler_config.yaml`:

```yaml
crawler:
  max_depth: 3
  concurrent_requests: 4
  download_delay: 1
  respect_robots: true
  user_agent: "ProfessionalDatasetCrawler/1.0"
```

### Processor Settings

Edit `config/processor_config.yaml`:

```yaml
deduplication:
  fuzzy_threshold: 0.8
  num_perm: 128

quality:
  min_content_length: 500
  max_content_length: 100000
  min_quality_score: 0.6

language:
  supported_languages: [en, zh, es, fr, de, ja, ko, ru]
  min_confidence: 0.7
```

## Monitoring

### Metrics Available

- **Crawler**: Pages crawled, links extracted, processing time
- **Processor**: Documents processed/filtered, quality scores
- **System**: CPU, memory, disk usage
- **Dataset**: Size, quality metrics, language distribution

### Grafana Dashboards

Access Grafana at http://localhost:13001 and import the provided dashboard:

- **Crawler Performance**: Crawl rates, error rates, queue status
- **Data Quality**: Language distribution, quality scores, filtering stats
- **System Resources**: CPU, memory, disk usage across services

## Dataset Quality Features

### Deduplication
- **Exact**: SHA256 content hashing
- **Fuzzy**: MinHash + LSH for near-duplicate detection

### Quality Filtering
- **Length**: Minimum/maximum content length
- **Language**: Support for 8+ languages with confidence scoring
- **Readability**: Automated readability assessment
- **Entropy**: Information density measurement

### Content Cleaning
- HTML tag removal
- URL and email redaction
- Excessive punctuation normalization
- Unicode normalization

## Scaling

### Horizontal Scaling

```bash
# Scale crawler workers
docker-compose up -d --scale crawler=5

# Scale processor workers
docker-compose up -d --scale processor=3
```

### Large-Scale Deployment

For production deployments:

1. **Use external databases**: Replace PostgreSQL/Redis with managed services
2. **Object storage**: Use S3/GCS instead of MinIO
3. **Kubernetes**: Deploy using the provided Helm charts
4. **GPU support**: Add GPU workers for accelerated tokenization

## API Reference

### Endpoints

- `POST /crawl` - Start crawling job
- `POST /process` - Start processing job
- `POST /tokenize` - Start tokenization job
- `GET /jobs/{id}` - Get job status
- `GET /jobs` - List all jobs
- `GET /dataset/summary` - Get dataset summary
- `GET /dataset/versions` - List dataset versions

### Job Statuses

- `queued` - Job waiting to start
- `running` - Job in progress
- `completed` - Job finished successfully
- `failed` - Job failed with error

## Development

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run individual components
python -m crawler.crawler
python -m processor.data_processor
python -m processor.tokenizer_sharder

# Run API server
uvicorn api.main:app --reload
```

### Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html
```

## Troubleshooting

### Common Issues

1. **Crawler gets blocked**:
   - Reduce concurrent requests
   - Increase download delay
   - Rotate user agents

2. **Out of memory**:
   - Reduce batch sizes in config
   - Increase container memory limits
   - Process data in smaller chunks

3. **Slow processing**:
   - Scale worker containers
   - Use SSD storage
   - Enable GPU acceleration for tokenization

### Logs

```bash
# View service logs
docker-compose logs crawler
docker-compose logs processor
docker-compose logs api

# Follow logs
docker-compose logs -f
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built with Scrapy, FastAPI, and modern NLP libraries
- Inspired by OpenAI's WebText and Common Crawl
- Designed for creating datasets at Qwen3/LLaMA3 scale
