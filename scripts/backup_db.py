import os
import shutil
from datetime import datetime
import sqlite3

def backup_database():
    # Base paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, 'data')
    backup_dir = os.path.join(base_dir, 'data', 'backup')
    
    # Create backup directory if it doesn't exist
    os.makedirs(backup_dir, exist_ok=True)
    
    # Source database
    db_path = os.path.join(data_dir, 'audit_reports.db')
    
    try:
        # Verify database is valid
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        conn.close()
        
        if result[0] != 'ok':
            raise Exception("Database integrity check failed")
        
        # Create backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f'audit_reports_{timestamp}.db')
        
        # Create backup
        shutil.copy2(db_path, backup_path)
        
        # Verify backup size matches original
        original_size = os.path.getsize(db_path)
        backup_size = os.path.getsize(backup_path)
        
        if original_size != backup_size:
            raise Exception("Backup size mismatch")
        
        # Keep only last 5 backups
        backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.db')])
        if len(backups) > 5:
            for old_backup in backups[:-5]:
                os.remove(os.path.join(backup_dir, old_backup))
        
        print(f"Backup created successfully: {backup_path}")
        print(f"Size: {backup_size / (1024*1024):.2f} MB")
        
        return True, backup_path
        
    except Exception as e:
        print(f"Backup failed: {str(e)}")
        return False, str(e)

if __name__ == "__main__":
    success, result = backup_database()
    exit(0 if success else 1)