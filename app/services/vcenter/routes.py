from flask import Blueprint, render_template, jsonify, current_app
from ...models.infra import (Hosts, Clusters, VirtualMachines, WindowsVMs, 
                           UsersGroups, Snapshots, UpdateStats, ProdUsers, DevUsers, 
                           VCenterInfo, AffinityRule, cache)
from ..credentials import credentials_manager
from .collector import VCenterCollector
from datetime import datetime
import os
import json

vcenter_bp = Blueprint('vcenter', __name__)

def get_update_stats():
    """Get update statistics from database"""
    try:
        stats = UpdateStats.query.order_by(UpdateStats.id.desc()).first()
        if stats:
            return {
                'last_run': format_date(stats.last_run),
                'duration': round(stats.duration, 2),
                'count': stats.total_count
            }
    except Exception as e:
        print(f"Error reading update stats: {e}")
    return {
        'last_run': None,
        'duration': 0,
        'count': 0
    }

def format_date(date):
    """Format datetime object to string"""
    if date:
        return date.strftime('%Y-%m-%d %H:%M:%S')
    return None

@vcenter_bp.route('/')
@cache.cached(timeout=300)
def dashboard():
    # Get VMs by state
    powered_on_vms = VirtualMachines.query.filter_by(State='poweredOn').all()
    powered_off_vms = VirtualMachines.query.filter_by(State='poweredOff').all()
    
    # Count VMs by OS type
    total_vms = len(powered_on_vms)
    windows_vms = len([vm for vm in powered_on_vms if 'windows' in vm.OS.lower()])
    redhat_vms = len([vm for vm in powered_on_vms if 'red hat' in vm.OS.lower()])
    
    # Get cluster storage info
    cluster_storage = {}
    for cluster in Clusters.query.all():
        if cluster.vSANEnabled:
            cluster_storage[cluster.ClusterName] = round(cluster.vSANFreeTiB, 2)
    
    # Initialize counters
    site_counts = {}
    powered_off_by_site = {}
    hosts_by_site = {}
    
    # Count powered on VMs by site
    for vm in powered_on_vms:
        site_counts[vm.Site] = site_counts.get(vm.Site, 0) + 1
    
    # Count powered off VMs by site
    for vm in powered_off_vms:
        if vm.Site:  # Ensure Site is not None
            powered_off_by_site[vm.Site] = powered_off_by_site.get(vm.Site, 0) + 1
    
    # Count hosts by site
    for host in Hosts.query.all():
        if host.Datacenter:  # Ensure Datacenter is not None
            hosts_by_site[host.Datacenter] = hosts_by_site.get(host.Datacenter, 0) + 1
    
    # Sort dictionaries by site name
    site_counts = dict(sorted(site_counts.items()))
    powered_off_by_site = dict(sorted(powered_off_by_site.items()))
    hosts_by_site = dict(sorted(hosts_by_site.items()))
    
    # Get vCenter health metrics
    now = datetime.utcnow()
    vcenters = VCenterInfo.query.all()
    certs_expiring = 0
    drs_disabled = 0
    ha_disabled = 0
    vcenter_issues = 0
    
    for vcenter in vcenters:
        # Check certificates
        if vcenter.ssl_certificate_expiration:
            days_until_expiry = (vcenter.ssl_certificate_expiration - now).days
            if days_until_expiry < 30:
                certs_expiring += 1
        
        # Check DRS status
        if vcenter.drs_status == 'Disabled' or vcenter.drs_status == 'Unknown':
            drs_disabled += 1
            
        # Check HA status
        if vcenter.ha_status == 'Disabled' or vcenter.ha_status == 'None' or vcenter.ha_status == 'Unknown':
            ha_disabled += 1
            
        # Check for issues
        if (vcenter.status != 'connected' or 
            vcenter.storage_health_status == 'Critical' or 
            vcenter.network_status == 'Critical' or 
            vcenter.vsan_health_status == 'Critical'):
            vcenter_issues += 1
    
    # Get update statistics
    update_stats = get_update_stats()
    
    return render_template('dashboard.html',
                         total_vms=total_vms,
                         windows_vms=windows_vms,
                         redhat_vms=redhat_vms,
                         cluster_storage=cluster_storage,
                         site_counts=site_counts,
                         hosts_by_site=hosts_by_site,
                         powered_off_by_site=powered_off_by_site,
                         last_update=update_stats,
                         # Add vCenter health metrics
                         certs_expiring=certs_expiring,
                         drs_disabled=drs_disabled,
                         ha_disabled=ha_disabled,
                         vcenter_issues=vcenter_issues)

