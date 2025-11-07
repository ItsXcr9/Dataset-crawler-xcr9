#!/usr/bin/env python3
"""
Test script for trained models
Loads a trained model and generates sample text
"""

import argparse
import sys
from pathlib import Path

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
except ImportError:
    print("Error: transformers and torch are required")
    print("Install with: pip install transformers torch")
    sys.exit(1)


def test_model(model_path: str, prompt: str = "What is", max_length: int = 50):
    """Test a trained model with a prompt"""
    
    print(f"Loading model from: {model_path}")
    
    # Check if model exists
    if not Path(model_path).exists():
        print(f"Error: Model directory not found: {model_path}")
        return False
    
    try:
        # Load tokenizer
        print("Loading tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        
        # Load model
        print("Loading model...")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {device}")
        
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            trust_remote_code=True,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map="auto" if device == "cuda" else None
        )
        
        # Tokenize input
        print(f"\nPrompt: '{prompt}'")
        inputs = tokenizer(prompt, return_tensors="pt")
        
        if device == "cuda":
            inputs = {k: v.to(device) for k, v in inputs.items()}
        
        # Generate
        print("Generating text...")
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_length=max_length,
                num_return_sequences=1,
                temperature=0.7,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id
            )
        
        # Decode output
        generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        print(f"\n{'='*60}")
        print("Generated Text:")
        print(f"{'='*60}")
        print(generated_text)
        print(f"{'='*60}\n")
        
        # Show training info if available
        info_file = Path(model_path) / "training_info.json"
        if info_file.exists():
            import json
            with open(info_file) as f:
                info = json.load(f)
            print("Training Information:")
            print(f"  Base Model: {info.get('base_model', 'N/A')}")
            print(f"  Trained At: {info.get('trained_at', 'N/A')}")
            print(f"  Epochs: {info.get('epochs', 'N/A')}")
            print(f"  Training Samples: {info.get('train_samples', 'N/A')}")
            print(f"  Final Loss: {info.get('final_loss', 'N/A')}")
            print()
        
        return True
        
    except Exception as e:
        print(f"Error testing model: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Test a trained model")
    parser.add_argument("model_path", help="Path to trained model directory")
    parser.add_argument("--prompt", default="What is", help="Test prompt (default: 'What is')")
    parser.add_argument("--max_length", type=int, default=100, help="Maximum generation length")
    
    args = parser.parse_args()
    
    success = test_model(args.model_path, args.prompt, args.max_length)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

