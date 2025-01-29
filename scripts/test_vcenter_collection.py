import os
import sys
import logging
import time
from datetime import datetime
from typing import Dict, List, Any
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.infra import db, VCenterInfo, AffinityRule
from app.services.credentials import credentials_manager
from app.services.vcenter.collector import VCenterCollector
from app.utils.config import VCENTERS

# Define test vCenters
vcenter_list = [vc for vc in VCENTERS if vc['host'] in [
    'cr3-vcenter-11.csmodule.com',
    'std-vcenter-11.cydmodule.com'
]]

def setup_logging():
    """Set up logging configuration"""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'vcenter_test.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def update_vcenter_database(vcenter_data: Dict) -> bool:
    """Update database with collected vCenter data"""
    app = create_app()
    with app.app_context():
        try:
            # Clear existing vCenter data
            db.session.query(VCenterInfo).delete()
            
            # Update vCenter info
            logging.info("Updating vCenter information...")
            for vcenter_info in vcenter_data.get('vcenter_info', []):
                # Get SSL certificate info from certificates list
                ssl_cert = next((cert for cert in vcenter_info.get('certificates', []) 
                               if cert['type'] == 'SSL Certificate'), {})
                
                # Parse datetime strings to datetime objects
                ssl_expiration = None
                if ssl_cert.get('expiration'):
                    try:
                        # Handle ISO format dates
                        if 'T' in ssl_cert['expiration']:
                            ssl_expiration = datetime.strptime(
                                ssl_cert['expiration'].split('.')[0],
                                '%Y-%m-%dT%H:%M:%S'
                            )
                            logging.info(f"Parsed SSL expiration: {ssl_expiration}")
                    except Exception as e:
                        logging.error(f"Error parsing SSL expiration: {e}")

                vcenter = VCenterInfo(
                    hostname=vcenter_info['hostname'],
                    version=vcenter_info['version'],
                    build_number=vcenter_info['build_number'],
                    deploy_type=vcenter_info['deploy_type'],
                    # Health metrics
                    storage_health_status=vcenter_info.get('storage_health_status', 'Unknown'),
                    disk_health_status=vcenter_info.get('disk_health_status', 'Unknown'),
                    storage_capacity_used=vcenter_info.get('storage_capacity_used', 0),
                    network_status=vcenter_info.get('network_status', 'Unknown'),
                    network_details=vcenter_info.get('network_details', 'Not collected'),
                    vsan_health_status=vcenter_info.get('vsan_health_status', 'Unknown'),
                    vsan_disk_status=vcenter_info.get('vsan_disk_status', 'Unknown'),
                    vsan_network_status=vcenter_info.get('vsan_network_status', 'Unknown'),
                    avg_latency=vcenter_info.get('avg_latency', 0),
                    cpu_overcommitment=vcenter_info.get('cpu_overcommitment', 0),
                    memory_overcommitment=vcenter_info.get('memory_overcommitment', 0),
                    storage_overcommitment=vcenter_info.get('storage_overcommitment', 0),
                    drs_status=vcenter_info.get('drs_status', 'Unknown'),
                    drs_balance=vcenter_info.get('drs_balance', 'Unknown'),
                    ha_status=vcenter_info.get('ha_status', 'None'),
                    # Status fields
                    last_checked=datetime.utcnow(),
                    status=vcenter_info.get('status', 'connected'),
                    error_message=vcenter_info.get('error_message')
                )
                db.session.add(vcenter)
                logging.info(f"Added vCenter info for {vcenter_info['hostname']}")

            db.session.commit()
            logging.info("Database update completed successfully")
            return True
            
        except Exception as e:
            logging.error(f"Error during database update: {str(e)}")
            db.session.rollback()
            return False

def test_vcenter_collection():
    """Test vCenter data collection process"""
    logger = setup_logging()
    results = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'stages': {},
        'metrics': {}
    }
    
    try:
        start_time = time.time()
        
        # Get credentials
        logger.info("Getting credentials...")
        credentials = credentials_manager.get_credentials()
        cred_time = time.time() - start_time
        
        # Collect vCenter data
        logger.info("Collecting vCenter data...")
        collector = VCenterCollector(credentials)
        collection_start = time.time()
                
        all_data = {
            'hosts_data': [],
            'clusters_data': [],
            'vms_data': [],
            'snapshots_data': [],
            'vcenter_info': [],
            'affinity_rules': []
        }

        with ThreadPoolExecutor(max_workers=len(vcenter_list)) as executor:
            future_to_vcenter = {
                executor.submit(collector.collect_data_from_vcenter, vcenter): vcenter 
                for vcenter in vcenter_list
            }
            
            for future in as_completed(future_to_vcenter):
                vcenter = future_to_vcenter[future]
                try:
                    data = future.result()
                    for key in all_data:
                        all_data[key].extend(data.get(key, []))
                except Exception as e:
                    logger.error(f"Error processing {vcenter['host']}: {str(e)}")
                    continue

        collection_time = time.time() - collection_start
        
        # Update database
        logger.info("Updating database...")
        db_start = time.time()
        update_success = update_vcenter_database(all_data)
        db_time = time.time() - db_start
        
        # Calculate metrics
        total_time = time.time() - start_time
        results['metrics'] = {
            'total_duration_seconds': round(total_time, 2),
            'credential_time': round(cred_time, 2),
            'collection_time': round(collection_time, 2),
            'database_time': round(db_time, 2)
        }
        
        # Print results
        print("\nvCenter Collection Test Results:")
        print("=" * 50)
        print(f"Timestamp: {results['timestamp']}")
        
        print("\nvCenter Information:")
        for vc in all_data.get('vcenter_info', []):
            print(f"\n{vc['hostname']}:")
            print(f"  Version: {vc['version']}")
            print(f"  Status: {vc['status']}")
            print(f"  License Type: {vc.get('license_type', 'None')}")
            print(f"  HA Status: {vc.get('ha_status', 'None')}")
            print("  Certificates:")
            for cert in vc.get('certificates', []):
                print(f"    Type: {cert['type']}")
                print(f"    Expiration: {cert.get('expiration')}")
                print(f"    Issuer: {cert.get('issuer')}")
                print(f"    Subject: {cert.get('subject')}")
            print(f"  Certificate Mode: {vc.get('cert_mode')}")
        
        print("\nPerformance Metrics:")
        print("-" * 30)
        for key, value in results['metrics'].items():
            print(f"{key.replace('_', ' ').title()}: {value} seconds")
        
        logger.info("Collection test completed successfully")
        return results
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        return None

if __name__ == "__main__":
    print("Starting vCenter collection test...")
    print(f"Testing with vCenters: {[vc['host'] for vc in vcenter_list]}")
    test_vcenter_collection()