@vcenter_bp.route('/vcenters')
@cache.cached(timeout=300)
def vcenters():
    """Route for vCenter overview page"""
    try:
        # Add current datetime for certificate expiry calculations
        now = datetime.utcnow()  # Add this line
        
        # Get all vCenter information
        vcenters = VCenterInfo.query.all()
        
        # Add some debug logging
        print(f"Found {len(vcenters)} vCenters in database")  # Add this line
        
        # Initialize counters
        expiring_soon = 0
        ha_enabled = 0
        status_issues = 0

        # Calculate statistics and check expiration
        for vcenter in vcenters:
            # Check certificate expiration
            if vcenter.ssl_certificate_expiration:
                days_until_expiry = (vcenter.ssl_certificate_expiration - now).days
                vcenter.ssl_expiring_soon = days_until_expiry < 30
                if days_until_expiry < 30:
                    expiring_soon += 1

            # Check HA status
            if vcenter.ha_status and vcenter.ha_status.lower() != 'none':
                ha_enabled += 1

            # Check health issues
            if (vcenter.status != 'connected' or 
                vcenter.storage_health_status == 'Critical' or 
                vcenter.network_status == 'Critical' or 
                vcenter.vsan_health_status == 'Critical'):
                status_issues += 1

        return render_template('vcenters.html',
                            vcenters=vcenters,
                            expiring_soon=expiring_soon,
                            ha_enabled=ha_enabled,
                            status_issues=status_issues,
                            now=now)  # Add this parameter

    except Exception as e:
        current_app.logger.error(f"Error in vcenters route: {str(e)}")
        return render_template('vcenters.html',
                            vcenters=[],
                            expiring_soon=0,
                            ha_enabled=0,
                            status_issues=1,
                            now=datetime.utcnow())  # Add this parameter

@vcenter_bp.route('/hosts')
@cache.cached(timeout=300)
def hosts():
    hosts_data = Hosts.query.all()
    return render_template('hosts.html', hosts=hosts_data)

@vcenter_bp.route('/clusters')
@cache.cached(timeout=300)
def clusters():
    clusters_data = Clusters.query.all()
    return render_template('clusters.html', clusters=clusters_data)

@vcenter_bp.route('/rules')
@cache.cached(timeout=300)
def rules():
    """Route for affinity rules overview page"""
    try:
        rules = AffinityRule.query.all()
        return render_template('rules.html', rules=rules)
    except Exception as e:
        current_app.logger.error(f"Error in rules route: {str(e)}")
        return render_template('rules.html', rules=[])

@vcenter_bp.route('/virtual_machines')
@cache.cached(timeout=300)
def virtual_machines():
    vms_data = VirtualMachines.query.all()
    return render_template('virtual_machines.html', vms=vms_data)

@vcenter_bp.route('/snapshots')
@cache.cached(timeout=300)
def snapshots():
    snapshots_data = Snapshots.query.all()
    return render_template('snapshots.html', snapshots=snapshots_data)

@vcenter_bp.route('/users_groups')
@cache.cached(timeout=300)
def users_groups():
    users_data = UsersGroups.query.all()
    return render_template('users_groups.html', users=users_data)

@vcenter_bp.route('/windows_vms')
@cache.cached(timeout=300)
def windows_vms():
    vms_data = WindowsVMs.query.all()
    return render_template('windows_vms.html', windows_vms=vms_data)

@vcenter_bp.route('/prod_users')
@cache.cached(timeout=300)
def prod_users():
    users_data = ProdUsers.query.all()
    formatted_users = []
    for user in users_data:
        formatted_user = user.__dict__.copy()
        formatted_user['CreationDate'] = format_date(user.CreationDate)
        formatted_user['LastLogin'] = format_date(user.LastLogin)
        formatted_users.append(formatted_user)
    return render_template('prod_users.html', users=formatted_users)

@vcenter_bp.route('/dev_users')
@cache.cached(timeout=300)
def dev_users():
    users_data = DevUsers.query.all()
    formatted_users = []
    for user in users_data:
        formatted_user = user.__dict__.copy()
        formatted_user['CreationDate'] = format_date(user.CreationDate)
        formatted_user['LastLogin'] = format_date(user.LastLogin)
        formatted_users.append(formatted_user)
    return render_template('dev_users.html', users=formatted_users)

