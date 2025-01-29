import os
import sys
import logging
import time
from datetime import datetime
from typing import Dict, List, Any
import json

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.infra import (db, Hosts, Clusters, VirtualMachines, 
                            Snapshots, UpdateStats, VCenterInfo, AffinityRule)
from app.services.credentials import credentials_manager
from app.services.vcenter.collector import VCenterCollector
from app.utils.config import DATABASE_PATH, LOG_DIR, VCENTERS

def setup_logging():
    """Set up logging configuration"""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'collection_test.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def update_database(vcenter_data: Dict, total_collection_time: float) -> bool:
    """Update database with collected data"""
    app = create_app()
    with app.app_context():
        try:
            # Clear existing data
            db.session.query(Hosts).delete()
            db.session.query(Clusters).delete()
            db.session.query(VirtualMachines).delete()
            db.session.query(Snapshots).delete()
            db.session.query(VCenterInfo).delete()
            db.session.query(AffinityRule).delete()
            
            # Update hosts
            logging.info("Updating hosts...")
            for host_data in vcenter_data['hosts_data']:
                host = Hosts(
                    Host=host_data['Host'],
                    Datacenter=host_data['Datacenter'],
                    Cluster=host_data['Cluster'],
                    NumCPU=host_data['NumCPU'],
                    NumCores=host_data['NumCores'],
                    CPUUsagePercentage=host_data['CPUUsagePercentage'],
                    Mem=host_data['Mem'],
                    MemoryUsagePercentage=host_data['MemoryUsagePercentage'],
                    TotalVMs=host_data['TotalVMs'],
                    DNS=host_data['DNS'],
                    NTP=host_data['NTP'],
                    IP=host_data['IP'],
                    MAC=host_data['MAC'],
                    PowerPolicy=host_data['PowerPolicy'],
                    Vendor=host_data['Vendor'],
                    Model=host_data['Model'],
                    ServiceTag=host_data['ServiceTag']
                )
                db.session.add(host)

            # Update clusters
            logging.info("Updating clusters...")
            for cluster_data in vcenter_data['clusters_data']:
                # First, get cluster name from either format
                cluster_name = cluster_data.get('ClusterName', cluster_data.get('name', 'Unknown'))
                logging.debug(f"Processing cluster: {cluster_name}")
                
                cluster = Clusters(
                    ClusterName=cluster_name,
                    CPUUtilization=cluster_data.get('CPUUtilization', cluster_data.get('cpu_utilization', 0)),
                    MemoryUtilization=cluster_data.get('MemoryUtilization', cluster_data.get('memory_utilization', 0)),
                    StorageUtilization=cluster_data.get('StorageUtilization', cluster_data.get('storage_utilization', 0)),
                    vSANEnabled=cluster_data.get('vSANEnabled', cluster_data.get('vsan_enabled', False)),
                    vSANCapacityTiB=cluster_data.get('vSANCapacityTiB', cluster_data.get('vsan_capacity', 0)),
                    vSANUsedTiB=cluster_data.get('vSANUsedTiB', cluster_data.get('used_storage', 0)),
                    vSANFreeTiB=cluster_data.get('vSANFreeTiB', cluster_data.get('vsan_free', 0)),
                    vSANUtilization=cluster_data.get('vSANUtilization', cluster_data.get('vsan_utilization', 0)),
                    NumHosts=len(cluster_data.get('hosts', [])),
                    NumCPUSockets=sum(host.get('NumCPU', 0) for host in cluster_data.get('hosts', [])),
                    NumCPUCores=sum(host.get('NumCores', 0) for host in cluster_data.get('hosts', [])),
                    FoundationLicenseCoreCount=cluster_data.get('FoundationLicenseCoreCount', 0),
                    EntitledVSANLicenseTiBCount=cluster_data.get('EntitledVSANLicenseTiBCount', 0),
                    RequiredVSANTiBCapacity=cluster_data.get('RequiredVSANTiBCapacity', 0),
                    VSANLicenseTiBCount=cluster_data.get('VSANLicenseTiBCount', 0),
                    RequiredVVFComputeLicenses=cluster_data.get('RequiredVVFComputeLicenses', 0),
                    RequiredVSANAddOnLicenses=cluster_data.get('RequiredVSANAddOnLicenses', 0),
                    DeployType=cluster_data.get('DeployType', cluster_data.get('deploy_type', 'Unknown'))
                )
                db.session.add(cluster)

            # Update VMs
            logging.info("Updating virtual machines...")
            for vm_data in vcenter_data['vms_data']:
                vm = VirtualMachines(
                    VMName=vm_data['VMName'],
                    OS=vm_data['OS'],
                    Site=vm_data['Site'],
                    State=vm_data['State'],
                    Created=vm_data['Created'],
                    SizeGB=vm_data['SizeGB'],
                    InUseGB=vm_data['InUseGB'],
                    IP=vm_data['IP'],
                    NICType=vm_data['NICType'],
                    VMTools=vm_data['VMTools'],
                    VMVersion=vm_data['VMVersion'],
                    Host=vm_data['Host'],
                    Cluster=vm_data['Cluster'],
                    Notes=vm_data.get('Notes', '')
                )
                db.session.add(vm)

            # Update snapshots
            logging.info("Updating snapshots...")
            for snapshot_data in vcenter_data['snapshots_data']:
                snapshot = Snapshots(
                    vm_id=snapshot_data['vm_id'],
                    vm_name=snapshot_data['vm_name'],
                    snapshot=snapshot_data['snapshot'],
                    created=snapshot_data['created']
                )
                db.session.add(snapshot)
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
                    # Health monitoring fields
                    storage_health_status=vcenter_info.get('storage_health_status', 'Unknown'),
                    disk_health_status=vcenter_info.get('disk_health_status', 'Unknown'),
                    storage_capacity_used=vcenter_info.get('storage_capacity_used', 0),
                    network_status=vcenter_info.get('network_status', 'Unknown'),
                    network_details=vcenter_info.get('network_details', 'Not collected'),
                    vsan_health_status=vcenter_info.get('vsan_health_status', 'Unknown'),
                    vsan_disk_status=vcenter_info.get('vsan_disk_status', 'Unknown'),
                    vsan_network_status=vcenter_info.get('vsan_network_status', 'Unknown'),
                    drs_status=vcenter_info.get('drs_status', 'Unknown'),
                    drs_balance=vcenter_info.get('drs_balance', 'Unknown'),
                    ha_status=vcenter_info.get('ha_status', 'None'),
                    # Certificate fields
                    ssl_certificate_expiration=ssl_expiration,
                    ssl_issuer=ssl_cert.get('issuer'),
                    ssl_subject=ssl_cert.get('subject'),
                    # Status fields
                    last_checked=datetime.utcnow(),
                    status=vcenter_info.get('status', 'connected'),
                    error_message=vcenter_info.get('error_message')
                )
                db.session.add(vcenter)
                logging.info(f"Added vCenter info for {vcenter_info['hostname']}")

            # Update affinity rules
            logging.info("Updating affinity rules...")
            for rule_data in vcenter_data.get('affinity_rules', []):
                rule = AffinityRule(
                    vcenter=rule_data['vcenter'],
                    rule_name=rule_data['rule_name'],
                    rule_type=rule_data['rule_type'],
                    enabled=rule_data['enabled'],
                    cluster=rule_data['cluster'],
                    vms=rule_data.get('vms', ''),
                    hosts=rule_data.get('hosts', ''),
                    mandatory=rule_data.get('mandatory', False),
                    description=rule_data.get('description', ''),
                    last_checked=datetime.utcnow()
                )
                db.session.add(rule)

            db.session.commit()
            
            # Update statistics
            previous_stats = UpdateStats.query.order_by(UpdateStats.id.desc()).first()
            count = (previous_stats.total_count + 1) if previous_stats else 1
            
            stats = UpdateStats(
                last_run=datetime.utcnow(),
                duration=round(total_collection_time, 2),
                total_count=count
            )
            db.session.add(stats)
            db.session.commit()
            
            logging.info(f"Update stats saved - Duration: {total_collection_time:.2f}s, Count: {count}")
            return True
            
        except Exception as e:
            logging.error(f"Error during database update: {str(e)}")
            db.session.rollback()
            return False

