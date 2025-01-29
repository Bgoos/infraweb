#!/usr/bin/env python3
import os
import sys
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
import ssl
from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect
import re
import time
import urllib3
import requests

# Disable SSL warnings for internal vCenter connections
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Add the parent directory to the Python path for imports
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from app import create_app
from app.services.credentials import credentials_manager
from app.models.infra import db, WindowsVMs, VirtualMachines
from app.utils.config import VCENTERS, LOG_DIR

class WindowsVMCollector:
    def __init__(self):
        self.setup_logging()
        self.credentials = None
        self.stats = {
            'total_windows_vms': 0,
            'powered_on_vms': 0,
            'successful_collections': 0,
            'failed_collections': 0,
            'vm_not_found': 0,
            'vcenter_errors': Counter()
        }

    def setup_logging(self):
        """Set up logging configuration"""
        log_file = os.path.join(LOG_DIR, 'windows_vm_collection.log')
        os.makedirs(LOG_DIR, exist_ok=True)

        self.logger = logging.getLogger('WindowsVMCollector')
        self.logger.setLevel(logging.INFO)

        # Clear existing handlers
        self.logger.handlers = []

        # File handler with rotation
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10485760, backupCount=5)
        
        # Console handler
        console_handler = logging.StreamHandler()

        # Create formatter and add it to handlers
        log_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(log_format)
        console_handler.setFormatter(log_format)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def get_windows_vms(self) -> list:
        """Get Windows VMs from the virtual_machines table"""
        try:
            print("Querying database for Windows VMs...")
            # Get all Windows VMs first
            all_windows_vms = VirtualMachines.query.filter(
                VirtualMachines.OS.ilike('%windows%')
            ).all()
            
            self.stats['total_windows_vms'] = len(all_windows_vms)
            print(f"Found {self.stats['total_windows_vms']} total Windows VMs")

            # Filter for powered on VMs
            windows_vms = [vm for vm in all_windows_vms if vm.State == 'poweredOn']
            self.stats['powered_on_vms'] = len(windows_vms)
            print(f"Found {self.stats['powered_on_vms']} powered on Windows VMs")
            
            vm_data = []
            for vm in windows_vms:
                # Clean up NIC type format
                nic_types = []
                if vm.NICType:
                    for nic in vm.NICType.split(','):
                        nic = nic.strip()
                        if 'vim.vm.device.' in nic:
                            nic = nic.replace('vim.vm.device.', '')
                        nic_types.append(nic)
                
                # Match API field names exactly
                vm_info = {
                    'VMName': vm.VMName,
                    'OS': vm.OS,
                    'Site': vm.Site,
                    'State': vm.State,
                    'SizeGB': vm.SizeGB,
                    'InUseGB': vm.InUseGB,
                    'IP': vm.IP,
                    'NICType': ','.join(nic_types) if nic_types else '',
                    'VMTools': vm.VMTools,
                    'VMVersion': vm.VMVersion,
                    'Host': vm.Host,
                    'Cluster': vm.Cluster,
                    'Notes': vm.Notes
                }
                vm_data.append(vm_info)

            return vm_data
        except Exception as e:
            self.logger.error(f"Error fetching Windows VMs: {e}")
            print(f"Error fetching Windows VMs: {e}")
            return []

    def group_by_vcenter(self, vms: list) -> dict:
        """Group VMs by their vCenter"""
        print("\nGrouping VMs by vCenter...")
        vcenter_groups = {}
        for vm in vms:
            vcenter = self._extract_vcenter_from_cluster(vm['Cluster'])
            if vcenter:
                vcenter_groups.setdefault(vcenter, []).append(vm)
        
        for vcenter, vm_list in vcenter_groups.items():
            print(f"- {vcenter}: {len(vm_list)} VMs")
        
        return vcenter_groups

    def _extract_vcenter_from_cluster(self, cluster: str) -> str:
        """Extract vCenter hostname from cluster name"""
        if not cluster:
            return None
        try:
            site_prefix = cluster.split('-')[0].lower()
            vcenter = next(
                (vc['host'] for vc in VCENTERS 
                 if vc['host'].startswith(site_prefix)),
                None
            )
            return vcenter
        except Exception as e:
            self.logger.error(f"Error extracting vCenter from cluster {cluster}: {e}")
            return None

    def collect_vm_data(self, vcenter: str, vms: list) -> list:
        """Collect Windows-specific data from VMs"""
        print(f"\nConnecting to vCenter: {vcenter}")
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS)
            context.verify_mode = ssl.CERT_NONE
            si = SmartConnect(
                host=vcenter,
                user=self.credentials['vcenter']['username'],
                pwd=self.credentials['vcenter']['password'],
                sslContext=context
            )
            content = si.RetrieveContent()
            print(f"Connected to {vcenter}")

            results = []
            print(f"Processing {len(vms)} VMs...")
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_vm = {
                    executor.submit(
                        self._process_single_vm, content, vm
                    ): vm for vm in vms
                }
                
                completed = 0
                for future in as_completed(future_to_vm):
                    vm = future_to_vm[future]
                    try:
                        data = future.result()
                        if data:
                            results.append(data)
                            self.stats['successful_collections'] += 1
                        else:
                            self.stats['failed_collections'] += 1
                        
                        # Progress indicator
                        completed += 1
                        print(f"\rProgress: {completed}/{len(vms)} VMs processed", end='', flush=True)
                            
                    except Exception as e:
                        self.stats['failed_collections'] += 1
                        self.logger.error(f"Error processing VM {vm['VMName']}: {e}")

            print("\n")  # New line after progress indicator
            Disconnect(si)
            return results

        except Exception as e:
            self.stats['vcenter_errors'][str(e)] += 1
            self.logger.error(f"Error connecting to vCenter {vcenter}: {e}")
            return []

    def _process_single_vm(self, content, vm_info: dict) -> dict:
        """Process a single VM to get Windows-specific information"""
        try:
            vm = self._find_vm_by_name(content, vm_info['VMName'])
            if not vm:
                self.stats['vm_not_found'] += 1
                return None

            creds = vim.vm.guest.NamePasswordAuthentication(
                username=self.credentials['windows']['username'],
                password=self.credentials['windows']['password']
            )

            pm = content.guestOperationsManager.processManager
            fm = content.guestOperationsManager.fileManager

            # Define commands to run
            commands = [
                # OS Version
                ('systeminfo | findstr "OS Name:" > C:\\Windows\\Temp\\os_ver.txt', 'os_ver.txt', "OS Version"),
                # Cortex Service Status
                ('sc query cyserver > C:\\Windows\\Temp\\cortex.txt', 'cortex.txt', "Cortex Status"),
                # VR Service Status
                ('sc query vrevo > C:\\Windows\\Temp\\vr.txt', 'vr.txt', "VR Status"),
                # Update Target Group
                ('reg query "HKLM\\Software\\Policies\\Microsoft\\Windows\\WindowsUpdate" /v TargetGroup > C:\\Windows\\Temp\\update.txt', 'update.txt', "Update Settings"),
                # SSL/TLS Settings
                ('reg query "HKLM\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\SCHANNEL\\Protocols\\SSL 3.0\\Client" /v Enabled > C:\\Windows\\Temp\\ssl.txt', 'ssl.txt', "SSL Settings"),
                ('reg query "HKLM\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\SCHANNEL\\Protocols\\TLS 1.1\\Client" /v Enabled > C:\\Windows\\Temp\\tls.txt', 'tls.txt', "TLS Settings")
            ]

            results = {}
            
            for cmd, output_file, description in commands:
                try:
                    # Execute command
                    spec = vim.vm.guest.ProcessManager.ProgramSpec(
                        programPath="C:\\Windows\\System32\\cmd.exe",
                        arguments=f"/c {cmd}"
                    )
                    pid = pm.StartProgram(vm=vm, auth=creds, spec=spec)
                    time.sleep(1)  # Wait for command to complete

                    # Read output
                    try:
                        file_transfer = fm.InitiateFileTransferFromGuest(
                            vm=vm,
                            auth=creds,
                            guestFilePath=f"C:\\Windows\\Temp\\{output_file}"
                        )
                        
                        if file_transfer:
                            response = requests.get(file_transfer.url, verify=False)
                            results[description] = response.text.strip()
                    
                    except vim.fault.FileNotFound:
                        results[description] = None
                        
                except Exception as e:
                    self.logger.error(f"Command failed for {vm_info['VMName']}: {e}")
                    results[description] = None

            # Parse results
            try:
                # Extract OS name
                os_name = None
                if results.get("OS Version"):
                    os_match = re.search(r"OS Name:\s*(.*)", results["OS Version"])
                    if os_match:
                        os_name = os_match.group(1).strip()

                # Parse service statuses
                cortex_running = False
                if results.get("Cortex Status"):
                    # Clean and normalize the text for consistent checking
                    status_text = ' '.join(results["Cortex Status"].replace('\n', ' ').split())
                    if "STATE" in status_text and "4" in status_text and "RUNNING" in status_text:
                        cortex_running = True
                        self.logger.debug(f"Cortex running for {vm_info['VMName']}")
                    self.logger.debug(f"Cortex raw status: {results['Cortex Status']}")

                vr_running = False
                if results.get("VR Status"):
                    # Clean and normalize the text for consistent checking
                    status_text = ' '.join(results["VR Status"].replace('\n', ' ').split())
                    if "STATE" in status_text and "4" in status_text and "RUNNING" in status_text:
                        vr_running = True
                        self.logger.debug(f"VR running for {vm_info['VMName']}")
                    self.logger.debug(f"VR raw status: {results['VR Status']}")

                # Parse update target group
                update_tg = None
                if results.get("Update Settings"):
                    tg_match = re.search(r"TargetGroup\s+REG_SZ\s+(.*)", results["Update Settings"])
                    if tg_match:
                        update_tg = tg_match.group(1).strip()

                # Parse SSL/TLS settings
                ssl_disabled = False
                tls_disabled = False
                if results.get("SSL Settings"):
                    ssl_disabled = "0x0" in results["SSL Settings"]
                if results.get("TLS Settings"):
                    tls_disabled = "0x0" in results["TLS Settings"]

                # Cleanup temporary files
                cleanup_spec = vim.vm.guest.ProcessManager.ProgramSpec(
                    programPath="C:\\Windows\\System32\\cmd.exe",
                    arguments="/c del /F /Q C:\\Windows\\Temp\\*.txt"
                )
                pm.StartProgram(vm=vm, auth=creds, spec=cleanup_spec)

                # Return collected data
                return {
                    'VMName': vm_info['VMName'],
                    'OS': os_name or vm_info['OS'],
                    'Site': vm_info['Site'],
                    'State': vm_info['State'],
                    'Size': vm_info['SizeGB'],
                    'IP': vm_info['IP'],
                    'NICType': vm_info['NICType'],
                    'VMToolsVersion': vm_info['VMTools'],
                    'VMHardwareVersion': vm_info['VMVersion'],
                    'Cortex': cortex_running,
                    'CortexVersion': None,  # We don't get version from sc query
                    'VR': vr_running,
                    'UpdateTG': update_tg,
                    'Ciphers': ssl_disabled and tls_disabled,
                    'Notes': vm_info['Notes']
                }

            except Exception as e:
                self.logger.error(f"Error parsing results for {vm_info['VMName']}: {e}")
                return None

        except Exception as e:
            self.logger.error(f"Error processing VM {vm_info['VMName']}: {str(e)}")
            return None

    def _find_vm_by_name(self, content, vm_name: str) -> vim.VirtualMachine:
        """Find VM object by name"""
        container = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.VirtualMachine], True
        )
        for vm in container.view:
            if vm.name == vm_name:
                return vm
        return None

    def update_database(self, vm_data: list) -> bool:
        """Update database with collected VM data"""
        try:
            print(f"\nUpdating database with {len(vm_data)} VMs...")
            WindowsVMs.query.delete()
            
            for data in vm_data:
                vm = WindowsVMs(
                    VMName=data['VMName'],
                    OS=data['OS'],
                    Site=data['Site'],
                    State=data['State'],
                    Size=data['Size'],
                    IP=data['IP'],
                    NICType=data['NICType'],
                    VMToolsVersion=data['VMToolsVersion'],
                    VMHardwareVersion=data['VMHardwareVersion'],
                    Cortex=data['Cortex'],
                    CortexVersion=data['CortexVersion'],
                    VR=data['VR'],
                    UpdateTG=data['UpdateTG'],
                    Ciphers=data['Ciphers'],
                    Notes=data['Notes']
                )
                db.session.add(vm)
            
            db.session.commit()
            print("Database update completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating database: {e}")
            print(f"Error updating database: {e}")
            db.session.rollback()
            return False

    def print_stats(self):
        """Print collection statistics"""
        print("\n=== Collection Statistics ===")
        print("-" * 50)
        print(f"Total Windows VMs found: {self.stats['total_windows_vms']}")
        print(f"Powered on VMs: {self.stats['powered_on_vms']}")
        print(f"Successful collections: {self.stats['successful_collections']}")
        print(f"Failed collections: {self.stats['failed_collections']}")
        print(f"VMs not found: {self.stats['vm_not_found']}")
        
        if self.stats['vcenter_errors']:
            print("\nvCenter Errors:")
            for error, count in self.stats['vcenter_errors'].items():
                print(f"  {error}: {count}")

