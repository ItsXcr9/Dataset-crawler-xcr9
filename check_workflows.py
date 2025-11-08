#!/usr/bin/env python3
"""
Check GitHub Actions workflows before pushing to GitHub
"""

import os
import sys
from pathlib import Path

def check_workflow_files():
    """Check if all workflow files exist and are valid"""
    workflow_dir = Path('.github/workflows')
    
    if not workflow_dir.exists():
        print("❌ .github/workflows directory not found!")
        return False
    
    expected_workflows = [
        'ci.yml',
        'training.yml', 
        'integration.yml',
        'security.yml',
        'nightly.yml',
        'release.yml'
    ]
    
    missing = []
    for workflow in expected_workflows:
        if not (workflow_dir / workflow).exists():
            missing.append(workflow)
    
    if missing:
        print(f"❌ Missing workflow files: {', '.join(missing)}")
        return False
    
    print("✅ All workflow files present")
    return True

def check_yaml_syntax():
    """Basic YAML syntax check"""
    try:
        import yaml
        workflow_dir = Path('.github/workflows')
        issues = []

        for yml_file in workflow_dir.glob('*.yml'):
            try:
                with open(yml_file, 'r') as f:
                    yaml.safe_load(f)
            except yaml.YAMLError as e:
                issues.append(f"{yml_file.name}: YAML parsing error - {str(e)[:100]}")
            except Exception as e:
                issues.append(f"{yml_file.name}: Error reading file - {e}")

        if issues:
            print("❌ YAML syntax issues found:")
            for issue in issues[:5]:  # Show first 5
                print(f"   {issue}")
            return False

        print("✅ All YAML files are syntactically valid")
        return True

    except ImportError:
        # Fallback check without PyYAML
        workflow_dir = Path('.github/workflows')
        issues = []

        for yml_file in workflow_dir.glob('*.yml'):
            try:
                with open(yml_file, 'r') as f:
                    content = f.read()

                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    # Check for tabs (YAML doesn't like tabs)
                    if '\t' in line:
                        issues.append(f"{yml_file.name}:{i}: Contains tabs (use spaces)")

            except Exception as e:
                issues.append(f"{yml_file.name}: Error reading file - {e}")

        if issues:
            print("❌ Basic YAML issues found:")
            for issue in issues[:5]:  # Show first 5
                print(f"   {issue}")
            return False

        print("✅ Basic YAML syntax check passed (PyYAML not available for full validation)")
        return True

def check_required_files():
    """Check for files referenced in workflows"""
    required_files = [
        'requirements.txt',
        'pytest.ini',
        'tests/__init__.py',
        'tests/test_crawler.py',
        'tests/test_processor.py', 
        'tests/test_trainer.py',
        'run_tests.py'
    ]
    
    missing = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing.append(file_path)
    
    if missing:
        print(f"⚠️  Missing files referenced in workflows: {', '.join(missing)}")
        print("   These will cause workflow failures but won't prevent running")
        return True  # Not a blocking issue
    
    print("✅ All workflow-referenced files present")
    return True

def check_docker_files():
    """Check Docker-related files"""
    docker_files = [
        'docker/Dockerfile.crawler',
        'docker/Dockerfile.processor',
        'docker/Dockerfile.api',
        'docker/Dockerfile.webui',
        'docker-compose.yml'
    ]
    
    missing = []
    for file_path in docker_files:
        if not Path(file_path).exists():
            missing.append(file_path)
    
    if missing:
        print(f"⚠️  Missing Docker files: {', '.join(missing)}")
        print("   Docker-related workflows will fail")
        return False
    
    print("✅ Docker files present")
    return True

def main():
    """Run all checks"""
    print("🔍 Checking GitHub Actions workflows setup...\n")
    
    checks = [
        check_workflow_files,
        check_yaml_syntax,
        check_required_files,
        check_docker_files
    ]
    
    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as e:
            print(f"❌ Error running {check.__name__}: {e}")
            results.append(False)
    
    print(f"\n📊 Summary: {sum(results)}/{len(results)} checks passed")
    
    if all(results):
        print("🎉 All checks passed! Ready to push to GitHub.")
        print("\nNext steps:")
        print("1. git add .")
        print("2. git commit -m 'Add CI/CD workflows'")
        print("3. git push origin main")
        print("4. Go to Actions tab to monitor workflows")
        return 0
    else:
        print("❌ Some checks failed. Please fix issues before pushing.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
