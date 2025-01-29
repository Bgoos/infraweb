from datetime import datetime
from typing import List, Dict, Any
from ...models import db
from ...models.infra import Hosts, Clusters, VirtualMachines, Snapshots
from ..vcenter.collector import VCenterCollector
import logging

class DatabaseManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def update_hosts(self, hosts_data: List[Dict[str, Any]]) -> bool:
        """Update hosts table with new data"""
        try:
            # Clear existing data
            Hosts.query.delete()
            
            # Insert new data
            for host_data in hosts_data:
                host = Hosts(**host_data)
                db.session.add(host)
            
            db.session.commit()
            self.logger.info(f"Successfully updated {len(hosts_data)} hosts")
            return True
        except Exception as e:
            self.logger.error(f"Error updating hosts: {str(e)}")
            db.session.rollback()
            return False

    def update_clusters(self, clusters_data: List[Dict[str, Any]]) -> bool:
        """Update clusters table with new data"""
        try:
            Clusters.query.delete()
            
            for cluster_data in clusters_data:
                cluster = Clusters(**cluster_data)
                db.session.add(cluster)
            
            db.session.commit()
            self.logger.info(f"Successfully updated {len(clusters_data)} clusters")
            return True
        except Exception as e:
            self.logger.error(f"Error updating clusters: {str(e)}")
            db.session.rollback()
            return False

    def update_virtual_machines(self, vms_data: List[Dict[str, Any]]) -> bool:
        """Update virtual machines table with new data"""
        try:
            VirtualMachines.query.delete()
            
            for vm_data in vms_data:
                vm = VirtualMachines(**vm_data)
                db.session.add(vm)
            
            db.session.commit()
            self.logger.info(f"Successfully updated {len(vms_data)} virtual machines")
            return True
        except Exception as e:
            self.logger.error(f"Error updating virtual machines: {str(e)}")
            db.session.rollback()
            return False

    def update_snapshots(self, snapshots_data: List[Dict[str, Any]]) -> bool:
        """Update snapshots table with new data"""
        try:
            Snapshots.query.delete()
            
            for snapshot_data in snapshots_data:
                snapshot = Snapshots(**snapshot_data)
                db.session.add(snapshot)
            
            db.session.commit()
            self.logger.info(f"Successfully updated {len(snapshots_data)} snapshots")
            return True
        except Exception as e:
            self.logger.error(f"Error updating snapshots: {str(e)}")
            db.session.rollback()
            return False

    def perform_full_update(self, vcenter_data: Dict[str, List[Dict[str, Any]]]) -> bool:
        """Perform a full update of all tables"""
        try:
            # Start transaction
            db.session.begin()
            
            # Update each table
            success = all([
                self.update_hosts(vcenter_data.get('hosts_data', [])),
                self.update_clusters(vcenter_data.get('clusters_data', [])),
                self.update_virtual_machines(vcenter_data.get('vms_data', [])),
                self.update_snapshots(vcenter_data.get('snapshots_data', []))
            ])
            
            if success:
                db.session.commit()
                self.logger.info("Full database update completed successfully")
                return True
            else:
                raise Exception("One or more updates failed")
                
        except Exception as e:
            self.logger.error(f"Error during full update: {str(e)}")
            db.session.rollback()
            return False