def main():
    """Main execution function"""
    start_time = datetime.now()
    print("\n=== Starting Windows VM Collection ===")
    print(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    app = create_app()
    
    with app.app_context():
        collector = WindowsVMCollector()
        print("Initializing collector...")
        
        try:
            print("Getting credentials...")
            collector.credentials = credentials_manager.get_credentials()
            
            print("Fetching Windows VMs from database...")
            windows_vms = collector.get_windows_vms()
            if not windows_vms:
                print("No Windows VMs found!")
                return
            
            print("\nGrouping VMs by vCenter...")
            vcenter_groups = collector.group_by_vcenter(windows_vms)
            
            print("\nProcessing VMs by vCenter:")
            all_vm_data = []
            for vcenter, vms in vcenter_groups.items():
                print(f"- {vcenter}: Processing {len(vms)} VMs...")
                vm_data = collector.collect_vm_data(vcenter, vms)
                all_vm_data.extend(vm_data)
            
            if all_vm_data:
                print(f"\nUpdating database with {len(all_vm_data)} VMs...")
                collector.update_database(all_vm_data)
            else:
                print("\nNo VM data collected. Database not updated.")
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            print(f"\nCollection completed in {duration:.2f} seconds")
            print(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            collector.print_stats()
            
        except Exception as e:
            print(f"\nERROR: {str(e)}")
            collector.logger.error(f"Error in main execution: {e}")
            raise

if __name__ == "__main__":
    main()