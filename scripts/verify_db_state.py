import sqlite3
import os
from datetime import datetime

def verify_database_state(db_path):
    print(f"\nDatabase State Verification Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Database size
        size_mb = os.path.getsize(db_path) / (1024 * 1024)
        print(f"Database Size: {size_mb:.2f}MB")
        
        # Table information
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        print("\nTable Statistics:")
        print("-" * 50)
        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            
            # Get last update time if available
            date_fields = []
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            for col in columns:
                if any(term in col[1].lower() for term in ['date', 'time', 'created', 'updated']):
                    date_fields.append(col[1])
            
            print(f"\nTable: {table_name}")
            print(f"Records: {count}")
            
            if date_fields:
                for date_field in date_fields:
                    cursor.execute(f"SELECT MAX({date_field}) FROM {table_name}")
                    last_update = cursor.fetchone()[0]
                    if last_update:
                        print(f"Last {date_field}: {last_update}")
            
            # Sample data distribution if applicable
            if table_name == 'windows_vms':
                cursor.execute("SELECT DISTINCT UpdateTG FROM windows_vms WHERE UpdateTG IS NOT NULL")
                update_groups = cursor.fetchall()
                if update_groups:
                    print("Update Target Groups:", ", ".join([group[0] for group in update_groups]))
        
        conn.close()
        print("\nVerification completed successfully.")
        
    except Exception as e:
        print(f"Error during verification: {str(e)}")

if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                          'data', 'audit_reports.db')
    verify_database_state(db_path)