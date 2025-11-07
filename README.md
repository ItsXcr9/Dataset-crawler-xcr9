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
- **Web UI**: http://localhost:3000
- **API**: http://localhost:8000
- **MinIO Console**: http://localhost:9001 (admin/admin)
- **Grafana**: http://localhost:3001 (admin/admin)
- **Prometheus**: http://localhost:9090

### Basic Usage

#### Using the Web UI

1. Open http://localhost:3000
2. Click "Start New Crawl"
3. Enter starting URL (e.g., `https://kubernetes.io/docs/home/`)
4. Set crawl parameters:
   - Max depth: 3
   - Domains: auto-detected from start URL
5. Click "Start Crawl"
6. Monitor progress in real-time
7. Process data when crawl completes

#### Using the API

```bash
# Start a crawl
curl -X POST http://localhost:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "start_url": "https://kubernetes.io/docs/home/",
    "max_depth": 3
  }'

# Check job status
curl http://localhost:8000/jobs/{job_id}

# Process crawled data
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{
    "raw_dir": "dataset/raw",
    "output_dir": "dataset"
  }'

# Create training shards
curl -X POST http://localhost:8000/tokenize \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "microsoft/DialoGPT-medium",
    "max_length": 2048
  }'
```

#### Using the Command Line

```bash
# Start crawling
docker-compose exec crawler python -m crawler.crawler https://kubernetes.io/docs/home/ 3 dataset/raw

# Process data
docker-compose exec processor python -m processor.data_processor

# Tokenize and shard
docker-compose exec processor python -m processor.tokenizer_sharder
```

## Dataset Structure

```
dataset/
├── raw/                    # Raw crawled data (JSONL)
├── cleaned/               # Processed and cleaned data
├── metadata/              # Dataset metadata and statistics
│   ├── manifest.jsonl     # Document manifest
│   └── dataset_stats.csv  # Statistics
├── shards/                # Training-ready shards
│   ├── train/            # Training shards
│   └── val/              # Validation shards
├── tokenizer/            # Tokenizer files
└── registry.yaml         # Version registry
```

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

Access Grafana at http://localhost:3001 and import the provided dashboard:

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
