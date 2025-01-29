from app import create_app
import signal
import sys
import logging
from app.scheduler import scheduler_manager
from app.utils.config import PORT, DEBUG, LOG_FORMAT, LOG_FILE

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Shutdown signal received. Cleaning up...")
    scheduler_manager.stop()
    logger.info("Scheduler stopped")
    sys.exit(0)

def main():
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        app = create_app()
        logger.info(f"Starting application on port {PORT}")
        app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
    except Exception as e:
        logger.error(f"Application failed to start: {str(e)}")
        scheduler_manager.stop()
        sys.exit(1)

if __name__ == '__main__':
    main()
