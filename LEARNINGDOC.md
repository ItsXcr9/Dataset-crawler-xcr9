# Deep Technical Guide: Web Crawler to LLM Training Pipeline
## From Zero to Hero - Complete Technical Deep Dive

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Web Crawling Deep Dive](#2-web-crawling-deep-dive)
3. [Data Processing Pipeline](#3-data-processing-pipeline)
4. [Tokenization & Sharding](#4-tokenization--sharding)
5. [Model Training Architecture](#5-model-training-architecture)
6. [Storage & Versioning](#6-storage--versioning)
7. [Docker & Infrastructure](#7-docker--infrastructure)
8. [API & Web Interface](#8-api--web-interface)
9. [Performance Optimization](#9-performance-optimization)
10. [Troubleshooting & Debugging](#10-troubleshooting--debugging)

---

## 1. System Architecture Overview

### 1.1 High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER INPUT (URL)                              │
└───────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: WEB CRAWLING (crawler/crawler.py)                      │
│  ────────────────────────────────────────────────────────────   │
│  • Scrapy CrawlSpider                                           │
│  • Domain restriction (root domain extraction)                  │
│  • Robots.txt compliance                                        │
│  • Rate limiting & politeness                                   │
│  • HTML parsing & text extraction                               │
│  • Output: Raw JSONL files (dataset/raw/*.jsonl)                │
└───────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: DATA PROCESSING (processor/data_processor.py)          │
│  ────────────────────────────────────────────────────────────   │
│  • Language detection (langdetect)                              │
│  • Quality scoring (textstat)                                   │
│  • Deduplication (exact + fuzzy with simhash)                   │
│  • Content cleaning & normalization                             │
│  • Time-based filtering (only current crawl)                    │
│  • Output: Cleaned JSONL files (dataset/cleaned/*.jsonl)         │
└───────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: TOKENIZATION & SHARDING (processor/tokenizer_sharder.py)│
│  ────────────────────────────────────────────────────────────   │
│  • HuggingFace tokenizer (BPE/WordPiece)                        │
│  • Sequence tokenization (input_ids, attention_mask)            │
│  • Train/Val split (95/5)                                       │
│  • Parquet sharding (512MB chunks)                              │
│  • Manifest generation (metadata JSON)                           │
│  • Output: Parquet shards (dataset/shards/train/*.parquet)      │
└───────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: MODEL TRAINING (trainer/model_trainer.py)              │
│  ────────────────────────────────────────────────────────────   │
│  • Model loading (AutoModelForCausalLM)                         │
│  • Dataset loading (ParquetDataset)                             │
│  • Training loop (HuggingFace Trainer)                          │
│  • Checkpointing & early stopping                               │
│  • Model saving (HuggingFace format)                            │
│  • Output: Trained model (models/<name>/)                        │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Interaction

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Crawler    │────▶│  Processor   │────▶│  Tokenizer   │
│  (Scrapy)    │     │  (Cleaning)  │     │  (Sharding)  │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────────────────────────────────────────────────┐
│           Shared Storage (dataset/)                  │
│  • raw/        - Raw crawled data                    │
│  • cleaned/    - Processed data                      │
│  • shards/     - Training-ready shards               │
│  • metadata/   - Statistics & manifests             │
└──────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│   Trainer    │
│  (PyTorch)   │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Models/    │
│  (Output)    │
└──────────────┘
```

---

## 2. Web Crawling Deep Dive

### 2.1 Scrapy Architecture

**Technology**: Scrapy Framework (Python)
**Pattern**: CrawlSpider with LinkExtractor

#### Core Components:

```python
class DatasetCrawler(CrawlSpider):
    name = 'dataset_crawler'
    
    # 1. INITIALIZATION ORDER (CRITICAL!)
    def __init__(self, start_url, max_depth, output_dir, *args, **kwargs):
        # MUST set these BEFORE super().__init__()
        self.start_urls = [start_url]
        self.allowed_domains = [extract_root_domain(start_url)]
        self.max_depth = max_depth
        self.output_dir = output_dir
        self.visited_urls = set()
        self.crawled_data = []
        
        # Define rules for link following
        self.rules = (
            Rule(LinkExtractor(allow=(), deny_extensions=...), 
                 callback='parse_item', 
                 follow=True),
        )
        
        # Compile rules BEFORE super().__init__()
        self._compile_rules()
        
        # NOW call super().__init__()
        super().__init__(*args, **kwargs)
```

**Why this order matters:**
- `CrawlSpider` reads `start_urls` and `allowed_domains` during `__init__()`
- Rules must be compiled before parent initialization
- Otherwise, spider won't follow links correctly

### 2.2 Domain Restriction Algorithm

**Problem**: Allow all subdomains (e.g., `docs.kubernetes.io`, `blog.kubernetes.io`) but block external domains.

**Solution**: Root domain extraction

```python
def extract_root_domain(netloc):
    """
    Extract root domain from netloc
    Examples:
        docs.kubernetes.io -> kubernetes.io
        blog.example.com -> example.com
        www.example.co.uk -> example.co.uk
    """
    domain_parts = netloc.split('.')
    
    if len(domain_parts) >= 3:
        # Check for special TLDs (co.uk, com.au, etc.)
        if domain_parts[-2] in ['co', 'com', 'net', 'org']:
            # example.co.uk -> last 3 parts
            return '.'.join(domain_parts[-3:])
    
    # Standard case: example.com -> last 2 parts
    return '.'.join(domain_parts[-2:])
```

**How it works:**
1. Split domain by dots: `['docs', 'kubernetes', 'io']`
2. Check for special TLDs (co.uk, com.au)
3. Return last 2-3 parts as root domain
4. Scrapy's `allowed_domains` automatically allows all subdomains

### 2.3 HTML Content Extraction

**Challenge**: Extract clean text, exclude navigation, ads, scripts.

**Solution**: CSS selector with `:not()` pseudo-class

```python
def extract_text_content(self, response):
    """
    Extract main content, excluding unwanted elements
    """
    # Remove script, style, nav, footer, etc.
    content = response.css('body *:not(script):not(style):not(nav):not(footer):not(header):not(.sidebar):not(.advertisement)::text').getall()
    
    # Join and clean
    text = ' '.join(content)
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    return text.strip()
```

**Why `:not()` instead of `.remove()`:**
- Scrapy selectors are lazy (don't modify DOM)
- `.remove()` doesn't work on Scrapy selectors
- `:not()` filters at selector level (more efficient)

### 2.4 Robots.txt Compliance

**Implementation**: `ROBOTSTXT_OBEY = True` in Scrapy settings

**How it works:**
1. Scrapy fetches `robots.txt` from domain root
2. Parses rules using `urllib.robotparser`
3. Checks `User-agent: *` and specific user-agent rules
4. Respects `Crawl-delay` directives
5. Blocks URLs matching `Disallow:` patterns

**Example robots.txt:**
```
User-agent: *
Allow: /docs/
Disallow: /api/
Crawl-delay: 1
```

### 2.5 Rate Limiting & Politeness

**Settings:**
```python
'DOWNLOAD_DELAY': 1.0,  # 1 second between requests
'RANDOMIZE_DOWNLOAD_DELAY': 0.5,  # Randomize ±50%
'CONCURRENT_REQUESTS': 16,  # Max parallel requests
'CONCURRENT_REQUESTS_PER_DOMAIN': 8,  # Per domain limit
```

**Why this matters:**
- Prevents server overload
- Reduces risk of IP blocking
- Respects website resources
- Maintains good "netizen" behavior

### 2.6 Data Storage Format (JSONL)

**Format**: JSON Lines (one JSON object per line)

**Example:**
```jsonl
{"id": "crawl_123_abc", "url": "https://example.com/page1", "title": "Page 1", "content": "Text content...", "domain": "example.com", "content_length": 1234, "crawled_at": "2025-11-07T19:00:00Z"}
{"id": "crawl_123_def", "url": "https://example.com/page2", "title": "Page 2", "content": "More text...", "domain": "example.com", "content_length": 5678, "crawled_at": "2025-11-07T19:00:01Z"}
```

**Why JSONL:**
- Streamable (can process line-by-line)
- Append-friendly (easy to add new records)
- Memory efficient (don't need to load entire file)
- Compatible with pandas, PyArrow, etc.

---

## 3. Data Processing Pipeline

### 3.1 Language Detection

**Library**: `langdetect` (based on Google's language-detection)

**How it works:**
1. Analyzes character n-grams (character sequences)
2. Compares against language models (trained on Wikipedia)
3. Returns language code (e.g., 'en', 'fa', 'ar')
4. Confidence score (0.0 to 1.0)

**Code:**
```python
from langdetect import detect, DetectorFactory

# Set seed for reproducibility
DetectorFactory.seed = 0

language = detect(text)
# Returns: 'en', 'fa', 'ar', etc.
```

**Filtering**: Only keep `language == 'en'` for English-only datasets

### 3.2 Quality Scoring

**Library**: `textstat` (text statistics)

**Metrics calculated:**
1. **Flesch Reading Ease**: Readability score (0-100)
2. **Average Sentence Length**: Words per sentence
3. **Average Syllables per Word**: Complexity indicator
4. **Character Count**: Document length
5. **Word Count**: Vocabulary richness

**Quality Score Formula:**
```python
def calculate_quality_score(text):
    """
    Composite quality score (0.0 to 1.0)
    Higher = better quality
    """
    if len(text) < 500:  # Too short
        return 0.0
    
    # Normalize metrics to 0-1 range
    flesch = textstat.flesch_reading_ease(text) / 100.0
    sentence_length = min(textstat.avg_sentence_length(text) / 30.0, 1.0)
    word_complexity = min(textstat.avg_syllables_per_word(text) / 3.0, 1.0)
    
    # Weighted average
    quality = (flesch * 0.4 + sentence_length * 0.3 + word_complexity * 0.3)
    return max(0.0, min(1.0, quality))
```

**Filtering**: Only keep documents with `quality_score > 0.6`

### 3.3 Deduplication Strategy

**Two-stage approach:**

#### Stage 1: Exact Deduplication
```python
seen_content = set()
for doc in documents:
    content_hash = hashlib.md5(doc['content'].encode()).hexdigest()
    if content_hash in seen_content:
        skip  # Exact duplicate
    seen_content.add(content_hash)
```

#### Stage 2: Fuzzy Deduplication (SimHash)
```python
from simhash import Simhash

def get_simhash(text):
    """Generate 64-bit simhash fingerprint"""
    tokens = text.lower().split()
    return Simhash(tokens).value

# Compare simhashes (Hamming distance)
def is_similar(hash1, hash2, threshold=3):
    """
    Check if two simhashes are similar
    threshold=3 means max 3 bits different (out of 64)
    """
    hamming = bin(hash1 ^ hash2).count('1')
    return hamming <= threshold
```

**SimHash Algorithm:**
1. Tokenize text into words
2. Hash each token to 64-bit integer
3. Create 64-element vector (one per bit position)
4. For each token hash, increment/decrement vector positions
5. Final hash: positive positions = 1, negative = 0
6. Similar texts have similar hashes (few bit differences)

**Why SimHash:**
- Fast comparison (bitwise XOR)
- Detects near-duplicates (typos, minor edits)
- Memory efficient (64 bits per document)
- Used by Google for web page deduplication

### 3.4 Time-Based Filtering

**Problem**: Processor might process old files from previous crawls.

**Solution**: Timestamp-based filtering

```python
# In crawl_full_site.sh
CRAWL_START_TIME=$(date +%s)
echo "$CRAWL_START_TIME" > dataset/.crawl_start_time

# In data_processor.py
crawl_start_file = Path(raw_dir).parent / ".crawl_start_time"
if crawl_start_file.exists():
    crawl_start_time = float(crawl_start_file.read_text().strip())
    # Only process files modified after crawl started
    raw_files = [
        f for f in raw_files 
        if f.stat().st_mtime >= (crawl_start_time - 10)  # 10s buffer
    ]
```

**How it works:**
1. Record Unix timestamp when crawl starts
2. Save to `dataset/.crawl_start_time`
3. Processor checks file modification time (`st_mtime`)
4. Only processes files created after crawl start
5. 10-second buffer accounts for clock skew

---

## 4. Tokenization & Sharding

### 4.1 Tokenization Process

**Library**: HuggingFace Transformers `AutoTokenizer`

**Tokenization Types:**

#### 4.1.1 BPE (Byte Pair Encoding)
- Used by: GPT-2, GPT-3, GPT-4, RoBERTa
- Algorithm:
  1. Start with character-level vocabulary
  2. Find most frequent byte pair
  3. Merge into single token
  4. Repeat until vocabulary size reached
- Example: "hello" → ["he", "ll", "o"] (after training)

#### 4.1.2 WordPiece
- Used by: BERT, DistilBERT
- Similar to BPE but uses word-level statistics
- Example: "unhappiness" → ["un", "##happiness"]

#### 4.1.3 SentencePiece
- Used by: T5, ALBERT, Qwen
- Works on raw text (no pre-tokenization)
- Handles multiple languages better
- Example: "Hello world" → ["▁Hello", "▁world"] (▁ = space)

**Our Implementation:**
```python
tokenizer = AutoTokenizer.from_pretrained("microsoft/DialoGPT-medium")

encoding = tokenizer(
    text,
    truncation=True,
    padding=False,
    max_length=2048,
    return_attention_mask=True
)

# Returns:
# {
#   'input_ids': [101, 2023, 2003, ...],  # Token IDs
#   'attention_mask': [1, 1, 1, ...]      # 1 = real token, 0 = padding
# }
```

### 4.2 Sharding Strategy

**Why Shard?**
- Large datasets don't fit in memory
- Enables parallel processing
- Faster loading (only load needed shards)
- Distributed training support

**Shard Size**: 512 MB (configurable)

**Algorithm:**
```python
def create_shards(documents, shard_size_mb=512):
    shards = []
    current_shard = []
    current_size_bytes = 0
    
    avg_doc_size = 2048  # Estimate: tokens * ~2 bytes
    
    for doc in documents:
        current_shard.append(doc)
        current_size_bytes += avg_doc_size
        
        if current_size_bytes >= shard_size_mb * 1024 * 1024:
            # Shard is full, save it
            shard = save_shard(current_shard, shard_id)
            shards.append(shard)
            current_shard = []
            current_size_bytes = 0
    
    # Save remaining documents
    if current_shard:
        shard = save_shard(current_shard, shard_id)
        shards.append(shard)
    
    return shards
```

### 4.3 Parquet Format

**Why Parquet?**
- Columnar storage (efficient compression)
- Schema preservation (types, nullability)
- Fast reads (only load needed columns)
- Cross-language support (Python, R, Java, etc.)

**Schema:**
```python
schema = pa.schema([
    ('doc_id', pa.string()),
    ('tokens', pa.list_(pa.int32())),      # Variable-length list
    ('attention_mask', pa.list_(pa.int32())),
    ('language', pa.string()),
    ('quality_score', pa.float32()),
    ('token_count', pa.int32()),
])
```

**Storage:**
- Compression: Snappy (fast, good compression)
- Row groups: ~10,000 rows per group
- Metadata: Embedded schema + statistics

### 4.4 Train/Validation Split

**Ratio**: 95% train, 5% validation

**Implementation:**
```python
# Shuffle for randomness
np.random.shuffle(all_documents)

# Split
val_size = int(len(all_documents) * 0.05)
val_docs = all_documents[:val_size]
train_docs = all_documents[val_size:]
```

**Why shuffle?**
- Prevents temporal bias (newer docs in val)
- Ensures representative distribution
- Better generalization

### 4.5 Manifest Files

**Purpose**: Metadata about shards (for training orchestration)

**Structure:**
```json
{
  "version": "1.0",
  "created_at": "2025-11-07T19:00:00Z",
  "total_shards": 5,
  "total_documents": 1000,
  "total_tokens": 5000000,
  "shards": [
    {
      "shard_id": "04d",
      "file": "shard_04d.parquet",
      "documents": 200,
      "tokens": 1000000,
      "languages": {"en": 200},
      "avg_quality": 0.75,
      "created_at": "2025-11-07T19:00:00Z"
    },
    ...
  ]
}
```

**Usage:**
- Training scripts read manifest to know which shards to load
- Enables distributed training (each worker gets different shards)
- Tracks dataset statistics

---

## 5. Model Training Architecture

### 5.1 Model Loading

**Library**: HuggingFace Transformers

**Process:**
```python
# 1. Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(
    "Qwen/Qwen2.5-0.5B",
    trust_remote_code=True  # For custom models
)

# 2. Load model
model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-0.5B",
    trust_remote_code=True,
    torch_dtype=torch.float16 if use_gpu else torch.float32,
    device_map="auto" if use_gpu else None,  # Auto GPU placement
    low_cpu_mem_usage=True  # Efficient loading
)

# 3. Resize token embeddings (if vocab size changed)
model.resize_token_embeddings(len(tokenizer))
```

**Model Architecture (Causal LM):**
```
Input: [batch_size, sequence_length]
    ↓
Embedding Layer: [batch_size, seq_len, hidden_size]
    ↓
Transformer Blocks (N layers):
    - Self-Attention
    - Feed-Forward
    - Layer Norm
    - Residual Connections
    ↓
Output Head: [batch_size, seq_len, vocab_size]
    ↓
Logits: Probabilities for next token
```

### 5.2 Dataset Loading

**Custom Dataset Class:**
```python
class ParquetDataset(Dataset):
    def __init__(self, shard_dir, tokenizer, max_length=2048):
        # Find all parquet files
        self.shard_files = list(Path(shard_dir).glob("*.parquet"))
        
        # Load all data into memory
        self.data = []
        for shard_file in self.shard_files:
            table = pq.read_table(shard_file)
            for row in table.to_pylist():
                self.data.append({
                    'input_ids': torch.tensor(row['tokens'], dtype=torch.long),
                    'attention_mask': torch.tensor(row['attention_mask'], dtype=torch.long),
                    'labels': torch.tensor(row['tokens'], dtype=torch.long)  # For causal LM
                })
    
    def __getitem__(self, idx):
        return self.data[idx]
    
    def __len__(self):
        return len(self.data)
```

**Why load into memory?**
- Small datasets (< 1GB): Faster access
- Large datasets: Use lazy loading (load on-demand)

### 5.3 Training Loop (HuggingFace Trainer)

**HuggingFace Trainer handles:**
- Forward pass
- Loss calculation
- Backward pass (gradient computation)
- Optimizer step
- Learning rate scheduling
- Gradient accumulation
- Mixed precision (FP16/BF16)
- Checkpointing
- Evaluation

**Training Arguments:**
```python
TrainingArguments(
    output_dir="models/my_model",
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,  # Effective batch = 4 * 4 = 16
    learning_rate=2e-5,
    warmup_steps=100,  # Linear warmup
    logging_steps=100,
    save_steps=500,
    eval_steps=500,
    eval_strategy="steps",
    fp16=True,  # Mixed precision (GPU only)
    dataloader_num_workers=0,  # 0 = main process (avoids multiprocessing issues)
    load_best_model_at_end=True,
    metric_for_best_model="loss",
)
```

**Loss Function (Causal LM):**
```python
# Cross-entropy loss
# For each position i, predict token at position i+1
# Labels are shifted input_ids
loss = CrossEntropyLoss()(logits[:, :-1, :], labels[:, 1:])
```

**Forward Pass:**
```
Input: [batch=4, seq_len=512]
    ↓
Model Forward
    ↓
Logits: [batch=4, seq_len=512, vocab_size=50000]
    ↓
Loss Calculation (compare with labels)
    ↓
Backward Pass (compute gradients)
    ↓
Optimizer Step (update weights)
```

### 5.4 Optimizer & Learning Rate

**Optimizer**: AdamW (Adam with weight decay)

**Why AdamW:**
- Adaptive learning rates (per parameter)
- Handles sparse gradients well
- Weight decay for regularization
- Default choice for transformer training

**Learning Rate Schedule:**
```python
# Linear warmup + constant decay
lr(step) = {
    if step < warmup_steps:
        lr = base_lr * (step / warmup_steps)  # Warmup
    else:
        lr = base_lr * (1 - step / total_steps)  # Linear decay
}
```

**Typical Values:**
- Base LR: 2e-5 (0.00002)
- Warmup: 100-1000 steps
- Weight decay: 0.01

### 5.5 Gradient Accumulation

**Problem**: GPU memory limits batch size.

**Solution**: Gradient accumulation

```python
# Instead of:
loss.backward()
optimizer.step()  # Batch size = 4

# Do:
for i in range(4):  # Accumulate 4 batches
    loss = model(batch[i])
    loss = loss / 4  # Scale loss
    loss.backward()  # Accumulate gradients

optimizer.step()  # Effective batch size = 16
```

**Effective Batch Size** = `batch_size * gradient_accumulation_steps`

### 5.6 Mixed Precision Training (FP16)

**Why FP16:**
- 2x faster training
- 2x less memory usage
- Minimal accuracy loss

**How it works:**
```python
# Forward pass: FP16
with torch.cuda.amp.autocast():
    logits = model(inputs)  # FP16 computation
    loss = criterion(logits, labels)

# Backward pass: FP32 (for stability)
scaler.scale(loss).backward()  # Gradient scaling
scaler.step(optimizer)  # Unscale & update
scaler.update()
```

**Gradient Scaling:**
- FP16 can underflow (gradients too small)
- Scale loss by large factor (e.g., 65536)
- Compute gradients in FP32
- Unscale before optimizer step

### 5.7 Checkpointing

**What's saved:**
```
models/my_model/
├── config.json           # Model architecture
├── pytorch_model.bin     # Model weights
├── tokenizer_config.json # Tokenizer config
├── vocab.json            # Vocabulary
├── merges.txt            # BPE merges (if applicable)
├── training_args.bin      # Training arguments
└── training_info.json     # Custom metadata
```

**Checkpoint Strategy:**
- Save every N steps (`save_steps=500`)
- Keep last 3 checkpoints (`save_total_limit=3`)
- Save best model (`load_best_model_at_end=True`)

### 5.8 Early Stopping

**Purpose**: Prevent overfitting

**Implementation:**
```python
EarlyStoppingCallback(
    early_stopping_patience=3,  # Stop if no improvement for 3 evals
    early_stopping_threshold=0.001  # Min improvement to count
)
```

**How it works:**
1. Evaluate on validation set every N steps
2. Track best validation loss
3. If no improvement for 3 evaluations → stop training
4. Load best model (lowest validation loss)

---

## 6. Storage & Versioning

### 6.1 Directory Structure

```
dataset/
├── raw/                    # Raw crawled data
│   └── crawl_batch_*.jsonl
├── cleaned/                # Processed data
│   └── cleaned_*.jsonl
├── shards/                 # Training shards
│   ├── train/
│   │   └── *.parquet
│   ├── val/
│   │   └── *.parquet
│   ├── train_manifest.json
│   └── val_manifest.json
├── metadata/              # Statistics
│   └── dataset_stats.csv
├── VERSION.txt            # Current version info
└── .crawl_start_time    # Timestamp marker

dataset_backups/
└── <version_name>/
    ├── raw/
    ├── cleaned/
    └── shards/

models/
└── <model_name>/
    ├── config.json
    ├── pytorch_model.bin
    └── training_info.json
```

### 6.2 Version Management

**Concept**: Each crawl creates a versioned backup

**Process:**
1. Crawl creates data in `dataset/`
2. After processing, backup to `dataset_backups/<version>/`
3. Clear `dataset/` for next crawl
4. Versions are immutable (read-only)

**Version Selection:**
```bash
# Script lists all versions
1. Current dataset (dataset/shards/)
2. version1 (dataset_backups/version1/)
3. version2 (dataset_backups/version2/)
...
```

### 6.3 Cleanup Logic

**Critical**: Prevent old data from mixing with new

**Implementation:**
```bash
# 1. Remove entire directories (not just files)
rm -rf dataset/raw dataset/cleaned dataset/shards

# 2. Create fresh directories
mkdir -p dataset/{raw,cleaned,shards/train,shards/val}

# 3. Record start time
echo $(date +%s) > dataset/.crawl_start_time

# 4. Processor filters by modification time
```

**Why this matters:**
- Old files might have same names
- Modification time is reliable indicator
- Prevents data contamination

---

## 7. Docker & Infrastructure

### 7.1 Container Architecture

```
┌─────────────────────────────────────────────────┐
│              Docker Network                     │
│           (crawler_network)                     │
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ Crawler  │  │Processor │  │   API    │     │
│  │ (x3)     │  │  (x2)    │  │          │     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
│       │             │              │           │
│       └─────────────┼──────────────┘           │
│                     │                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ Postgres │  │  Redis   │  │  MinIO   │     │
│  └──────────┘  └──────────┘  └──────────┘     │
└─────────────────────────────────────────────────┘
```

### 7.2 Volume Mounts

**Purpose**: Persist data outside containers

**Configuration:**
```yaml
volumes:
  - ./dataset:/app/dataset:rw        # Read-write (crawler, processor)
  - ./models:/app/models:rw          # Read-write (trainer)
  - ./trainer:/app/trainer:ro       # Read-only (trainer code)
  - ./test_model.py:/app/test_model.py:ro
```

**Permissions:**
- Containers run as non-root (UID 1000)
- Host directories must be writable by UID 1000
- Script uses `chown` and `chmod` to fix permissions

### 7.3 Service Dependencies

**Health Checks:**
```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U crawler"]
  interval: 10s
  timeout: 5s
  retries: 5
```

**Dependency Chain:**
```
processor → postgres (healthy)
processor → redis (started)
processor → minio (healthy)
```

**Why health checks:**
- Ensures services are ready before starting
- Prevents race conditions
- Automatic retry on failure

### 7.4 Resource Management

**Memory:**
- Crawler: ~100MB per instance
- Processor: ~2GB (for tokenization)
- Trainer: ~8GB+ (depends on model size)

**CPU:**
- Crawler: I/O bound (network)
- Processor: CPU bound (text processing)
- Trainer: CPU/GPU bound (computation)

**Storage:**
- Raw data: ~1MB per page
- Cleaned: ~50% of raw (after filtering)
- Shards: ~500MB per shard
- Models: ~1-50GB (depends on model size)

---

## 8. API & Web Interface

### 8.1 API Architecture (FastAPI)

**Framework**: FastAPI (async Python web framework)

**Endpoints:**
```python
POST /crawl          # Start crawl job
POST /process        # Start processing job
POST /tokenize       # Start tokenization job
GET  /jobs           # List all jobs
GET  /jobs/{id}      # Get job status
GET  /dataset/summary # Get dataset statistics
```

**Job Tracking:**
```python
# Store in Redis
job_data = {
    "job_id": "crawl_20251107_120000",
    "type": "crawl",
    "status": "running",  # queued, running, completed, failed
    "progress": 0.5,       # 0.0 to 1.0
    "message": "Processing page 50/100",
    "created_at": "2025-11-07T12:00:00Z",
    "updated_at": "2025-11-07T12:05:00Z"
}

redis_client.set(f"job:{job_id}", json.dumps(job_data))
```

### 8.2 Web Interface (React)

**Technology Stack:**
- React (UI framework)
- TanStack Query (data fetching)
- Nginx (reverse proxy)

**Data Flow:**
```
Browser → Nginx (port 13000)
    ↓
Nginx → API (port 8000) via /api/ proxy
    ↓
API → Redis/Postgres
    ↓
Response → Browser
```

**Why Proxy:**
- Single origin (avoids CORS)
- Simplified API URLs (`/api/jobs` instead of `http://api:8000/jobs`)
- Can add authentication/rate limiting at proxy level

### 8.3 Real-time Updates

**Polling Strategy:**
```javascript
// Poll every 5 seconds
useQuery({
    queryKey: ['jobs'],
    queryFn: () => fetchJson('/api/jobs'),
    refetchInterval: 5000,  // 5 seconds
});
```

**Why Polling (not WebSockets):**
- Simpler implementation
- Works through proxies
- Sufficient for job monitoring
- No connection management needed

---

## 9. Performance Optimization

### 9.1 Crawling Performance

**Bottlenecks:**
1. Network latency (biggest)
2. HTML parsing
3. Disk I/O

**Optimizations:**
- Concurrent requests (16 parallel)
- Async I/O (Scrapy's Twisted framework)
- Batch file writes (append to single file)
- Connection pooling (reuse TCP connections)

### 9.2 Processing Performance

**Bottlenecks:**
1. Language detection (CPU intensive)
2. Quality scoring (text analysis)
3. Deduplication (hash computation)

**Optimizations:**
- Parallel processing (multiprocessing)
- Batch operations (process multiple docs)
- Early exit (skip if quality too low)
- Efficient data structures (sets for deduplication)

### 9.3 Training Performance

**Bottlenecks:**
1. GPU computation (if available)
2. Data loading (I/O)
3. Model size (memory)

**Optimizations:**
- Mixed precision (FP16)
- Gradient accumulation (larger effective batch)
- DataLoader workers (parallel loading)
- Pin memory (faster CPU→GPU transfer)

**GPU vs CPU:**
- GPU: 10-100x faster (depends on model)
- CPU: Works but very slow
- Recommendation: Use GPU for training

### 9.4 Memory Management

**Strategies:**
1. **Lazy Loading**: Load data on-demand
2. **Streaming**: Process in chunks
3. **Garbage Collection**: Explicit cleanup
4. **Memory Mapping**: Use mmap for large files

**Example (Lazy Loading):**
```python
class LazyParquetDataset(Dataset):
    def __init__(self, shard_dir):
        self.shard_files = list(Path(shard_dir).glob("*.parquet"))
        # Don't load data yet
    
    def __getitem__(self, idx):
        # Load shard on-demand
        shard_idx = idx // 1000
        shard_file = self.shard_files[shard_idx]
        table = pq.read_table(shard_file)
        return table[idx % 1000]  # Return specific row
```

---

## 10. Troubleshooting & Debugging

### 10.1 Common Issues

#### Issue: Crawler saves 0 pages
**Causes:**
- Rules not initialized before `super().__init__()`
- `parse_start_url` not implemented
- Domain restriction too strict

**Debug:**
```python
# Enable DEBUG logging
LOG_LEVEL = 'DEBUG'

# Check visited URLs
print(f"Visited: {len(spider.visited_urls)} URLs")

# Check rules
print(f"Rules: {spider.rules}")
```

#### Issue: Permission denied
**Cause**: Docker container user (UID 1000) can't write to host directories

**Fix:**
```bash
chown -R 1000:1000 dataset/ models/
chmod -R 775 dataset/ models/
```

#### Issue: Old data mixing with new
**Cause**: Files not deleted before new crawl

**Fix:**
```bash
# Remove entire directories
rm -rf dataset/raw dataset/cleaned dataset/shards

# Then create fresh
mkdir -p dataset/{raw,cleaned,shards/train,shards/val}
```

#### Issue: Training out of memory
**Causes:**
- Batch size too large
- Model too large for GPU
- Sequence length too long

**Fixes:**
```python
# Reduce batch size
batch_size = 1  # Instead of 4

# Use gradient accumulation
gradient_accumulation_steps = 8  # Effective batch = 8

# Reduce sequence length
max_length = 512  # Instead of 2048

# Use smaller model
model_name = "gpt2"  # Instead of "gpt2-large"
```

### 10.2 Debugging Tools

**Scrapy Shell:**
```bash
scrapy shell https://example.com
>>> response.css('title::text').get()
>>> response.xpath('//h1/text()').get()
```

**Python Debugger:**
```python
import pdb; pdb.set_trace()  # Breakpoint
```

**Logging:**
```python
import structlog
logger = structlog.get_logger()
logger.info("Debug info", key=value)
```

**Docker Logs:**
```bash
docker-compose logs crawler --tail 100
docker-compose logs processor --tail 100
docker-compose logs api --tail 100
```

### 10.3 Performance Profiling

**Python Profiler:**
```python
import cProfile
profiler = cProfile.Profile()
profiler.enable()
# Your code here
profiler.disable()
profiler.dump_stats('profile.stats')
```

**Memory Profiler:**
```python
from memory_profiler import profile

@profile
def my_function():
    # Your code here
```

**Time Profiling:**
```python
import time

start = time.perf_counter()
# Your code
elapsed = time.perf_counter() - start
print(f"Took {elapsed:.2f} seconds")
```

---

## 11. Advanced Topics

### 11.1 Distributed Training

**Multi-GPU Training:**
```python
# DataParallel (single machine, multiple GPUs)
model = torch.nn.DataParallel(model)

# DistributedDataParallel (multiple machines)
model = torch.nn.parallel.DistributedDataParallel(model)
```

**HuggingFace Accelerate:**
```bash
accelerate launch train.py
```

### 11.2 Model Quantization

**Purpose**: Reduce model size, faster inference

**Methods:**
1. **INT8 Quantization**: 4x smaller, minimal accuracy loss
2. **INT4 Quantization**: 8x smaller, some accuracy loss
3. **Dynamic Quantization**: Quantize on-the-fly
4. **Static Quantization**: Pre-quantize weights

**Example:**
```python
from transformers import AutoModelForCausalLM

model = AutoModelForCausalLM.from_pretrained("models/my_model")
quantized_model = torch.quantization.quantize_dynamic(
    model, {torch.nn.Linear}, dtype=torch.qint8
)
```

### 11.3 Fine-tuning Strategies

**Full Fine-tuning:**
- Update all model parameters
- Requires most memory
- Best quality

**LoRA (Low-Rank Adaptation):**
- Only train small adapter layers
- 10-100x less memory
- Nearly same quality

**Example (LoRA):**
```python
from peft import LoraConfig, get_peft_model

config = LoraConfig(
    r=16,  # Rank
    lora_alpha=32,
    target_modules=["q_proj", "v_proj"],
    lora_dropout=0.1,
)

model = get_peft_model(model, config)
# Now only adapter weights are trainable
```

### 11.4 Evaluation Metrics

**Perplexity:**
- Measures model's uncertainty
- Lower = better
- Formula: `exp(cross_entropy_loss)`

**BLEU Score:**
- Measures translation quality
- 0.0 to 1.0 (higher = better)
- Compares n-grams with reference

**ROUGE Score:**
- Measures summarization quality
- ROUGE-1, ROUGE-2, ROUGE-L
- Higher = better

---

## 12. Best Practices

### 12.1 Data Quality

1. **Filter early**: Remove low-quality data before tokenization
2. **Deduplicate**: Prevent model from memorizing duplicates
3. **Balance**: Ensure diverse content (not just one topic)
4. **Validate**: Check samples manually

### 12.2 Training

1. **Start small**: Test with small model/dataset first
2. **Monitor loss**: Watch for overfitting (train loss ↓, val loss ↑)
3. **Save checkpoints**: Don't lose progress
4. **Use validation**: Always validate on held-out data
5. **Early stopping**: Prevent overfitting

### 12.3 Infrastructure

1. **Backup data**: Version your datasets
2. **Monitor resources**: Watch CPU, memory, disk
3. **Log everything**: Debugging is easier with logs
4. **Test incrementally**: Test each component separately
5. **Document changes**: Keep track of what you changed

### 12.4 Security

1. **Sanitize inputs**: Validate URLs before crawling
2. **Rate limiting**: Don't overwhelm target servers
3. **Respect robots.txt**: Legal and ethical
4. **Secure credentials**: Don't commit API keys
5. **Container security**: Run as non-root user

---

## 13. Technical Deep Dives

### 13.1 How Scrapy Works Internally

**Event Loop (Twisted):**
```python
# Scrapy uses Twisted (async framework)
from twisted.internet import reactor

# Deferred (promise-like)
d = download_page(url)
d.addCallback(parse_response)
d.addErrback(handle_error)

reactor.run()  # Event loop
```

**Request Flow:**
1. Scheduler queues request
2. Downloader fetches page
3. Response sent to spider
4. Spider parses, yields items/requests
5. Items go to pipeline
6. New requests go back to scheduler

### 13.2 Transformer Architecture

**Self-Attention:**
```python
# Query, Key, Value
Q = X @ W_q  # [batch, seq, d_model]
K = X @ W_k
V = X @ W_v

# Attention scores
scores = Q @ K.T / sqrt(d_k)  # [batch, seq, seq]
attention = softmax(scores) @ V  # [batch, seq, d_model]
```

**Multi-Head Attention:**
- Split into multiple heads (e.g., 12 heads)
- Each head learns different patterns
- Concatenate outputs

**Feed-Forward:**
```python
ffn(x) = max(0, x @ W1 + b1) @ W2 + b2
# ReLU activation, two linear layers
```

### 13.3 Gradient Descent Math

**Loss Function:**
```
L(θ) = -log P(y|x; θ)  # Negative log likelihood
```

**Gradient:**
```
∇L(θ) = ∂L/∂θ  # Partial derivatives
```

**Update Rule (AdamW):**
```
m_t = β1 * m_{t-1} + (1-β1) * ∇L(θ_t)  # Momentum
v_t = β2 * v_{t-1} + (1-β2) * (∇L(θ_t))²  # Variance
θ_{t+1} = θ_t - α * (m_t / (√v_t + ε) + λ * θ_t)  # Update
```

**Learning Rate:**
- Too high: Overshoots minimum, unstable
- Too low: Slow convergence, might get stuck
- Optimal: Found via hyperparameter tuning

---

## 14. Production Deployment

### 14.1 Scaling

**Horizontal Scaling:**
- Add more crawler instances
- Add more processor workers
- Use load balancer

**Vertical Scaling:**
- Increase container memory
- Use larger GPU
- Faster CPU

### 14.2 Monitoring

**Metrics to Track:**
- Crawl rate (pages/minute)
- Processing throughput (docs/second)
- Training loss (should decrease)
- Memory usage
- Disk usage
- Error rates

**Tools:**
- Prometheus (metrics collection)
- Grafana (visualization)
- ELK Stack (log aggregation)

### 14.3 CI/CD

**Pipeline:**
```
1. Code commit
2. Run tests
3. Build Docker images
4. Deploy to staging
5. Run integration tests
6. Deploy to production
```

**Tools:**
- GitHub Actions
- GitLab CI
- Jenkins

---

## 15. Conclusion

This system provides a complete pipeline from web crawling to trained LLM:

1. **Crawling**: Professional web scraping with Scrapy
2. **Processing**: Quality filtering, deduplication, cleaning
3. **Tokenization**: Convert text to training-ready format
4. **Training**: Fine-tune language models on your data
5. **Deployment**: Use trained models in production

**Key Takeaways:**
- Each component is independently testable
- Data flows through clear stages
- Versioning enables reproducibility
- Docker ensures consistency
- Monitoring enables optimization

**Next Steps:**
- Experiment with different models
- Tune hyperparameters
- Scale to larger datasets
- Deploy to production
- Monitor and iterate

---

**End of Technical Deep Dive** 🚀

