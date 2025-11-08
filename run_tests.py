#!/usr/bin/env python3
"""
Local test runner for Dataset Crawler CI/CD
Runs tests similar to GitHub Actions CI pipeline
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd, description, cwd=None):
    """Run a command and return success status"""
    print(f"\n{'='*60}")
    print(f"🔍 {description}")
    print('='*60)

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            print(f"✅ {description} - PASSED")
            if result.stdout:
                print(result.stdout[-500:])  # Last 500 chars of output
            return True
        else:
            print(f"❌ {description} - FAILED")
            print("STDOUT:", result.stdout[-1000:])
            print("STDERR:", result.stderr[-1000:])
            return False

    except subprocess.TimeoutExpired:
        print(f"⏰ {description} - TIMEOUT")
        return False
    except Exception as e:
        print(f"💥 {description} - ERROR: {e}")
        return False


def main():
    """Run all CI tests locally"""
    print("🚀 Dataset Crawler - Local CI Test Runner")
    print("="*60)

    # Change to project root
    project_root = Path(__file__).parent
    os.chdir(project_root)

    results = []

    # 1. Check Python imports
    results.append(run_command(
        "python -c \"import scrapy; print('Scrapy OK')\"",
        "Check Scrapy import"
    ))

    results.append(run_command(
        "python -c \"from transformers import AutoTokenizer; print('Transformers OK')\"",
        "Check Transformers import"
    ))

    results.append(run_command(
        "python -c \"import torch; print('PyTorch OK')\"",
        "Check PyTorch import"
    ))

    results.append(run_command(
        "python -c \"import datasets; print('Datasets OK')\"",
        "Check Datasets import"
    ))

    # 2. Run unit tests
    if Path("requirements-dev.txt").exists():
        results.append(run_command(
            "pip install -r requirements-dev.txt",
            "Install dev dependencies"
        ))

    results.append(run_command(
        "pytest tests/ -v --tb=short",
        "Run unit tests"
    ))

    # 3. Test crawler imports
    results.append(run_command(
        "cd crawler && python -c \"from crawler import DatasetCrawler; print('Crawler OK')\"",
        "Test crawler imports",
        cwd=project_root / "crawler"
    ))

    # 4. Test processor imports
    results.append(run_command(
        "cd processor && python -c \"from data_processor import DataProcessor; from tokenizer_sharder import TokenizerSharder; print('Processor OK')\"",
        "Test processor imports",
        cwd=project_root / "processor"
    ))

    # 5. Test trainer imports
    results.append(run_command(
        "cd trainer && python -c \"from model_trainer import ParquetDataset, train_model; print('Trainer OK')\"",
        "Test trainer imports",
        cwd=project_root / "trainer"
    ))

    # 6. Test API imports
    results.append(run_command(
        "cd api && python -c \"from main import app; print('API OK')\"",
        "Test API imports",
        cwd=project_root / "api"
    ))

    # 7. Test Docker builds (if Docker available)
    docker_available = run_command("docker --version", "Check Docker availability")
    if docker_available:
        results.append(run_command(
            "docker build -f docker/Dockerfile.crawler -t test-crawler .",
            "Build crawler Docker image"
        ))

        results.append(run_command(
            "docker build -f docker/Dockerfile.processor -t test-processor .",
            "Build processor Docker image"
        ))

        results.append(run_command(
            "docker build -f docker/Dockerfile.api -t test-api .",
            "Build API Docker image"
        ))

    # Summary
    print(f"\n{'='*60}")
    print("📊 TEST SUMMARY")
    print('='*60)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        return 0
    else:
        print("💥 SOME TESTS FAILED!")
        print("\nFailed tests:")
        for i, (result, description) in enumerate(zip(results, [
            "Scrapy import", "Transformers import", "PyTorch import", "Datasets import",
            "Dev dependencies", "Unit tests", "Crawler imports", "Processor imports",
            "Trainer imports", "API imports", "Docker check", "Crawler Docker",
            "Processor Docker", "API Docker"
        ])):
            if not result:
                print(f"  - {description}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
