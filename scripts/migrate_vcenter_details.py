import os
import sys
import sqlite3
import logging
from datetime import datetime

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.config import DATABASE_PATH

def setup_logging():
    """Set up logging configuration"""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'database_migration.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def migrate_database():
    """Add new columns to vcenter_details table"""
    logger = setup_logging()
    logger.info("Starting database migration for vcenter_details table")
    
    try:
        # Connect to the database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # New columns to add
        new_columns = [
            ('storage_health_status', 'VARCHAR(50)'),
            ('disk_health_status', 'VARCHAR(50)'),
            ('storage_capacity_used', 'FLOAT'),
            ('network_status', 'VARCHAR(50)'),
            ('network_details', 'VARCHAR(200)'),
            ('vsan_health_status', 'VARCHAR(50)'),
            ('vsan_disk_status', 'VARCHAR(50)'),
            ('vsan_network_status', 'VARCHAR(50)'),
            ('avg_latency', 'FLOAT'),
            ('cpu_overcommitment', 'FLOAT'),
            ('memory_overcommitment', 'FLOAT'),
            ('storage_overcommitment', 'FLOAT'),
            ('drs_status', 'VARCHAR(50)'),
            ('drs_balance', 'VARCHAR(50)')
        ]
        
        # Get existing columns
        cursor.execute("PRAGMA table_info(vcenter_details)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # Add new columns if they don't exist
        for column_name, column_type in new_columns:
            if column_name not in existing_columns:
                logger.info(f"Adding column {column_name}")
                try:
                    cursor.execute(f"ALTER TABLE vcenter_details ADD COLUMN {column_name} {column_type}")
                    logger.info(f"Successfully added column {column_name}")
                except sqlite3.OperationalError as e:
                    logger.error(f"Error adding column {column_name}: {str(e)}")
                    continue
        
        # Remove old columns (if needed)
        # Note: SQLite doesn't support dropping columns directly
        
        conn.commit()
        logger.info("Database migration completed successfully")
        
    except Exception as e:
        logger.error(f"Error during migration: {str(e)}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("Starting database migration...")
    migrate_database()
    print("Migration complete!")