import os
import sys
import logging
from datetime import datetime

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.infra import db, UpdateStats

def setup_logging():
    """Set up logging configuration"""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'db_init.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def init_db():
    """Initialize the database and create necessary tables"""
    logger = setup_logging()
    
    try:
        logger.info("Starting database initialization")
        app = create_app()
        
        with app.app_context():
            # Create all tables
            logger.info("Creating database tables")
            db.create_all()
            
            # Initialize update stats if empty
            if not UpdateStats.query.first():
                logger.info("Initializing update stats")
                initial_stats = UpdateStats(
                    last_run=datetime.utcnow(),
                    duration=0,
                    total_count=0
                )
                db.session.add(initial_stats)
                db.session.commit()
            
            logger.info("Database initialization completed successfully")
            print("Database initialized successfully!")
            
    except Exception as e:
        logger.error(f"Error during database initialization: {str(e)}")
        print(f"Error: {str(e)}")
        return False
        
    return True

def check_db_tables():
    """Check the status of database tables"""
    logger = setup_logging()
    
    try:
        logger.info("Checking database tables")
        app = create_app()
        
        with app.app_context():
            # Get list of all tables
            tables = db.metadata.tables.keys()
            logger.info(f"Found tables: {', '.join(tables)}")
            
            # Print table information
            print("\nDatabase Tables Status:")
            print("=" * 50)
            
            for table_name in tables:
                # Get table
                table = db.metadata.tables[table_name]
                
                # Get column information
                columns = [f"{col.name} ({col.type})" for col in table.columns]
                
                print(f"\nTable: {table_name}")
                print("-" * 30)
                print("Columns:")
                for col in columns:
                    print(f"  - {col}")
                
            print("\nAll tables verified successfully!")
            
    except Exception as e:
        logger.error(f"Error checking database tables: {str(e)}")
        print(f"Error: {str(e)}")
        return False
        
    return True

if __name__ == "__main__":
    # Initialize database
    if init_db():
        # Check tables if initialization was successful
        check_db_tables()