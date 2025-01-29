from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
from datetime import datetime

db = SQLAlchemy()
cache = Cache()

class VCenterInfo(db.Model):
    """Model for storing comprehensive vCenter information"""
    __tablename__ = 'vcenter_details'
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(100), index=True)
    version = db.Column(db.String(50))
    build_number = db.Column(db.String(50))
    deploy_type = db.Column(db.String(10))
    
    # Certificate fields (these were in the working version)
    ssl_certificate_expiration = db.Column(db.DateTime)
    ssl_issuer = db.Column(db.String(200))
    ssl_subject = db.Column(db.String(200))
    idp_type = db.Column(db.String(50))
    idp_token_expiration = db.Column(db.DateTime)
    status = db.Column(db.String(20))
    license_type = db.Column(db.String(50))
    license_expiry = db.Column(db.DateTime)

    # Storage Health
    storage_health_status = db.Column(db.String(50))  # 'Healthy', 'Warning', 'Critical'
    disk_health_status = db.Column(db.String(50))    # 'Normal', 'Degraded', 'Critical'
    storage_capacity_used = db.Column(db.Float)      # Percentage
    
    # Network Status
    network_status = db.Column(db.String(50))        # 'Normal', 'Warning', 'Critical'
    network_details = db.Column(db.String(200))      # Additional details like "All Links Up"
    
    # vSAN Health
    vsan_health_status = db.Column(db.String(50))    # 'Healthy', 'Warning', 'Critical'
    vsan_disk_status = db.Column(db.String(50))      # 'Normal', 'Warning', 'Critical'
    vsan_network_status = db.Column(db.String(50))   # 'Normal', 'Warning', 'Critical'
    
    # Performance
    avg_latency = db.Column(db.Float)                # in milliseconds
    
    # Overcommitment
    cpu_overcommitment = db.Column(db.Float)         # Percentage
    memory_overcommitment = db.Column(db.Float)      # Percentage
    storage_overcommitment = db.Column(db.Float)     # Percentage
    
    # DRS Status
    drs_status = db.Column(db.String(50))           # 'Active', 'Partially Active', 'Disabled'
    drs_balance = db.Column(db.String(50))          # 'Optimal', 'Good', 'Fair', 'Poor'
    
    # HA Status (existing field)
    ha_status = db.Column(db.String(50))
    
    # Timestamps and Tracking
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)
    error_message = db.Column(db.Text)

class AffinityRule(db.Model):
    """Model for storing vCenter affinity rules"""
    __tablename__ = 'affinity_rules'
    id = db.Column(db.Integer, primary_key=True)
    vcenter = db.Column(db.String(100), index=True)
    rule_name = db.Column(db.String(100), index=True)
    rule_type = db.Column(db.String(50))  # 'affinity' or 'anti-affinity'
    enabled = db.Column(db.Boolean, index=True)
    cluster = db.Column(db.String(100), index=True)
    vms = db.Column(db.Text)  # Comma-separated list of VMs
    hosts = db.Column(db.Text)  # Comma-separated list of hosts
    mandatory = db.Column(db.Boolean)
    description = db.Column(db.Text)
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)

class Hosts(db.Model):
    __tablename__ = 'hosts'
    id = db.Column(db.Integer, primary_key=True)
    Host = db.Column(db.String, index=True)
    Datacenter = db.Column(db.String)
    Cluster = db.Column(db.String)
    NumCPU = db.Column(db.Integer)
    NumCores = db.Column(db.Integer)
    CPUUsagePercentage = db.Column(db.Float)
    Mem = db.Column(db.Float)
    MemoryUsagePercentage = db.Column(db.Float)
    TotalVMs = db.Column(db.Integer)
    DNS = db.Column(db.String)
    NTP = db.Column(db.String)
    IP = db.Column(db.String)
    MAC = db.Column(db.String)
    PowerPolicy = db.Column(db.String)
    Vendor = db.Column(db.String)
    Model = db.Column(db.String)
    ServiceTag = db.Column(db.String)

