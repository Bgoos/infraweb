import os
import sys
import shutil
import logging
from pathlib import Path
import importlib.metadata

def get_package_version(package_name: str) -> str:
    """Safely get package version"""
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "Not found"

def check_prerequisites():
    """Check and setup prerequisites for the application"""
    results = {
        'status': 'not_run',
        'checks': {},
        'actions_needed': []
    }

    # Check Python version
    python_version = sys.version_info
    results['checks']['python_version'] = {
        'status': 'pass' if python_version >= (3, 9) else 'fail',
        'version': f"{python_version.major}.{python_version.minor}.{python_version.micro}"
    }

    # Check required directories exist
    base_dir = Path(__file__).parent.parent
    required_dirs = [
        'app',
        'data',
        'logs',
        'scripts',
        'static',
        'templates'
    ]

    for dir_name in required_dirs:
        dir_path = base_dir / dir_name
        if not dir_path.exists():
            dir_path.mkdir(parents=True)
            results['actions_needed'].append(f"Created directory: {dir_name}")

    # Check credential script
    cred_script = base_dir / 'scripts' / 'credential_script.ps1'
    if not cred_script.exists():
        results['checks']['credential_script'] = {
            'status': 'fail',
            'error': 'credential_script.ps1 not found'
        }
        results['actions_needed'].append("Copy credential_script.ps1 to scripts directory")
    else:
        results['checks']['credential_script'] = {
            'status': 'pass',
            'path': str(cred_script)
        }

    # Check required packages
    required_packages = [
        'flask',
        'flask-sqlalchemy',
        'pyvmomi',
        'schedule',
        'requests'
    ]

    package_versions = {}
    missing_packages = []

    for package in required_packages:
        version = get_package_version(package)
        if version == "Not found":
            missing_packages.append(package)
        else:
            package_versions[package] = version

    if missing_packages:
        results['checks']['packages'] = {
            'status': 'fail',
            'error': f"Missing packages: {', '.join(missing_packages)}",
            'installed': package_versions
        }
        results['actions_needed'].append("Run: pip install -r requirements.txt")
    else:
        results['checks']['packages'] = {
            'status': 'pass',
            'installed': package_versions
        }

    # Check database file
    db_path = base_dir / 'data' / 'audit_reports.db'
    if not db_path.exists():
        results['checks']['database'] = {
            'status': 'warning',
            'message': 'Database file not found (will be created when app starts)'
        }
    else:
        results['checks']['database'] = {
            'status': 'pass',
            'path': str(db_path),
            'size': f"{db_path.stat().st_size / (1024*1024):.2f}MB"
        }

    # Overall status
    results['status'] = 'fail' if any(
        check['status'] == 'fail' 
        for check in results['checks'].values()
    ) else 'pass'

    return results

def main():
    results = check_prerequisites()
    
    print("\nPrerequisite Check Results:")
    print("=" * 50)
    
    for check_name, check_result in results['checks'].items():
        status = check_result['status']
        print(f"\n{check_name}:")
        print(f"  Status: {status.upper()}")
        
        if status == 'fail' and 'error' in check_result:
            print(f"  Error: {check_result['error']}")
        
        if 'version' in check_result:
            print(f"  Version: {check_result['version']}")
        
        if 'installed' in check_result:
            print("  Installed packages:")
            for pkg, ver in check_result['installed'].items():
                print(f"    - {pkg}: {ver}")
        
        if 'message' in check_result:
            print(f"  Message: {check_result['message']}")
        
        if 'path' in check_result:
            print(f"  Path: {check_result['path']}")

    if results['actions_needed']:
        print("\nActions needed:")
        for action in results['actions_needed']:
            print(f"- {action}")
    
    print(f"\nOverall Status: {results['status'].upper()}")

if __name__ == "__main__":
    main()