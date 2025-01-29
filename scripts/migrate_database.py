import os
import sys
import sqlite3

def migrate_database():
    """Alter existing tables to add new columns"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                          'data', 'audit_reports.db')
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Backup first
        cursor.execute("BEGIN TRANSACTION")
        
        # Rename existing virtual_machines table
        cursor.execute("ALTER TABLE virtual_machines RENAME TO virtual_machines_old")
        
        # Create new virtual_machines table with updated schema
        cursor.execute("""
            CREATE TABLE virtual_machines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                VMName VARCHAR(100),
                OS VARCHAR(100),
                Site VARCHAR(50),
                State VARCHAR(50),
                Created DATETIME,
                SizeGB FLOAT,
                InUseGB FLOAT,
                IP VARCHAR(255),
                NICType VARCHAR(50),
                VMTools VARCHAR(50),
                VMVersion INTEGER,
                Host VARCHAR(50),
                Cluster VARCHAR(50),
                Notes TEXT,
                Team VARCHAR(50)
            )
        """)
        
        # Copy data from old table to new table
        cursor.execute("""
            INSERT INTO virtual_machines 
            (id, VMName, OS, Site, State, Created, SizeGB, InUseGB, IP, 
             VMTools, VMVersion, Host, Cluster, Notes)
            SELECT 
                id, VMName, OS, Site, State, Created, SizeGB, InUseGB, IP, 
                VMTools, VMVersion, Host, Cluster, Notes
            FROM virtual_machines_old
        """)
        
        # Drop old table
        cursor.execute("DROP TABLE virtual_machines_old")
        
        # Commit changes
        cursor.execute("COMMIT")
        print("Database migration completed successfully")
        
    except Exception as e:
        cursor.execute("ROLLBACK")
        print(f"Error during migration: {str(e)}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()