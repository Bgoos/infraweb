from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy import text
from ...models import db
import logging

class DatabaseOperations:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def execute_with_retry(self, operation_func, max_retries=3):
        """Execute database operation with retry logic"""
        for attempt in range(max_retries):
            try:
                result = operation_func()
                return result
            except Exception as e:
                self.logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_retries - 1:
                    raise
                db.session.rollback()

    def verify_table_integrity(self, table_name: str) -> Tuple[bool, Optional[str]]:
        """Verify the integrity of a specific table"""
        try:
            with db.engine.connect() as conn:
                # Check if table exists
                result = conn.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"))
                if not result.fetchone():
                    return False, f"Table {table_name} does not exist"
                
                # Check table structure
                result = conn.execute(text(f"PRAGMA table_info({table_name})"))
                if not result.fetchall():
                    return False, f"Table {table_name} has no columns"
                
                return True, None
        except Exception as e:
            return False, str(e)

    def get_table_stats(self, table_name: str) -> Dict:
        """Get statistics for a specific table"""
        try:
            with db.engine.connect() as conn:
                # Get record count
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.scalar()
                
                # Get last update time if applicable
                last_update = None
                result = conn.execute(text(f"PRAGMA table_info({table_name})"))
                columns = result.fetchall()
                date_columns = [col[1] for col in columns if 
                              any(term in col[1].lower() for term in 
                                  ['date', 'time', 'created', 'updated'])]
                
                if date_columns:
                    result = conn.execute(
                        text(f"SELECT MAX({date_columns[0]}) FROM {table_name}")
                    )
                    last_update = result.scalar()

                return {
                    'record_count': count,
                    'last_update': last_update,
                    'status': 'healthy' if count > 0 else 'empty'
                }
        except Exception as e:
            self.logger.error(f"Error getting stats for {table_name}: {str(e)}")
            return {
                'record_count': 0,
                'last_update': None,
                'status': 'error',
                'error': str(e)
            }

    def cleanup_orphaned_records(self) -> Dict[str, int]:
        """Clean up orphaned records in related tables"""
        cleanup_results = {}
        try:
            # Clean up snapshots without VMs
            with db.engine.connect() as conn:
                result = conn.execute(text("""
                    DELETE FROM snapshots 
                    WHERE vm_id NOT IN (
                        SELECT VMName FROM virtual_machines
                    )
                """))
                cleanup_results['snapshots'] = result.rowcount

            db.session.commit()
            return cleanup_results
        except Exception as e:
            self.logger.error(f"Error during cleanup: {str(e)}")
            db.session.rollback()
            return {'error': str(e)}

    def get_database_size(self) -> Dict:
        """Get database file size and stats"""
        try:
            with db.engine.connect() as conn:
                # Get page count and page size
                page_count = conn.execute(text("PRAGMA page_count")).scalar()
                page_size = conn.execute(text("PRAGMA page_size")).scalar()
                
                # Calculate sizes
                total_size = page_count * page_size
                free_size = conn.execute(text("PRAGMA freelist_count")).scalar() * page_size
                
                return {
                    'total_size_mb': total_size / (1024 * 1024),
                    'free_space_mb': free_size / (1024 * 1024),
                    'used_space_mb': (total_size - free_size) / (1024 * 1024)
                }
        except Exception as e:
            self.logger.error(f"Error getting database size: {str(e)}")
            return {'error': str(e)}

    def optimize_database(self) -> bool:
        """Perform database optimization operations"""
        try:
            with db.engine.connect() as conn:
                # Analyze tables
                conn.execute(text("ANALYZE"))
                
                # Vacuum database
                conn.execute(text("VACUUM"))
                
                return True
        except Exception as e:
            self.logger.error(f"Error optimizing database: {str(e)}")
            return False

    def get_table_relationships(self) -> Dict[str, List[str]]:
        """Get relationships between tables based on foreign keys"""
        relationships = {}
        try:
            with db.engine.connect() as conn:
                tables = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )).fetchall()
                
                for table in tables:
                    table_name = table[0]
                    fk_result = conn.execute(text(
                        f"PRAGMA foreign_key_list({table_name})"
                    )).fetchall()
                    
                    if fk_result:
                        relationships[table_name] = [
                            {'table': fk[2], 'from': fk[3], 'to': fk[4]}
                            for fk in fk_result
                        ]
            
            return relationships
        except Exception as e:
            self.logger.error(f"Error getting table relationships: {str(e)}")
            return {}