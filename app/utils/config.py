import os
from typing import List, Dict

# Base paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
BACKUP_DIR = os.path.join(DATA_DIR, 'backup')

# Create directories if they don't exist
for directory in [DATA_DIR, LOG_DIR, BACKUP_DIR]:
    os.makedirs(directory, exist_ok=True)

# Database configuration
DATABASE_PATH = os.path.join(DATA_DIR, 'audit_reports.db')
SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'
SQLALCHEMY_TRACK_MODIFICATIONS = False

# vCenter configuration
VCENTERS: List[Dict[str, str]] = [
    {"host": "cr3-vcenter-11.csmodule.com", "DeployType": "VCF"},
    {"host": "cha-vcenter-11.csmodule.com", "DeployType": "VVF"},
    {"host": "gib-vcenter-11.csmodule.com", "DeployType": "VVF"},
    {"host": "us-mi-vcenter-01.csmodule.com", "DeployType": "VCF"},
    {"host": "us-wv-vcenter-11.csmodule.com", "DeployType": "VCF"},
    {"host": "nj2-vcenter-11.csmodule.com", "DeployType": "VCF"},
    {"host": "usa-nj-vcenter-11.csmodule.com", "DeployType": "VCF"},
    {"host": "usa-pa-vcenter-11.csmodule.com", "DeployType": "VCF"},
    {"host": "usa-mi-vcenter-11.csmodule.com", "DeployType": "VCF"},
    {"host": "usa-wv-vcenter-11.csmodule.com", "DeployType": "VCF"},
    {"host": "mt-vcenter-11.csmodule.com", "DeployType": "VVF"},
    {"host": "pa-vcenter-11.csmodule.com", "DeployType": "VCF"},
    {"host": "ca-van-vcenter-11.csmodule.com", "DeployType": "VCF"},
    {"host": "std-vcenter-11.cydmodule.com", "DeployType": "VCF"}
]

# Credential configuration
VCENTER_PASSWORD_ID = "28417"
WINDOWS_PASSWORD_ID = "13579"

# Logging configuration
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_FILE = os.path.join(LOG_DIR, 'app.log')
LOG_LEVEL = 'INFO'

# Scheduler configuration
UPDATE_SCHEDULE_TIME = "07:00"  # Daily update time

# Application configuration
DEBUG = True  # Set to False in production
PORT = 5005