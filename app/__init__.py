from flask import Flask
from flask_caching import Cache
from .models.infra import db, cache
from .services.vcenter.routes import vcenter_bp
import os

def create_app():
    app = Flask(__name__, 
                template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
                static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'))
    
    # Configure your app
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///C:/Docker/infraweb/data/audit_reports.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Configure cache
    app.config['CACHE_TYPE'] = 'redis'
    app.config['CACHE_REDIS_HOST'] = 'localhost'
    app.config['CACHE_REDIS_PORT'] = 6379
    app.config['CACHE_DEFAULT_TIMEOUT'] = 300
    
    # Initialize extensions
    db.init_app(app)
    cache.init_app(app)
    
    # Register blueprints
    app.register_blueprint(vcenter_bp)
    
    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    return app