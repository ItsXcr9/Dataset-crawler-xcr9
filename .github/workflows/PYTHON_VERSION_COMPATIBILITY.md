# Python Version Compatibility Fix

## Issue
Python 3.14.0 is not compatible with pandas 2.1.4. The error shows:
```
error: too few arguments to function '_PyLong_AsByteArray'
```

This is because pandas 2.1.4 was built before Python 3.14 existed and uses Python C API functions that have changed.

## Solution
Updated to **Python 3.12** which is:
- ✅ Stable and widely supported
- ✅ Compatible with all packages in requirements.txt
- ✅ Available in GitHub Actions
- ✅ Well-tested with pandas, numpy, and other scientific libraries

## Changes Made

### Python Version Updates
- **CI workflow**: Changed from `['3.14.0']` to `['3.12']`
- **Training workflow**: Changed from `'3.14.0'` to `'3.12'`
- **Nightly workflow**: Changed from `'3.14.0'` to `'3.12'`
- **Security workflow**: Changed from `'3.14.0'` to `'3.12'` (2 instances)

### Package Version Updates
- **pandas**: Changed from `==2.1.4` to `>=2.2.0` (better Python 3.12+ support)
- **numpy**: Changed from `==1.26.2` to `>=1.26.2` (allows newer compatible versions)

## Why Python 3.12?

1. **Stability**: Python 3.12 is a stable release with long-term support
2. **Compatibility**: All packages in requirements.txt work with Python 3.12
3. **Performance**: Python 3.12 has significant performance improvements
4. **Availability**: Available in GitHub Actions without issues
5. **Ecosystem**: Well-supported by the Python scientific computing ecosystem

## Alternative Versions

If you need a different version:
- **Python 3.11**: Very stable, excellent compatibility
- **Python 3.13**: Latest stable (if available in GitHub Actions)
- **Python 3.10**: Older but still supported

## Expected Result

After this fix:
- ✅ All Python packages will install successfully
- ✅ pandas will compile without C API errors
- ✅ All workflows will run with Python 3.12
- ✅ No compatibility issues with dependencies

## Note

Python 3.14.0 may not be available in GitHub Actions yet, or may be too new for many packages. Python 3.12 provides the best balance of:
- Modern features
- Package compatibility
- Stability
- Performance

