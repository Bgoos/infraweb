import os
import sys
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Any
import subprocess
from pathlib import Path

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.credentials import credentials_manager
from app.services.vcenter.collector import VCenterCollector
from app.utils.config import DATABASE_PATH, LOG_DIR, VCENTERS

class StartupTester:
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'tests': {},
            'overall_status': 'not_run'
        }
        self.setup_logging()

    def setup_logging(self):
        """Set up logging for tests"""
        log_file = os.path.join(LOG_DIR, 'startup_test.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def test_powershell_script(self) -> bool:
        """Test PowerShell credential script execution"""
        try:
            script_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'scripts',
                'credential_script.ps1'
            )
            
            # Test script existence
            if not os.path.exists(script_path):
                self.results['tests']['powershell_script'] = {
                    'status': 'fail',
                    'error': 'Credential script not found'
                }
                return False

            # Test script permissions
            try:
                # Run PowerShell Get-ExecutionPolicy
                result = subprocess.run(
                    ['powershell', 'Get-ExecutionPolicy'],
                    capture_output=True,
                    text=True
                )
                policy = result.stdout.strip()
                
                self.results['tests']['powershell_script'] = {
                    'status': 'pass',
                    'path': script_path,
                    'execution_policy': policy
                }
                return True
                
            except subprocess.CalledProcessError as e:
                self.results['tests']['powershell_script'] = {
                    'status': 'fail',
                    'error': f'PowerShell execution error: {str(e)}'
                }
                return False

        except Exception as e:
            self.results['tests']['powershell_script'] = {
                'status': 'fail',
                'error': str(e)
            }
            return False

    def test_database(self) -> bool:
        """Test database connection and structure"""
        try:
            if not os.path.exists(DATABASE_PATH):
                self.results['tests']['database'] = {
                    'status': 'fail',
                    'error': 'Database file not found'
                }
                return False

            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()

            # Check tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            
            # Get record counts and last update times
            table_stats = {}
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                
                # Try to get last update time if created/updated columns exist
                last_update = None
                cursor.execute(f"PRAGMA table_info({table})")
                columns = cursor.fetchall()
                date_columns = [col[1] for col in columns if 
                              any(term in col[1].lower() for term in 
                                  ['date', 'time', 'created', 'updated'])]
                
                if date_columns and count > 0:
                    cursor.execute(f"SELECT MAX({date_columns[0]}) FROM {table}")
                    last_update = cursor.fetchone()[0]
                
                table_stats[table] = {
                    'record_count': count,
                    'last_update': last_update
                }

            # Check database integrity
            cursor.execute("PRAGMA integrity_check")
            integrity = cursor.fetchone()[0]

            conn.close()

            self.results['tests']['database'] = {
                'status': 'pass' if integrity == 'ok' else 'fail',
                'integrity': integrity,
                'tables': table_stats,
                'size_mb': os.path.getsize(DATABASE_PATH) / (1024 * 1024)
            }
            return integrity == 'ok'

        except Exception as e:
            self.results['tests']['database'] = {
                'status': 'fail',
                'error': str(e)
            }
            return False

    def test_vcenter_config(self) -> bool:
        """Test vCenter configuration"""
        try:
            if not VCENTERS:
                self.results['tests']['vcenter_config'] = {
                    'status': 'fail',
                    'error': 'No vCenters configured'
                }
                return False

            vcenter_stats = {}
            for vcenter in VCENTERS:
                vcenter_stats[vcenter['host']] = {
                    'deploy_type': vcenter['DeployType'],
                    'host_format_valid': vcenter['host'].endswith('.csmodule.com'),
                    'deploy_type_valid': vcenter['DeployType'] in ['VCF', 'VVF']
                }

            self.results['tests']['vcenter_config'] = {
                'status': 'pass',
                'vcenter_count': len(VCENTERS),
                'vcenter_stats': vcenter_stats
            }
            return True

        except Exception as e:
            self.results['tests']['vcenter_config'] = {
                'status': 'fail',
                'error': str(e)
            }
            return False

    def run_all_tests(self):
        """Run all startup tests"""
        try:
            self.logger.info("Starting startup tests...")
            
            tests = [
                self.test_powershell_script,
                self.test_database,
                self.test_vcenter_config
            ]
            
            all_passed = True
            for test in tests:
                try:
                    test_name = test.__name__
                    self.logger.info(f"Running test: {test_name}")
                    passed = test()
                    all_passed = all_passed and passed
                    self.logger.info(f"Test {test_name}: {'PASSED' if passed else 'FAILED'}")
                except Exception as e:
                    self.logger.error(f"Error in {test.__name__}: {str(e)}")
                    all_passed = False

            self.results['overall_status'] = 'pass' if all_passed else 'fail'
            self.logger.info(f"All tests completed. Overall status: {self.results['overall_status']}")
            
            # Save results to file
            results_file = os.path.join(LOG_DIR, 'startup_test_results.log')
            with open(results_file, 'w') as f:
                import json
                json.dump(self.results, f, indent=2)
            
            return self.results

        except Exception as e:
            self.logger.error(f"Error running tests: {str(e)}")
            self.results['overall_status'] = 'error'
            self.results['error'] = str(e)
            return self.results

def main():
    tester = StartupTester()
    results = tester.run_all_tests()
    
    print("\nStartup Test Results:")
    print("=" * 50)
    
    for test_name, test_result in results['tests'].items():
        print(f"\n{test_name}:")
        print(f"  Status: {test_result['status'].upper()}")
        
        if test_result['status'] == 'fail' and 'error' in test_result:
            print(f"  Error: {test_result['error']}")
            
        if 'tables' in test_result:
            print("\n  Table Statistics:")
            for table, stats in test_result['tables'].items():
                print(f"    {table}:")
                print(f"      Records: {stats['record_count']}")
                if stats['last_update']:
                    print(f"      Last Update: {stats['last_update']}")
                    
        if 'vcenter_stats' in test_result:
            print("\n  vCenter Configuration:")
            for host, stats in test_result['vcenter_stats'].items():
                print(f"    {host}:")
                print(f"      Deploy Type: {stats['deploy_type']}")
                
    print(f"\nOverall Status: {results['overall_status'].upper()}")
    print(f"Detailed results saved to: {os.path.join(LOG_DIR, 'startup_test_results.log')}")

if __name__ == "__main__":
    main()