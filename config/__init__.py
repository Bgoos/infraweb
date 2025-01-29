import os

class Config:
    # Get base directory (C:\Docker\infraweb)
    BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    
    # Database directory and file
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    DB_FILE = 'audit_reports.db'
    
    # Create data directory if it doesn't exist
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Database URI
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(DATA_DIR, DB_FILE)}'
    
    # Disable Flask-SQLAlchemy modification tracking
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Logging configuration
    LOG_DIR = os.path.join(BASE_DIR, 'logs')
    os.makedirs(LOG_DIR, exist_ok=True)
    LOG_FILE = os.path.join(LOG_DIR, 'app.log')
    
    # Application configuration
    DEBUG = True  # Set to False in production
    PORT = 5005

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'  # Use in-memory database for testing

# Create a config map
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}