def test_collection():
    """Test the full data collection process with metrics"""
    logger = setup_logging()
    results = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'stages': {},
        'metrics': {},
        'vcenter_stats': {}
    }
    
    try:
        global start_time
        start_time = time.time()
        
        # 1. Test Credentials
        logger.info("Testing credential retrieval...")
        credentials = credentials_manager.get_credentials()
        cred_time = time.time() - start_time
        results['stages']['credentials'] = {
            'status': 'pass',
            'duration_seconds': round(cred_time, 2)
        }
        
        # 2. Test vCenter Collection
        logger.info("Testing vCenter data collection...")
        collector = VCenterCollector(credentials)
        collection_start = time.time()
        vcenter_data = collector.collect_from_all_vcenters()
        total_collection_time = time.time() - collection_start
        
        # Calculate statistics
        total_stats = {
            'hosts': len(vcenter_data['hosts_data']),
            'clusters': len(vcenter_data['clusters_data']),
            'vms': len(vcenter_data['vms_data']),
            'snapshots': len(vcenter_data['snapshots_data']),
            'vcenters': len(vcenter_data.get('vcenter_info', [])),
            'affinity_rules': len(vcenter_data.get('affinity_rules', []))
        }
        
        results['stages']['collection'] = {
            'status': 'pass',
            'duration_seconds': round(total_collection_time, 2),
            'total_stats': total_stats,
            'collection_rate': round(total_stats['vms'] / total_collection_time, 2),
            'vcenters_processed': len(VCENTERS)
        }
        
        # 3. Test Database Update
        logger.info("Testing database update...")
        db_start = time.time()
        update_success = update_database(vcenter_data, total_collection_time)
        db_time = time.time() - db_start
        
        results['stages']['database_update'] = {
            'status': 'pass' if update_success else 'fail',
            'duration_seconds': round(db_time, 2),
            'write_rate': round(total_stats['vms'] / db_time, 2) if db_time > 0 else 0
        }
        
        # Calculate overall metrics
        total_time = time.time() - start_time
        results['metrics'] = {
            'total_duration_seconds': round(total_time, 2),
            'average_collection_rate': round(total_stats['vms'] / total_time, 2),
            'credential_overhead_percentage': round((cred_time / total_time) * 100, 2),
            'collection_percentage': round((total_collection_time / total_time) * 100, 2),
            'database_percentage': round((db_time / total_time) * 100, 2)
        }
        
        # Print results
        print("\nCollection Test Results:")
        print("=" * 50)
        print(f"Timestamp: {results['timestamp']}")
        
        print("\nData Statistics:")
        print("-" * 30)
        for key, value in total_stats.items():
            print(f"{key.capitalize()}: {value}")
        
        print("\nPerformance Metrics:")
        print("-" * 30)
        for key, value in results['metrics'].items():
            print(f"{key.replace('_', ' ').title()}: {value}")
        
        print("\nStage Details:")
        print("-" * 30)
        for stage, data in results['stages'].items():
            print(f"\n{stage.upper()}:")
            for key, value in data.items():
                print(f"  {key}: {value}")
        
        logger.info(f"Collection completed successfully - Processed {total_stats['vms']} VMs in {total_time:.2f} seconds")
        
        return results
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        return None

if __name__ == "__main__":
    test_collection()