# API Endpoints
@vcenter_bp.route('/api/vcenters')
@cache.cached(timeout=300)
def api_vcenters():
    vcenters = VCenterInfo.query.all()
    return jsonify([{
        'hostname': vc.hostname,
        'version': vc.version,
        'build_number': vc.build_number,
        'deploy_type': vc.deploy_type,
        'ssl_expiration': format_date(vc.ssl_certificate_expiration),
        'ssl_issuer': vc.ssl_issuer,
        'ssl_subject': vc.ssl_subject,
        'storage_health': {
            'status': vc.storage_health_status,
            'disk_health': vc.disk_health_status,
            'capacity_used': vc.storage_capacity_used
        },
        'network': {
            'status': vc.network_status,
            'details': vc.network_details
        },
        'vsan_health': {
            'status': vc.vsan_health_status,
            'disk_status': vc.vsan_disk_status,
            'network_status': vc.vsan_network_status
        },
        'performance': {
            'latency': vc.avg_latency,
            'overcommitment': {
                'cpu': vc.cpu_overcommitment,
                'memory': vc.memory_overcommitment,
                'storage': vc.storage_overcommitment
            }
        },
        'drs': {
            'status': vc.drs_status,
            'balance': vc.drs_balance
        },
        'ha_status': vc.ha_status,
        'status': vc.status,
        'last_checked': format_date(vc.last_checked),
        'error_message': vc.error_message
    } for vc in vcenters])

@vcenter_bp.route('/api/hosts')
@cache.cached(timeout=300)
def api_hosts():
    hosts = Hosts.query.all()
    return jsonify([{
        'id': host.id,
        'Host': host.Host,
        'Datacenter': host.Datacenter,
        'Cluster': host.Cluster,
        'NumCPU': host.NumCPU,
        'NumCores': host.NumCores,
        'CPUUsagePercentage': host.CPUUsagePercentage,
        'Mem': host.Mem,
        'MemoryUsagePercentage': host.MemoryUsagePercentage,
        'TotalVMs': host.TotalVMs,
        'DNS': host.DNS,
        'NTP': host.NTP,
        'IP': host.IP,
        'MAC': host.MAC,
        'PowerPolicy': host.PowerPolicy,
        'Vendor': host.Vendor,
        'Model': host.Model,
        'ServiceTag': host.ServiceTag
    } for host in hosts])

@vcenter_bp.route('/api/clusters')
@cache.cached(timeout=300)
def api_clusters():
    clusters = Clusters.query.all()
    return jsonify([{
        'id': cluster.id,
        'ClusterName': cluster.ClusterName,
        'CPUUtilization': cluster.CPUUtilization,
        'MemoryUtilization': cluster.MemoryUtilization,
        'StorageUtilization': cluster.StorageUtilization,
        'vSANEnabled': cluster.vSANEnabled,
        'vSANCapacityTiB': cluster.vSANCapacityTiB,
        'vSANUsedTiB': cluster.vSANUsedTiB,
        'vSANFreeTiB': cluster.vSANFreeTiB,
        'vSANUtilization': cluster.vSANUtilization,
        'NumHosts': cluster.NumHosts,
        'NumCPUSockets': cluster.NumCPUSockets,
        'NumCPUCores': cluster.NumCPUCores,
        'FoundationLicenseCoreCount': cluster.FoundationLicenseCoreCount,
        'EntitledVSANLicenseTiBCount': cluster.EntitledVSANLicenseTiBCount,
        'RequiredVSANTiBCapacity': cluster.RequiredVSANTiBCapacity,
        'VSANLicenseTiBCount': cluster.VSANLicenseTiBCount,
        'RequiredVVFComputeLicenses': cluster.RequiredVVFComputeLicenses,
        'RequiredVSANAddOnLicenses': cluster.RequiredVSANAddOnLicenses,
        'DeployType': cluster.DeployType
    } for cluster in clusters])

@vcenter_bp.route('/api/virtual_machines')
@cache.cached(timeout=300)
def api_virtual_machines():
    vms = VirtualMachines.query.all()
    return jsonify([{
        'id': vm.id,
        'VMName': vm.VMName,
        'OS': vm.OS,
        'Site': vm.Site,
        'State': vm.State,
        'Created': format_date(vm.Created),
        'SizeGB': vm.SizeGB,
        'InUseGB': vm.InUseGB,
        'IP': vm.IP,
        'NICType': vm.NICType,
        'VMTools': vm.VMTools,
        'VMVersion': vm.VMVersion,
        'Host': vm.Host,
        'Cluster': vm.Cluster,
        'Notes': vm.Notes
    } for vm in vms])

