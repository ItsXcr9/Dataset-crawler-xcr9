# Model Training Guide

## Quick Start

### 1. Select Dataset Version and Model

Run the interactive training script:

```bash
./train_model.sh
```

The script will:
1. **List all available dataset versions** (from `dataset_backups/` and current `dataset/`)
2. **Ask you to select a version** (e.g., test_v1, xcr9_full_v3, etc.)
3. **Show available models** (Llama, Qwen, Mistral, etc.)
4. **Ask you to select a model**
5. **Configure training parameters** (epochs, batch size, learning rate)
6. **Start training**

### 2. Example Session

```bash
$ ./train_model.sh

============================================
  DATASET VERSION SELECTION
============================================

Available Dataset Versions:
  1. Current dataset (dataset/shards/)
  2. test_v1 (dataset_backups/test_v1/)
  3. xcr9_full_v3 (dataset_backups/xcr9_full_v3/)
  ...

Select dataset version (1-12): 2
Selected dataset: test_v1

============================================
  MODEL TRAINING SETUP
============================================

Available Models:
  1. Llama 2 7B
  2. Llama 2 13B
  3. Llama 3 8B
  4. Qwen2 7B
  5. Qwen2 7B Instruct
  6. Qwen2.5 7B
  7. Phi-2 (small, fast for testing)
  8. Mistral 7B
  9. Gemma 7B
  10. Custom model

Select model (1-10): 7
Selected model: microsoft/phi-2

Number of epochs (default: 3): 1
Batch size (default: 4): 2
Learning rate (default: 2e-5): 2e-5
Output model name (default: test_v1_phi-2): test_v1_phi2_quick

Training Configuration:
  Dataset: test_v1
  Model: microsoft/phi-2
  Epochs: 1
  Batch Size: 2
  Learning Rate: 2e-5
  Output: models/test_v1_phi2_quick

Start training? (y/N): y
```

### 3. Test Your Trained Model

After training completes, test the model:

```bash
# Test with default prompt
python3 test_model.py models/test_v1_phi2_quick

# Test with custom prompt
python3 test_model.py models/test_v1_phi2_quick --prompt "What is Kubernetes?" --max_length 100
```

Or from Docker:

```bash
docker-compose exec processor python3 /app/test_model.py models/test_v1_phi2_quick --prompt "What is" --max_length 50
```

## Available Models

| # | Model | Size | Speed | Use Case |
|---|-------|------|-------|----------|
| 1 | Llama 2 7B | 7B | Medium | General purpose |
| 2 | Llama 2 13B | 13B | Slow | Better quality |
| 3 | Llama 3 8B | 8B | Medium | Latest Llama |
| 4 | Qwen2 7B | 7B | Medium | Multilingual |
| 5 | Qwen2 7B Instruct | 7B | Medium | Instruction following |
| 6 | Qwen2.5 7B | 7B | Medium | Latest Qwen |
| 7 | **Phi-2** | **2.7B** | **Fast** | **Quick testing** |
| 8 | Mistral 7B | 7B | Medium | High quality |
| 9 | Gemma 7B | 7B | Medium | Google's model |
| 10 | Custom | Varies | Varies | Any HuggingFace model |

**Recommendation for testing:** Use Phi-2 (#7) - it's small and fast, perfect for quick tests.

## Training Parameters

- **Epochs**: How many times to train on the entire dataset
  - Quick test: 1 epoch
  - Normal: 3 epochs
  - Thorough: 5-10 epochs

- **Batch Size**: Number of samples per training step
  - Small GPU (8GB): 1-2
  - Medium GPU (16GB): 4-8
  - Large GPU (24GB+): 8-16

- **Learning Rate**: How fast the model learns
  - Default: 2e-5 (0.00002)
  - Lower (1e-5): Slower, more stable
  - Higher (5e-5): Faster, may be unstable

## Using Trained Models

### Python

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

# Load your trained model
model = AutoModelForCausalLM.from_pretrained("models/test_v1_phi2_quick")
tokenizer = AutoTokenizer.from_pretrained("models/test_v1_phi2_quick")

# Generate text
prompt = "What is Kubernetes?"
inputs = tokenizer(prompt, return_tensors="pt")
outputs = model.generate(**inputs, max_length=100, temperature=0.7)
print(tokenizer.decode(outputs[0]))
```

### Command Line

```bash
python3 test_model.py models/test_v1_phi2_quick --prompt "Your question here"
```

## File Locations

- **Trained Models**: `models/<model_name>/`
- **Dataset Versions**: `dataset_backups/<version_name>/shards/`
- **Current Dataset**: `dataset/shards/`
- **Training Logs**: Check Docker logs: `docker-compose logs processor`

## Troubleshooting

### Out of Memory

- Reduce batch size (try 1 or 2)
- Use a smaller model (Phi-2 instead of Llama)
- Reduce max_length in training

### Training Too Slow

- Use GPU if available (automatically detected)
- Use smaller model for testing
- Reduce number of epochs for quick tests

### Model Not Generating Good Text

- Train for more epochs (3-5)
- Use larger model
- Check dataset quality
- Adjust learning rate

## Quick Test Script

For a quick test with Phi-2 on test_v1 dataset:

```bash
./quick_train_test.sh
```

This will:
1. Train Phi-2 on test_v1 dataset (1 epoch, small batch)
2. Test the trained model automatically
3. Show generated text

## Next Steps

1. **Train on your dataset**: Use `./train_model.sh` to select your dataset version
2. **Test the model**: Use `test_model.py` to verify it works
3. **Use in production**: Load the model in your application
4. **Iterate**: Train again with different parameters to improve

