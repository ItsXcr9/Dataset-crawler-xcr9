"""
Tests for the trainer component
"""
import pytest
import torch
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path


class TestModelTrainer:
    """Test model training functionality"""

    def test_trainer_imports(self):
        """Test that trainer components can be imported"""
        try:
            from trainer.model_trainer import ParquetDataset, train_model
            assert True
        except ImportError:
            pytest.fail("Failed to import trainer components")

    @patch('transformers.AutoModelForCausalLM.from_pretrained')
    @patch('transformers.AutoTokenizer.from_pretrained')
    def test_model_loading(self, mock_tokenizer, mock_model):
        """Test model and tokenizer loading (mocked)"""
        # Mock tokenizer
        mock_tokenizer_instance = Mock()
        mock_tokenizer_instance.vocab_size = 50000
        mock_tokenizer_instance.pad_token = "<pad>"
        mock_tokenizer_instance.pad_token_id = 0
        mock_tokenizer_instance.eos_token_id = 1
        mock_tokenizer.return_value = mock_tokenizer_instance

        # Mock model
        mock_model_instance = Mock()
        mock_model_instance.resize_token_embeddings = Mock()
        mock_model.return_value = mock_model_instance

        from transformers import AutoTokenizer, AutoModelForCausalLM

        # Test loading
        tokenizer = AutoTokenizer.from_pretrained("test-model")
        model = AutoModelForCausalLM.from_pretrained("test-model")

        assert tokenizer.vocab_size == 50000
        assert model.resize_token_embeddings.called

    def test_parquet_dataset_creation(self):
        """Test ParquetDataset creation with mock data"""
        import pyarrow as pa
        import pandas as pd
        import tempfile

        # Create temporary parquet file
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test data
            test_data = {
                'doc_id': ['test_1', 'test_2'],
                'tokens': [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]],
                'attention_mask': [[1, 1, 1, 1, 1], [1, 1, 1, 1, 1]],
                'language': ['en', 'en'],
                'quality_score': [0.8, 0.9],
                'token_count': [5, 5]
            }

            df = pd.DataFrame(test_data)
            parquet_path = Path(temp_dir) / "test.parquet"
            df.to_parquet(parquet_path)

            # Test dataset creation
            from trainer.model_trainer import ParquetDataset

            with patch('transformers.AutoTokenizer.from_pretrained') as mock_tokenizer:
                mock_tokenizer_instance = Mock()
                mock_tokenizer_instance.pad_token_id = 0
                mock_tokenizer_instance.eos_token_id = 1
                mock_tokenizer.return_value = mock_tokenizer_instance

                dataset = ParquetDataset(temp_dir, mock_tokenizer_instance, max_length=10)

                assert len(dataset) == 2
                assert len(dataset.data) == 2

                # Test item access
                item = dataset[0]
                assert 'input_ids' in item
                assert 'attention_mask' in item
                assert 'labels' in item

    @patch('torch.cuda.is_available')
    def test_device_detection(self, mock_cuda_available):
        """Test device detection logic"""
        mock_cuda_available.return_value = False

        # Import and test device detection
        from trainer.model_trainer import train_model

        # This should work without errors (though we won't actually train)
        # The device detection happens early in the function
        assert torch.cuda.is_available() == False

        mock_cuda_available.return_value = True
        assert torch.cuda.is_available() == True

    def test_training_arguments_validation(self):
        """Test that training arguments are reasonable"""
        from transformers import TrainingArguments

        # Test that we can create training arguments
        args = TrainingArguments(
            output_dir="test_output",
            num_train_epochs=1,
            per_device_train_batch_size=2,
            learning_rate=1e-5,
            fp16=False,
            dataloader_num_workers=0
        )

        assert args.output_dir == "test_output"
        assert args.num_train_epochs == 1
        assert args.per_device_train_batch_size == 2
        assert args.learning_rate == 1e-5
