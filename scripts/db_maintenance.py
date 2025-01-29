import os
import sqlite3
from datetime import datetime
import shutil
import logging
from logging.handlers import RotatingFileHandler
import re

class DatabaseMaintenance:
    def __init__(self, db_path):
        self.db_path = db_path
        self.setup_logging()
        
    def setup_logging(self):
        """Initialize logging configuration"""
        log_dir = os.path.join(os.path.dirname(os.path.dirname(self.db_path)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'db_maintenance.log')
        
        self.logger = logging.getLogger('db_maintenance')
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        handler = RotatingFileHandler(log_file, maxBytes=1024*1024, backupCount=5)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        self.logger.addHandler(handler)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def backup_database(self):
        """Create a backup of the database"""
        backup_dir = os.path.join(os.path.dirname(self.db_path), 'backup')
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f'audit_reports_{timestamp}.db')
        
        try:
            shutil.copy2(self.db_path, backup_path)
            self.logger.info(f"Database backed up to: {backup_path}")
            return True
        except Exception as e:
            self.logger.error(f"Backup failed: {str(e)}")
            return False

    def parse_date_string(self, date_str):
        """Convert date strings to standard format, excluding WSUS target groups"""
        if not date_str:
            return None
            
        # Common date patterns
        patterns = {
            r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}': '%Y-%m-%d %H:%M:%S',
            r'^\d{2}/\d{2}/\d{4}': '%d/%m/%Y',
            r'^\d{4}/\d{2}/\d{2}': '%Y/%m/%d'
        }
        
        date_str = str(date_str).strip()
        
        for pattern, fmt in patterns.items():
            if re.match(pattern, date_str):
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    return parsed_date.strftime('%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass
        return None

    def standardize_dates(self):
        """Standardize date formats in the database, excluding WSUS target groups"""
        try:
            if not self.backup_database():
                raise Exception("Backup failed, aborting date standardization")
                
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            # Columns to explicitly exclude from date standardization
            exclude_columns = ['UpdateTG']
            
            for table in tables:
                table_name = table[0]
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                # Find date-like columns, excluding specific columns
                date_columns = [col[1] for col in columns 
                              if any(term in col[1].lower() 
                                    for term in ['date', 'time', 'created', 'updated'])
                              and col[1] not in exclude_columns]
                
                for date_col in date_columns:
                    cursor.execute(f"SELECT DISTINCT {date_col} FROM {table_name} WHERE {date_col} IS NOT NULL")
                    values = cursor.fetchall()
                    
                    for value in values:
                        old_value = value[0]
                        new_value = self.parse_date_string(old_value)
                        
                        if new_value and new_value != old_value:
                            cursor.execute(f"""
                                UPDATE {table_name} 
                                SET {date_col} = ? 
                                WHERE {date_col} = ?
                            """, (new_value, old_value))
                            self.logger.info(f"Standardized date in {table_name}.{date_col}: {old_value} -> {new_value}")
            
            conn.commit()
            self.logger.info("Date formats standardized (excluding WSUS target groups)")
            
            conn.close()
            return True
            
        except Exception as e:
            self.logger.error(f"Error standardizing dates: {str(e)}")
            return False

    def clean_empty_tables(self):
        """Identify and optionally remove empty tables"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            empty_tables = []
            for table in tables:
                table_name = table[0]
                if table_name != 'sqlite_sequence':  # Skip SQLite system table
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    if count == 0:
                        empty_tables.append(table_name)
                        self.logger.info(f"Found empty table: {table_name}")
            
            if empty_tables:
                print("\nEmpty tables found:")
                for table in empty_tables:
                    print(f"- {table}")
                
                user_input = input("\nWould you like to remove these empty tables? (yes/no): ").lower()
                if user_input == 'yes':
                    for table in empty_tables:
                        cursor.execute(f"DROP TABLE {table}")
                        cursor.execute("DELETE FROM sqlite_sequence WHERE name=?", (table,))
                        self.logger.info(f"Removed empty table: {table}")
                    conn.commit()
                    print("Empty tables removed.")
                else:
                    print("Empty tables kept for review.")
            else:
                print("No empty tables found.")
            
            conn.close()
            return True
            
        except Exception as e:
            self.logger.error(f"Error handling empty tables: {str(e)}")
            return False

    def vacuum_database(self):
        """Vacuum the database to reclaim space and optimize"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get size before vacuum
            size_before = os.path.getsize(self.db_path) / (1024*1024)
            
            cursor.execute("VACUUM")
            conn.commit()
            conn.close()
            
            # Get size after vacuum
            size_after = os.path.getsize(self.db_path) / (1024*1024)
            
            self.logger.info(f"Database vacuumed successfully. Size reduced from {size_before:.2f}MB to {size_after:.2f}MB")
            return True
            
        except Exception as e:
            self.logger.error(f"Error vacuuming database: {str(e)}")
            return False

    def analyze_database(self):
        """Analyze database content and structure"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            print("\nDatabase Analysis:")
            print("-" * 50)
            
            # Get table statistics
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            for table in tables:
                table_name = table[0]
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                print(f"\nTable: {table_name}")
                print(f"Records: {count}")
                
                # Get column info
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                print("Columns:", ", ".join(col[1] for col in columns))
            
            conn.close()
            return True
            
        except Exception as e:
            self.logger.error(f"Error analyzing database: {str(e)}")
            return False

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, 'data', 'audit_reports.db')
    
    maintainer = DatabaseMaintenance(db_path)
    
    print("Database Maintenance Utility")
    print("=" * 50)
    print(f"Database path: {db_path}")
    print(f"Current size: {os.path.getsize(db_path) / (1024*1024):.2f}MB")
    print("=" * 50)
    
    # Backup first
    print("\nCreating backup...")
    if not maintainer.backup_database():
        print("Failed to create backup. Aborting maintenance.")
        return
    
    # Standardize dates
    print("\nStandardizing date formats...")
    if maintainer.standardize_dates():
        print("Dates standardized successfully")
    else:
        print("Failed to standardize dates")
    
    # Clean empty tables
    print("\nChecking for empty tables...")
    if maintainer.clean_empty_tables():
        print("Empty tables handled successfully")
    else:
        print("Failed to handle empty tables")
    
    # Vacuum database
    print("\nOptimizing database...")
    if maintainer.vacuum_database():
        print("Database optimized successfully")
    else:
        print("Failed to optimize database")
    
    # Analyze database
    print("\nAnalyzing database...")
    if maintainer.analyze_database():
        print("Database analysis completed")
    else:
        print("Failed to analyze database")
    
    print("\nMaintenance complete. Check logs for details.")

if __name__ == "__main__":
    main()