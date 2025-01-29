import os
import sqlite3
from datetime import datetime
import platform

def format_result(result):
    # Windows-compatible symbols
    if isinstance(result, bool):
        return "[SUCCESS]" if result else "[FAILED]"
    elif isinstance(result, (int, str)):
        return result
    return str(result)

def format_timestamp(timestamp):
    if not timestamp:
        return "No date available"
    try:
        # Try parsing as datetime
        if isinstance(timestamp, str):
            # Remove any microseconds for consistent formatting
            timestamp = timestamp.split('.')[0]
            return datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
    except:
        return f"Non-standard format: {timestamp}"
    return timestamp

def verify_setup():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    results = []
    
    print("\nSystem Information:")
    print("-" * 50)
    print(f"Python Version: {platform.python_version()}")
    print(f"Operating System: {platform.system()} {platform.version()}")
    print(f"Base Directory: {base_dir}")
    
    # 1. Verify directories
    required_dirs = ['data', 'logs', 'app', 'config', 'templates']
    missing_dirs = []
    
    print("\nDirectory Verification:")
    print("-" * 50)
    for dir_name in required_dirs:
        dir_path = os.path.join(base_dir, dir_name)
        exists = os.path.exists(dir_path)
        if not exists:
            missing_dirs.append(dir_name)
        print(f"{dir_name:15} | {'[PRESENT]' if exists else '[MISSING]'}")
    
    if missing_dirs:
        print(f"\nWarning: Missing directories: {', '.join(missing_dirs)}")
    
    # 2. Database and utilities verification
    print("\nDatabase Verification:")
    print("-" * 50)
    db_path = os.path.join(base_dir, 'data', 'audit_reports.db')
    db_exists = os.path.exists(db_path)
    print(f"Database file    | {'[PRESENT]' if db_exists else '[MISSING]'}")
    
    if db_exists:
        size_mb = os.path.getsize(db_path) / (1024*1024)
        print(f"Database size    | {size_mb:.2f} MB")
    
    sqlite_files = ['sqlite3.exe', 'sqldiff.exe', 'sqlite3_analyzer.exe']
    for file in sqlite_files:
        file_path = os.path.join(base_dir, 'data', file)
        print(f"{file:15} | {'[PRESENT]' if os.path.exists(file_path) else '[MISSING]'}")
    
    # 3. Database content verification
    if db_exists:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Verify integrity
            cursor.execute("PRAGMA integrity_check")
            integrity_result = cursor.fetchone()[0]
            print(f"Database integrity| {integrity_result}")
            
            print("\nTable Statistics:")
            print("-" * 50)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            for table in tables:
                table_name = table[0]
                # Get record count
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                
                # Get column info
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                # Try to find date columns
                date_columns = [col[1] for col in columns if any(term in col[1].lower() 
                              for term in ['date', 'time', 'created', 'updated'])]
                
                print(f"\nTable: {table_name}")
                print(f"Records: {count}")
                
                if date_columns and count > 0:
                    for date_col in date_columns:
                        cursor.execute(f"SELECT MAX({date_col}) FROM {table_name}")
                        last_update = cursor.fetchone()[0]
                        if last_update:
                            print(f"Last {date_col}: {format_timestamp(last_update)}")
                
                # Show sample of column names
                print("Columns:", ", ".join(col[1] for col in columns[:5]))
                if len(columns) > 5:
                    print(f"... and {len(columns)-5} more columns")
            
            conn.close()
            
        except Exception as e:
            print(f"\nError accessing database: {str(e)}")
    
    # Log the verification
    log_dir = os.path.join(base_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'setup_verification.log')
    
    with open(log_path, 'a') as f:
        f.write(f"\nVerification Run: {datetime.now()}\n")
        f.write("-" * 50 + "\n")
        f.write(f"Database Path: {db_path}\n")
        f.write(f"Database Size: {size_mb:.2f} MB\n")
        f.write(f"Integrity Check: {integrity_result}\n")
        f.write("-" * 50 + "\n")

    print(f"\nVerification log written to: {log_path}")

if __name__ == "__main__":
    verify_setup()