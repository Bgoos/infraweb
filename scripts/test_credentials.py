import os
import sys
import logging

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.credentials import credentials_manager

def setup_logging():
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.DEBUG,  # Set to DEBUG for more detailed logging
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def test_credentials():
    """Test credential retrieval"""
    logger = setup_logging()
    
    try:
        logger.info("Testing credential script path...")
        script_path = credentials_manager.ps_script_path
        if os.path.exists(script_path):
            logger.info(f"Found credential script at: {script_path}")
        else:
            logger.error(f"Credential script not found at: {script_path}")
            return

        logger.info("Testing credential retrieval...")
        credentials = credentials_manager.get_credentials(force_refresh=True)
        
        # Print credential structure (without actual values)
        print("\nCredential Structure:")
        print("=" * 50)
        for service, creds in credentials.items():
            print(f"\n{service}:")
            for key in creds:
                print(f"  {key}: {'<value present>' if creds[key] else '<empty>'}")
        
    except Exception as e:
        logger.error(f"Credential test failed: {str(e)}")

if __name__ == "__main__":
    test_credentials()