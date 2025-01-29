import ssl
import socket
import requests
from typing import Dict, List, Any
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3
from ...utils.config import VCENTERS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class VCenterCollector:
    def __init__(self, credentials: Dict[str, str]):
        self.logger = logging.getLogger(__name__)
        self.credentials = credentials
        self._context = self._create_ssl_context()
        self.session_ids = {}

    def _create_ssl_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        context.verify_mode = ssl.CERT_NONE
        return context

    def _get_session_id(self, hostname: str) -> str:
        if hostname in self.session_ids:
            return self.session_ids[hostname]
            
        try:
            url = f"https://{hostname}/api/session"
            auth = (self.credentials['vcenter']['username'], 
                   self.credentials['vcenter']['password'])
            
            response = requests.post(url, auth=auth, verify=False)
            if response.ok:
                session_id = response.json()
                self.session_ids[hostname] = session_id
                self.logger.info(f"Successfully got session ID for {hostname}")
                return session_id
            else:
                self.logger.error(f"Failed to get session ID: {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"Error getting session ID for {hostname}: {str(e)}")
            return None

    def connect_vcenter(self, host: str) -> vim.ServiceInstance:
        try:
            si = SmartConnect(
                host=host,
                user=self.credentials['vcenter']['username'],
                pwd=self.credentials['vcenter']['password'],
                sslContext=self._context
            )
            self.logger.info(f"Successfully connected to vCenter: {host}")
            return si
        except Exception as e:
            self.logger.error(f"Failed to connect to vCenter {host}: {str(e)}")
            raise
    def collect_from_all_vcenters(self) -> Dict[str, List[Dict[str, Any]]]:
        all_data = {
            'hosts_data': [],
            'clusters_data': [],
            'vms_data': [],
            'snapshots_data': [],
            'vcenter_info': [],
            'affinity_rules': []
        }
        
        with ThreadPoolExecutor(max_workers=len(VCENTERS)) as executor:
            future_to_vcenter = {
                executor.submit(self.collect_data_from_vcenter, vcenter): vcenter 
                for vcenter in VCENTERS
            }
            
            for future in as_completed(future_to_vcenter):
                vcenter = future_to_vcenter[future]
                try:
                    data = future.result()
                    for key in all_data:
                        all_data[key].extend(data.get(key, []))
                except Exception as e:
                    self.logger.error(f"Error processing {vcenter['host']}: {str(e)}")
                    continue
        
        return all_data

    def _get_certificate_info(self, content: vim.ServiceInstance.RetrieveContent, hostname: str) -> Dict[str, Any]:
        try:
            cert_results = []
            session_id = self._get_session_id(hostname)
            
            if session_id:
                headers = {'vmware-api-session-id': session_id}
                
                # Get TLS certificate info
                tls_url = f"https://{hostname}/api/vcenter/certificate-management/vcenter/tls"
                try:
                    tls_response = requests.get(tls_url, headers=headers, verify=False)
                    if tls_response.ok:
                        tls_info = tls_response.json()
                        cert_results.append({
                            'type': 'SSL Certificate',
                            'expiration': tls_info.get('valid_to'),
                            'issuer': tls_info.get('issuer_dn'),
                            'subject': tls_info.get('subject_dn')
                        })
                        self.logger.info(f"Got TLS certificate info for {hostname}")
                except Exception as tls_e:
                    self.logger.error(f"Error getting TLS certificate: {tls_e}")

                # Get signing certificate info
                signing_url = f"https://{hostname}/api/vcenter/certificate-management/vcenter/signing-certificate"
                try:
                    signing_response = requests.get(signing_url, headers=headers, verify=False)
                    if signing_response.ok:
                        signing_info = signing_response.json()
                        if signing_info.get('active_cert_chain'):
                            cert_results.append({
                                'type': 'VMCA',
                                'expiration': signing_info['active_cert_chain'].get('valid_to'),
                                'issuer': signing_info['active_cert_chain'].get('issuer_dn'),
                                'subject': signing_info['active_cert_chain'].get('subject_dn')
                            })
                        self.logger.info(f"Got signing certificate info for {hostname}")
                except Exception as signing_e:
                    self.logger.error(f"Error getting signing certificate: {signing_e}")

            return {
                'certificates': cert_results,
                'mode': 'custom'
            }
                
        except Exception as e:
            self.logger.error(f"Error getting certificate info for {hostname}: {str(e)}")
            return {
                'certificates': [],
                'mode': None
            }
            
    def collect_data_from_vcenter(self, vcenter: Dict[str, str]) -> Dict[str, List[Dict[str, Any]]]:
        try:
            si = self.connect_vcenter(vcenter['host'])
            content = si.RetrieveContent()
            
            hosts_data = []
            clusters_data = []
            vms_data = []
            snapshots_data = []
            affinity_rules = []
            
            # Collect vCenter info with certificates
            vcenter_info = self._process_vcenter_info(content, vcenter)
            
            for datacenter in content.rootFolder.childEntity:
                self.logger.info(f"Processing datacenter: {datacenter.name}")
                
                for cluster in datacenter.hostFolder.childEntity:
                    # Process cluster
                    cluster_info = self._process_cluster(cluster, datacenter.name, vcenter['DeployType'])
                    clusters_data.append(cluster_info)
                    
                    # Process hosts in cluster
                    for host in cluster.host:
                        host_info = self._process_host(host, datacenter.name, cluster.name)
                        hosts_data.append(host_info)
                        
                        # Process VMs on host
                        for vm in host.vm:
                            vm_info = self._process_vm(vm, datacenter.name, cluster.name, host.name)
                            vms_data.append(vm_info)
                            
                            # Process snapshots
                            if vm.snapshot:
                                for snap in vm.snapshot.rootSnapshotList:
                                    snap_info = self._process_snapshot(snap, vm)
                                    snapshots_data.append(snap_info)
                    
                    # Collect affinity rules
                    cluster_rules = self._process_affinity_rules(cluster, vcenter['host'])
                    affinity_rules.extend(cluster_rules)
            
            Disconnect(si)
            return {
                'hosts_data': hosts_data,
                'clusters_data': clusters_data,
                'vms_data': vms_data,
                'snapshots_data': snapshots_data,
                'vcenter_info': [vcenter_info],
                'affinity_rules': affinity_rules
            }
            
        except Exception as e:
            self.logger.error(f"Error collecting data from {vcenter['host']}: {str(e)}")
            raise
    def _get_vsan_health(self, cluster: vim.ClusterComputeResource) -> Dict[str, Any]:
        try:
            if not cluster.configurationEx.vsanConfigInfo.enabled:
                return {'status': 'Disabled', 'disk_status': 'N/A', 'network_status': 'N/A'}

            disk_issues = 0
            network_issues = 0
            
            for host in cluster.host:
                if hasattr(host.configManager, 'vsanSystem') and host.configManager.vsanSystem:
                    system = host.configManager.vsanSystem
                    if not system.config.enabled:
                        network_issues += 1

            status = 'Healthy' if not (disk_issues or network_issues) else 'Warning'
                    
            return {
                'status': status,
                'disk_status': 'Warning' if disk_issues > 0 else 'Normal',
                'network_status': 'Warning' if network_issues > 0 else 'Normal'
            }
        except Exception as e:
            self.logger.error(f"vSAN health check failed: {str(e)}")
            return {'status': 'Unknown', 'disk_status': 'Unknown', 'network_status': 'Unknown'}

    def _calculate_overcommitment(self, cluster: vim.ClusterComputeResource) -> Dict[str, float]:
        try:
            total_cpu = sum(h.hardware.cpuInfo.numCpuCores * h.hardware.cpuInfo.hz for h in cluster.host)
            total_memory = sum(h.hardware.memorySize for h in cluster.host)
            total_storage = sum(d.summary.capacity for d in cluster.datastore)
            
            allocated_cpu = 0
            allocated_memory = 0
            allocated_storage = 0
            
            for vm in cluster.resourcePool.vm:
                if vm.config:
                    allocated_cpu += vm.config.hardware.numCPU * vm.config.hardware.cpuMhz  # Fixed CPU calculation
                    allocated_memory += vm.config.hardware.memoryMB * 1024 * 1024
                    allocated_storage += sum(device.capacityInBytes for device in vm.config.hardware.device 
                                          if isinstance(device, vim.vm.device.VirtualDisk))
            
            return {
                'cpu': round((allocated_cpu / total_cpu * 100) if total_cpu > 0 else 0, 2),
                'memory': round((allocated_memory / total_memory * 100) if total_memory > 0 else 0, 2),
                'storage': round((allocated_storage / total_storage * 100) if total_storage > 0 else 0, 2)
            }
        except Exception as e:
            self.logger.error(f"Error calculating overcommitment: {str(e)}")
            return {'cpu': 0, 'memory': 0, 'storage': 0}

    def _get_drs_status(self, cluster: vim.ClusterComputeResource) -> Dict[str, str]:
        try:
            if not cluster.configuration.drsConfig.enabled:
                return {'status': 'Disabled', 'balance': 'N/A'}
                
            migration_threshold = cluster.configuration.drsConfig.vmotionRate
            status = 'Conservative' if migration_threshold == 1 else 'Aggressive' if migration_threshold == 5 else 'Active'
            
            host_loads = [h.summary.quickStats.overallCpuUsage for h in cluster.host if h.summary.quickStats.overallCpuUsage is not None]
            
            if host_loads:
                avg = sum(host_loads) / len(host_loads)
                deviation = sum(abs(load - avg) for load in host_loads) / len(host_loads)
                balance = 'Optimal' if deviation < 10 else 'Good' if deviation < 20 else 'Fair' if deviation < 30 else 'Poor'
            else:
                balance = 'Unknown'
                
            return {'status': status, 'balance': balance}
        except Exception as e:
            self.logger.error(f"DRS status check failed: {str(e)}")
            return {'status': 'Unknown', 'balance': 'Unknown'}

    def _get_ha_status(self, cluster: vim.ClusterComputeResource) -> str:
        try:
            if hasattr(cluster.configuration, 'dasConfig'):
                das_config = cluster.configuration.dasConfig
                if das_config.enabled:
                    if not das_config.hostMonitoring:
                        return "Partially Enabled"
                    elif das_config.admissionControlEnabled:
                        return "Fully Enabled"
                    else:
                        return "Enabled (No Admission Control)"
                return "Disabled"
            return "Unknown"
        except Exception as e:
            self.logger.error(f"HA status check failed: {str(e)}")
            return "Unknown"

    def _get_average_latency(self, cluster: vim.ClusterComputeResource) -> float:
        try:
            latencies = []
            for host in cluster.host:
                for datastore in host.datastore:
                    if hasattr(datastore.summary, 'stats'):
                        stats = datastore.summary.stats
                        if hasattr(stats, 'maxReadLatency') and stats.maxReadLatency is not None:
                            latencies.append(stats.maxReadLatency)
                        if hasattr(stats, 'maxWriteLatency') and stats.maxWriteLatency is not None:
                            latencies.append(stats.maxWriteLatency)
            
            return round(sum(latencies) / len(latencies), 2) if latencies else 0
        except Exception as e:
            self.logger.error(f"Latency calculation failed: {str(e)}")
            return 0

    def _get_storage_health(self, datacenter: vim.Datacenter) -> Dict[str, Any]:
        try:
            issues = []
            total_capacity = 0
            total_used = 0
            
            for datastore in datacenter.datastore:
                if hasattr(datastore.summary, 'capacity'):
                    total_capacity += datastore.summary.capacity or 0
                    free_space = datastore.summary.freeSpace or 0
                    used = datastore.summary.capacity - free_space
                    total_used += used
                    
                    if not datastore.summary.accessible:
                        issues.append(f"{datastore.name} inaccessible")
                    elif used / datastore.summary.capacity > 0.9:
                        issues.append(f"{datastore.name} >90% full")

            capacity_used = (total_used / total_capacity * 100) if total_capacity > 0 else 0
            status = 'Critical' if any('inaccessible' in i for i in issues) else 'Warning' if issues else 'Healthy'
            
            return {
                'status': status,
                'capacity_used': round(capacity_used, 2),
                'disk_health': 'Critical' if status == 'Critical' else 'Warning' if status == 'Warning' else 'Normal'
            }
        except Exception as e:
            self.logger.error(f"Storage health check failed: {str(e)}")
            return {'status': 'Unknown', 'capacity_used': 0, 'disk_health': 'Unknown'}

    def _get_network_status(self, host: vim.HostSystem) -> Dict[str, Any]:
        try:
            up_nics = []
            down_nics = []
            for pnic in host.config.network.pnic:
                if pnic.linkSpeed:
                    up_nics.append(pnic.device)
                else:
                    down_nics.append(pnic.device)
                    
            if down_nics:
                status = 'Critical' if not up_nics else 'Warning'
                details = f"{len(up_nics)} NICs up, {len(down_nics)} NICs down" 
            else:
                status = 'Normal'
                details = f"All {len(up_nics)} links up"
                
            return {'status': status, 'details': details}
        except Exception as e:
            self.logger.error(f"Network status check failed: {str(e)}")
            return {'status': 'Unknown', 'details': 'Check failed'}
    def _process_vcenter_info(self, content: vim.ServiceInstance.RetrieveContent, vcenter: Dict[str, str]) -> Dict[str, Any]:
        try:
            about = content.about
            cert_info = self._get_certificate_info(content, vcenter['host'])
            
            # Initialize default values
            storage_health = {'status': 'Unknown', 'capacity_used': 0, 'disk_health': 'Unknown'}
            network_status = {'status': 'Unknown', 'details': 'Not collected'}
            vsan_health = {'status': 'Unknown', 'disk_status': 'Unknown', 'network_status': 'Unknown'}
            ha_status = "Unknown"
            avg_latency = 0
            overcommitment = {'cpu': 0, 'memory': 0, 'storage': 0}
            drs_info = {'status': 'Unknown', 'balance': 'Unknown'}

            # Collect metrics
            for datacenter in content.rootFolder.childEntity:
                storage_health = self._get_storage_health(datacenter)
                
                for cluster in datacenter.hostFolder.childEntity:
                    cluster_ha = self._get_ha_status(cluster)
                    if cluster_ha != "Disabled":
                        ha_status = cluster_ha
                    
                    drs_info = self._get_drs_status(cluster)
                    vsan_health = self._get_vsan_health(cluster)
                    
                    cluster_latency = self._get_average_latency(cluster)
                    if cluster_latency > avg_latency:
                        avg_latency = cluster_latency
                    
                    cluster_overcommit = self._calculate_overcommitment(cluster)
                    if cluster_overcommit['cpu'] > overcommitment['cpu']:
                        overcommitment = cluster_overcommit
                    
                    for host in cluster.host:
                        host_network = self._get_network_status(host)
                        if host_network['status'] != 'Unknown':
                            network_status = host_network
                            break

            return {
                'hostname': vcenter['host'],
                'version': about.version,
                'build_number': about.build,
                'deploy_type': vcenter['DeployType'],
                'certificates': cert_info.get('certificates', []),
                'cert_mode': cert_info.get('mode'),
                'ha_status': ha_status,
                'storage_health_status': storage_health['status'],
                'disk_health_status': storage_health['disk_health'],
                'storage_capacity_used': storage_health['capacity_used'],
                'network_status': network_status['status'],
                'network_details': network_status['details'],
                'vsan_health_status': vsan_health['status'],
                'vsan_disk_status': vsan_health['disk_status'],
                'vsan_network_status': vsan_health['network_status'],
                'avg_latency': avg_latency,
                'cpu_overcommitment': overcommitment['cpu'],
                'memory_overcommitment': overcommitment['memory'],
                'storage_overcommitment': overcommitment['storage'],
                'drs_status': drs_info['status'],
                'drs_balance': drs_info['balance'],
                'status': 'connected',
                'last_checked': datetime.utcnow(),
                'error_message': None
            }
        except Exception as e:
            self.logger.error(f"vCenter info processing failed: {str(e)}")
            return {
                'hostname': vcenter['host'],
                'version': None,
                'build_number': None,
                'deploy_type': vcenter['DeployType'],
                'certificates': [],
                'cert_mode': None,
                'ha_status': 'Unknown',
                'storage_health_status': 'Unknown',
                'disk_health_status': 'Unknown',
                'storage_capacity_used': 0,
                'network_status': 'Unknown',
                'network_details': 'Error collecting data',
                'vsan_health_status': 'Unknown',
                'vsan_disk_status': 'Unknown',
                'vsan_network_status': 'Unknown',
                'avg_latency': 0,
                'cpu_overcommitment': 0,
                'memory_overcommitment': 0,
                'storage_overcommitment': 0,
                'drs_status': 'Unknown',
                'drs_balance': 'Unknown',
                'status': 'error',
                'last_checked': datetime.utcnow(),
                'error_message': str(e)
            }

    def _process_host(self, host: vim.HostSystem, datacenter: str, cluster: str) -> Dict[str, Any]:
        try:
            cpu_usage = host.summary.quickStats.overallCpuUsage
            total_cpu = host.summary.hardware.cpuMhz * host.summary.hardware.numCpuCores
            memory_usage = host.summary.quickStats.overallMemoryUsage
            total_memory = host.summary.hardware.memorySize / (1024 * 1024)

            return {
                'Host': host.name,
                'Datacenter': datacenter,
                'Cluster': cluster,
                'NumCPU': host.hardware.cpuInfo.numCpuPackages,
                'NumCores': host.hardware.cpuInfo.numCpuCores,
                'CPUUsage': str(cpu_usage),
                'CPUUsagePercentage': round((cpu_usage / total_cpu * 100) if total_cpu > 0 else 0, 2),
                'Mem': round(total_memory / 1024, 2),
                'MemoryUsage': str(memory_usage),
                'MemoryUsagePercentage': round((memory_usage / total_memory * 100) if total_memory > 0 else 0, 2),
                'TotalVMs': len(host.vm),
                'DNS': ', '.join(host.config.network.dnsConfig.address),
                'NTP': ', '.join(host.config.dateTimeInfo.ntpConfig.server),
                'IP': ', '.join([nic.spec.ip.ipAddress for nic in host.config.network.vnic]),
                'MAC': ', '.join([nic.spec.mac for nic in host.config.network.vnic]),
                'PowerPolicy': host.config.powerSystemInfo.currentPolicy.shortName,
                'Vendor': host.hardware.systemInfo.vendor,
                'Model': host.hardware.systemInfo.model,
                'ServiceTag': host.hardware.systemInfo.serialNumber
            }
        except Exception as e:
            self.logger.error(f"Error processing host {host.name}: {str(e)}")
            raise

    def _process_cluster(self, cluster: vim.ClusterComputeResource, datacenter: str, deploy_type: str) -> Dict[str, Any]:
        try:
            total_cpu = 0
            used_cpu = 0
            total_memory = 0
            used_memory = 0
            total_storage = 0
            used_storage = 0
            vsan_capacity = 0
            vsan_free = 0
            vsan_enabled = False

            for host in cluster.host:
                cpu_mhz = host.summary.hardware.cpuMhz * host.summary.hardware.numCpuCores
                total_cpu += cpu_mhz
                used_cpu += host.summary.quickStats.overallCpuUsage or 0
                
                host_memory = host.summary.hardware.memorySize / (1024 * 1024)
                total_memory += host_memory
                used_memory += host.summary.quickStats.overallMemoryUsage or 0

            for datastore in cluster.datastore:
                total_storage += datastore.summary.capacity
                used_storage += (datastore.summary.capacity - datastore.summary.freeSpace)
                
                if hasattr(datastore.summary, 'type') and datastore.summary.type == 'vsan':
                    vsan_enabled = True
                    vsan_capacity += datastore.summary.capacity
                    vsan_free += datastore.summary.freeSpace

            return {
                'ClusterName': cluster.name,
                'CPUUtilization': round((used_cpu / total_cpu * 100) if total_cpu > 0 else 0, 2),
                'MemoryUtilization': round((used_memory / total_memory * 100) if total_memory > 0 else 0, 2),
                'StorageUtilization': round((used_storage / total_storage * 100) if total_storage > 0 else 0, 2),
                'vSANEnabled': vsan_enabled,
                'vSANCapacityTiB': round(vsan_capacity / (1024 ** 4), 2),
                'vSANUsedTiB': round((vsan_capacity - vsan_free) / (1024 ** 4), 2),
                'vSANFreeTiB': round(vsan_free / (1024 ** 4), 2),
                'vSANUtilization': round(((vsan_capacity - vsan_free) / vsan_capacity * 100) if vsan_capacity > 0 else 0, 2),
                'NumHosts': len(cluster.host),
                'NumCPUSockets': sum(host.hardware.cpuInfo.numCpuPackages for host in cluster.host),
                'NumCPUCores': sum(host.hardware.cpuInfo.numCpuCores for host in cluster.host),
                'DeployType': deploy_type
            }
        except Exception as e:
            self.logger.error(f"Error processing cluster {cluster.name}: {str(e)}")
            raise

    def _process_vm(self, vm: vim.VirtualMachine, datacenter: str, cluster: str, host: str) -> Dict[str, Any]:
        try:
            ips = []
            if hasattr(vm, 'guest') and hasattr(vm.guest, 'net'):
                for nic in vm.guest.net:
                    if hasattr(nic, 'ipAddress') and nic.ipAddress:
                        ips.extend(nic.ipAddress)

            nic_types = set()
            if hasattr(vm, 'config') and hasattr(vm.config, 'hardware'):
                for device in vm.config.hardware.device:
                    if isinstance(device, vim.vm.device.VirtualEthernetCard):
                        nic_type = device.__class__.__name__
                        nic_type = nic_type.replace('Virtual', '').replace('Card', '')
                        nic_types.add(nic_type)

            return {
                'VMName': vm.name,
                'OS': vm.summary.config.guestFullName,
                'Site': datacenter,
                'State': vm.summary.runtime.powerState,
                'Created': vm.config.createDate,
                'SizeGB': round(vm.summary.storage.committed / (1024 * 1024 * 1024), 2),
                'InUseGB': round(vm.summary.storage.uncommitted / (1024 * 1024 * 1024), 2),
                'IP': ', '.join(ips) if ips else None,
                'NICType': ', '.join(sorted(nic_types)) if nic_types else 'Unknown',
                'VMTools': vm.summary.guest.toolsStatus,
                'VMVersion': int(vm.config.version.replace('vmx-', '')),
                'Host': host,
                'Cluster': cluster,
                'Notes': vm.summary.config.annotation
            }
        except Exception as e:
            self.logger.error(f"Error processing VM {vm.name}: {str(e)}")
            raise

    def _process_snapshot(self, snapshot: vim.vm.Snapshot, vm: vim.VirtualMachine) -> Dict[str, Any]:
        try:
            return {
                'vm_id': vm.config.instanceUuid,
                'vm_name': vm.name,
                'snapshot': snapshot.name,
                'created': snapshot.createTime
            }
        except Exception as e:
            self.logger.error(f"Error processing snapshot for VM {vm.name}: {str(e)}")
            raise

    def _process_affinity_rules(self, cluster: vim.ClusterComputeResource, vcenter_host: str) -> List[Dict[str, Any]]:
        rules = []
        try:
            if hasattr(cluster, 'configurationEx') and hasattr(cluster.configurationEx, 'rule'):
                for rule in cluster.configurationEx.rule:
                    base_rule_data = {
                        'vcenter': vcenter_host,
                        'rule_name': rule.name,
                        'enabled': rule.enabled,
                        'cluster': cluster.name,
                        'mandatory': getattr(rule, 'mandatory', False),
                        'description': getattr(rule, 'description', ''),
                        'vms': '',
                        'hosts': ''
                    }

                    try:
                        # VM to Host rules
                        if isinstance(rule, vim.cluster.VmHostRuleInfo):
                            vm_names = []
                            host_names = []

                            if hasattr(rule, 'vmGroupName') and hasattr(cluster.configurationEx, 'group'):
                                vm_group = next((g for g in cluster.configurationEx.group 
                                               if hasattr(g, 'name') and g.name == rule.vmGroupName), None)
                                if vm_group and hasattr(vm_group, 'vm'):
                                    vm_names = [vm.name for vm in vm_group.vm]

                            if hasattr(rule, 'affineHostGroupName') and hasattr(cluster.configurationEx, 'group'):
                                host_group = next((g for g in cluster.configurationEx.group 
                                                 if hasattr(g, 'name') and g.name == rule.affineHostGroupName), None)
                                if host_group and hasattr(host_group, 'host'):
                                    host_names = [host.name for host in host_group.host]

                            base_rule_data.update({
                                'rule_type': 'vm_host_affinity',
                                'vms': ','.join(vm_names) if vm_names else '',
                                'hosts': ','.join(host_names) if host_names else ''
                            })
                            rules.append(base_rule_data)

                        # VM to VM affinity rules
                        elif isinstance(rule, vim.cluster.AffinityRuleSpec):
                            if hasattr(rule, 'vm'):
                                base_rule_data.update({
                                    'rule_type': 'vm_affinity',
                                    'vms': ','.join(vm.name for vm in rule.vm),
                                    'hosts': ''
                                })
                                rules.append(base_rule_data)

                        # VM to VM anti-affinity rules
                        elif isinstance(rule, vim.cluster.AntiAffinityRuleSpec):
                            if hasattr(rule, 'vm'):
                                base_rule_data.update({
                                    'rule_type': 'vm_anti_affinity',
                                    'vms': ','.join(vm.name for vm in rule.vm),
                                    'hosts': ''
                                })
                                rules.append(base_rule_data)

                    except Exception as e:
                        self.logger.error(f"Error processing rule {rule.name} in cluster {cluster.name}: {str(e)}")
                        continue

        except Exception as e:
            self.logger.error(f"Error processing rules for cluster {cluster.name}: {str(e)}")
        
        return rules