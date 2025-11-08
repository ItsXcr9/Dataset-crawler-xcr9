# CI/CD Workflows

This directory contains GitHub Actions workflows for continuous integration and deployment of the Dataset Crawler to LLM Training Pipeline.

## Workflows Overview

### 🔄 CI (`ci.yml`)
**Triggers**: Push/PR to main/develop branches
**Purpose**: Comprehensive testing and validation
- Python unit tests (pytest)
- Code coverage reporting
- Docker image building
- Quick training validation
- Multi-Python version testing (3.9, 3.10, 3.11)

### 🏃 Training Tests (`training.yml`)
**Triggers**: Manual dispatch, Weekly schedule
**Purpose**: Validate model training pipeline
- Test training with different models (phi-2, DialoGPT, etc.)
- Synthetic dataset generation
- Training performance validation
- Model inference testing

### 🔗 Integration Tests (`integration.yml`)
**Triggers**: Manual dispatch, Weekly schedule
**Purpose**: End-to-end pipeline validation
- Full crawler → processor → trainer pipeline
- Database and service integration
- API endpoint testing
- Docker Compose orchestration testing

### 🔒 Security & Quality (`security.yml`)
**Triggers**: Push/PR to main/develop, Weekly schedule
**Purpose**: Security and code quality checks
- Vulnerability scanning (Trivy)
- Dependency security checks
- Code linting (flake8, black, isort)
- Type checking (mypy)
- Secrets detection

### 🌙 Nightly Tests (`nightly.yml`)
**Triggers**: Daily at 2 AM UTC, Manual dispatch
**Purpose**: Comprehensive nightly validation
- Extended training tests with multiple models
- Performance regression detection
- Large synthetic dataset testing
- Automated report generation

### 🚀 Release (`release.yml`)
**Triggers**: GitHub release creation, Manual dispatch
**Purpose**: Production deployment preparation
- Multi-platform Docker image building
- Container registry publishing
- Release artifact generation
- Build provenance attestation

## Usage

### Running Tests Manually

#### Quick CI Check
```bash
# Trigger CI workflow
gh workflow run ci
```

#### Training Validation
```bash
# Run training tests with specific model
gh workflow run training.yml -f model=microsoft/phi-2 -f epochs=1 -f batch_size=2
```

#### Full Integration Test
```bash
# Run complete pipeline integration test
gh workflow run integration
```

#### Security Scan
```bash
# Run security and quality checks
gh workflow run security
```

### Scheduled Workflows

- **Nightly Tests**: Run automatically every night at 2 AM UTC
- **Weekly Training Tests**: Run every Sunday at 3 AM UTC
- **Weekly Security Scans**: Run every Sunday at 1 AM UTC

### Release Process

1. Create a GitHub release with a version tag (e.g., `v1.0.0`)
2. The release workflow automatically:
   - Builds multi-platform Docker images
   - Pushes to GitHub Container Registry
   - Generates release artifacts
   - Updates Docker Compose file

## Workflow Artifacts

All workflows upload artifacts that can be downloaded:
- Test coverage reports
- Training logs and models
- Security scan results
- Performance metrics

## Configuration

### Required Secrets
- `GITHUB_TOKEN`: Automatically provided by GitHub

### Environment Variables
Most configuration is handled through workflow parameters and matrix builds.

### Customizing Workflows

#### Adding New Models to Training Tests
Edit `training.yml` and add to the `MODELS` associative array:

```yaml
declare -A MODELS
MODELS["11"]="new/model-name"
```

#### Modifying Test Datasets
Synthetic datasets are generated in workflows. To modify:
1. Update the Python generation code in workflow steps
2. Adjust sample counts and parameters as needed

#### Adding New Test Types
1. Create new test files in `tests/` directory
2. Add corresponding workflow steps
3. Update coverage requirements in `pytest.ini`

## Troubleshooting

### Common Issues

#### Docker Build Failures
- Check Docker build logs
- Verify base images are available
- Ensure build context doesn't include large files

#### Training Test Timeouts
- Increase timeout in workflow (default: 120 minutes)
- Reduce epochs or batch sizes for faster testing
- Use smaller models for CI validation

#### Memory Issues
- Training tests run on GitHub's standard runners (8GB RAM)
- Use smaller models or reduce batch sizes
- Consider using self-hosted runners for larger tests

### Debugging Failed Workflows

1. Check workflow logs in GitHub Actions tab
2. Download artifacts for detailed output
3. Run workflows locally using `act` (if using local development)
4. Check for dependency conflicts in requirements files

## Performance Considerations

### Resource Usage
- **CI**: ~10-15 minutes, moderate resource usage
- **Training Tests**: ~60-120 minutes, high CPU/memory usage
- **Integration Tests**: ~30-60 minutes, moderate resource usage
- **Security Scans**: ~5-10 minutes, low resource usage

### Cost Optimization
- Use matrix builds efficiently
- Cache Docker layers and pip dependencies
- Run heavy tests only when necessary
- Use scheduled workflows instead of every commit

## Contributing

When adding new features:

1. Add corresponding tests in `tests/` directory
2. Update workflows if new testing is required
3. Ensure CI passes before merging
4. Update this documentation

### Code Quality Gates

- **Test Coverage**: Minimum 80%
- **Linting**: No flake8 errors
- **Type Checking**: MyPy passes
- **Security**: No high/critical vulnerabilities
- **Docker**: All images build successfully