class Clusters(db.Model):
    __tablename__ = 'clusters'
    id = db.Column(db.Integer, primary_key=True)
    ClusterName = db.Column(db.String, index=True)
    CPUUtilization = db.Column(db.Float)
    MemoryUtilization = db.Column(db.Float)
    StorageUtilization = db.Column(db.Float)
    vSANEnabled = db.Column(db.Boolean)
    vSANCapacityTiB = db.Column(db.Float)
    vSANUsedTiB = db.Column(db.Float)
    vSANFreeTiB = db.Column(db.Float)
    vSANUtilization = db.Column(db.Float)
    NumHosts = db.Column(db.Integer)
    NumCPUSockets = db.Column(db.Integer)
    NumCPUCores = db.Column(db.Integer)
    FoundationLicenseCoreCount = db.Column(db.Integer)
    EntitledVSANLicenseTiBCount = db.Column(db.Float)
    RequiredVSANTiBCapacity = db.Column(db.Float)
    VSANLicenseTiBCount = db.Column(db.Float)
    RequiredVVFComputeLicenses = db.Column(db.Integer)
    RequiredVSANAddOnLicenses = db.Column(db.Float)
    DeployType = db.Column(db.String(10))

class VirtualMachines(db.Model):
    __tablename__ = 'virtual_machines'
    id = db.Column(db.Integer, primary_key=True)
    VMName = db.Column(db.String(100), index=True)
    OS = db.Column(db.String(100))
    Site = db.Column(db.String(50))
    State = db.Column(db.String(50), index=True)
    Created = db.Column(db.DateTime)
    SizeGB = db.Column(db.Float)
    InUseGB = db.Column(db.Float)
    IP = db.Column(db.String(50))
    NICType = db.Column(db.String(50))
    VMTools = db.Column(db.String(50))
    VMVersion = db.Column(db.Integer)
    Host = db.Column(db.String(50))
    Cluster = db.Column(db.String(50))
    Notes = db.Column(db.Text)

class WindowsVMs(db.Model):
    __tablename__ = 'windows_vms'
    id = db.Column(db.Integer, primary_key=True)
    VMName = db.Column(db.String(100), index=True)
    OS = db.Column(db.String(50))
    Site = db.Column(db.String(50))
    State = db.Column(db.String(50), index=True)
    Size = db.Column(db.Float)
    IP = db.Column(db.String(50))
    NICType = db.Column(db.String(50))
    VMToolsVersion = db.Column(db.String(50))
    VMHardwareVersion = db.Column(db.String(50))
    Cortex = db.Column(db.Boolean)
    CortexVersion = db.Column(db.String(50))
    VR = db.Column(db.Boolean)
    UpdateTG = db.Column(db.String(50))
    Ciphers = db.Column(db.String(100))
    Notes = db.Column(db.String(255))
    Tag = db.Column(db.String(50))

class ProdUsers(db.Model):
    __tablename__ = 'prod_users'
    id = db.Column(db.Integer, primary_key=True)
    Name = db.Column(db.String(100), index=True)
    Samaccountname = db.Column(db.String(100), index=True)
    Role = db.Column(db.String(100))
    Enabled = db.Column(db.Boolean, index=True)
    CreationDate = db.Column(db.DateTime)
    LastLogin = db.Column(db.DateTime)

class DevUsers(db.Model):
    __tablename__ = 'dev_users'
    id = db.Column(db.Integer, primary_key=True)
    Name = db.Column(db.String(100), index=True)
    Samaccountname = db.Column(db.String(100), index=True)
    Role = db.Column(db.String(100))
    Enabled = db.Column(db.Boolean, index=True)
    CreationDate = db.Column(db.DateTime)
    LastLogin = db.Column(db.DateTime)

class UsersGroups(db.Model):
    __tablename__ = 'users_groups'
    id = db.Column(db.Integer, primary_key=True)
    Name = db.Column(db.String(100))
    Samaccountname = db.Column(db.String(100))
    Role = db.Column(db.String(100))
    Enabled = db.Column(db.Boolean)
    CreationDate = db.Column(db.DateTime)
    LastLogin = db.Column(db.DateTime)

class Snapshots(db.Model):
    __tablename__ = 'snapshots'
    id = db.Column(db.Integer, primary_key=True)
    vm_id = db.Column(db.String(100))
    vm_name = db.Column(db.String(100), index=True)
    snapshot = db.Column(db.String(100))
    created = db.Column(db.DateTime)

class UpdateStats(db.Model):
    __tablename__ = 'update_stats'
    id = db.Column(db.Integer, primary_key=True)
    last_run = db.Column(db.DateTime, default=datetime.utcnow)
    duration = db.Column(db.Float)
    total_count = db.Column(db.Integer, default=1)