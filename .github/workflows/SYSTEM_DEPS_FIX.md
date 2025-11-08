# System Dependencies Fix for lxml Build

## Issue
`lxml` package requires system-level development libraries to build from source:
- `libxml2-dev` - XML parsing library
- `libxslt1-dev` - XSLT transformation library
- `libffi-dev` - Foreign Function Interface library
- `libssl-dev` - SSL/TLS library
- `build-essential` - Compiler toolchain (gcc, make, etc.)
- `python3-dev` - Python development headers

## Error Message
```
Error: Please make sure the libxml2 and libxslt development packages are installed.
ERROR: Failed to build 'lxml' when getting requirements to build wheel
```

## Solution Applied

Added system dependency installation step **before** Python setup in all workflows that install Python packages:

### Workflows Updated:
1. **CI workflow** (`ci.yml`) - test job
2. **Security workflow** (`security.yml`) - code-quality and dependency-check jobs

### Installation Command:
```yaml
- name: Install system dependencies
  run: |
    sudo apt-get update
    sudo apt-get install -y \
      libxml2-dev \
      libxslt1-dev \
      libffi-dev \
      libssl-dev \
      build-essential \
      python3-dev
```

## Why This Is Needed

- **lxml**: Requires libxml2 and libxslt development headers to compile C extensions
- **cryptography**: Requires libffi-dev and libssl-dev for secure operations
- **Other packages**: May require build-essential for compiling C extensions
- **Python packages**: Need python3-dev for building native extensions

## Expected Result

After this fix:
- ✅ lxml will build successfully
- ✅ All Python packages will install without build errors
- ✅ Dependencies will be available for all workflows

## Note

These system packages are only needed for building Python packages from source. Once installed, they remain available for the entire workflow run.