@vcenter_bp.route('/api/windows_vms')
@cache.cached(timeout=300)
def api_windows_vms():
    vms = WindowsVMs.query.all()
    return jsonify([{
        'id': vm.id,
        'VMName': vm.VMName,
        'OS': vm.OS,
        'Site': vm.Site,
        'State': vm.State,
        'Size': vm.Size,
        'IP': vm.IP,
        'NICType': vm.NICType,
        'VMToolsVersion': vm.VMToolsVersion,
        'VMHardwareVersion': vm.VMHardwareVersion,
        'Cortex': vm.Cortex,
        'CortexVersion': vm.CortexVersion,
        'VR': vm.VR,
        'UpdateTG': vm.UpdateTG,
        'Ciphers': vm.Ciphers,
        'Notes': vm.Notes,
        'Tag': vm.Tag
    } for vm in vms])

@vcenter_bp.route('/api/users_groups')
@cache.cached(timeout=300)
def api_users_groups():
    users = UsersGroups.query.all()
    return jsonify([{
        'id': user.id,
        'Name': user.Name,
        'Samaccountname': user.Samaccountname,
        'Role': user.Role,
        'Enabled': user.Enabled,
        'CreationDate': format_date(user.CreationDate),
        'LastLogin': format_date(user.LastLogin)
    } for user in users])

@vcenter_bp.route('/api/prod_users')
@cache.cached(timeout=300)
def api_prod_users():
    users = ProdUsers.query.all()
    return jsonify([{
        'id': user.id,
        'Name': user.Name,
        'Samaccountname': user.Samaccountname,
        'Role': user.Role,
        'Enabled': user.Enabled,
        'CreationDate': format_date(user.CreationDate),
        'LastLogin': format_date(user.LastLogin)
    } for user in users])

@vcenter_bp.route('/api/dev_users')
@cache.cached(timeout=300)
def api_dev_users():
    users = DevUsers.query.all()
    return jsonify([{
        'id': user.id,
        'Name': user.Name,
        'Samaccountname': user.Samaccountname,
        'Role': user.Role,
        'Enabled': user.Enabled,
        'CreationDate': format_date(user.CreationDate),
        'LastLogin': format_date(user.LastLogin)
    } for user in users])


@vcenter_bp.route('/api/affinity_rules')
@cache.cached(timeout=300)
def api_affinity_rules():
    rules = AffinityRule.query.all()
    return jsonify([{
        'vcenter': rule.vcenter,
        'rule_name': rule.rule_name,
        'rule_type': rule.rule_type,
        'enabled': rule.enabled,
        'cluster': rule.cluster,
        'vms': rule.vms.split(',') if rule.vms else [],
        'hosts': rule.hosts.split(',') if rule.hosts else [],
        'mandatory': rule.mandatory,
        'description': rule.description,
        'last_checked': format_date(rule.last_checked)
    } for rule in rules])

@vcenter_bp.route('/api/snapshots')
@cache.cached(timeout=300)
def api_snapshots():
    snapshots = Snapshots.query.all()
    return jsonify([{
        'id': snapshot.id,
        'vm_id': snapshot.vm_id,
        'vm_name': snapshot.vm_name,
        'snapshot': snapshot.snapshot,
        'created': format_date(snapshot.created)
    } for snapshot in snapshots])

@vcenter_bp.route('/api/health')
@cache.cached(timeout=60)
def health_check():
    """API endpoint for system health check"""
    try:
        update_stats = get_update_stats()
        status = {
            'database': {
                'status': 'healthy',
                'details': {
                    'vm_count': VirtualMachines.query.filter_by(State='poweredOn').count(),
                    'host_count': Hosts.query.count(),
                    'cluster_count': Clusters.query.count(),
                    'snapshot_count': Snapshots.query.count(),
                    'vcenter_count': VCenterInfo.query.count(),
                    'affinity_rules_count': AffinityRule.query.count()
                }
            },
            'last_update': update_stats.get('last_run'),
            'status': 'operational'
        }
        return jsonify(status)
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500