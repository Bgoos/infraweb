import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import db

def reset_database():
    """Drop and recreate all tables"""
    app = create_app()
    with app.app_context():
        # Drop all tables
        db.drop_all()
        # Create all tables with new schema
        db.create_all()
        print("Database schema updated successfully")

if __name__ == "__main__":
    reset_database()