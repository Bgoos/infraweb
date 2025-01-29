import requests
import urllib3
import logging
from datetime import datetime
from typing import Dict, Optional
import subprocess
import json
import os
import re

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def get_credentials():
    """Get credentials using PowerShell script"""
    logger = setup_logging()
    try:
        # Define PowerShell script path
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ps_script = os.path.join(script_dir, 'Scripts', 'credential_script.ps1')
        vcenter_password_id = "28417"
        windows_password_id = "13579"

        # Run PowerShell script
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script,
             "-VCenterPasswordId", vcenter_password_id,
             "-WindowsPasswordId", windows_password_id],
            capture_output=True,
            text=True,
            check=True
        )

        output = result.stdout
        logger.info("Got PowerShell output")

        # Parse credential info using regex
        vcenter_match = re.search(r'"vcenter":\s*{\s*"password":\s*"([^"]+)",\s*"username":\s*"([^"]+)"\s*}', output)
        
        if vcenter_match:
            credentials = {
                'username': vcenter_match.group(2),
                'password': vcenter_match.group(1)
            }
            logger.info(f"Successfully parsed credentials for username: {credentials['username']}")
            return credentials
        else:
            logger.error("Could not find vCenter credentials in output")
            logger.debug(f"PowerShell output: {output}")
            return None

    except subprocess.CalledProcessError as e:
        logger.error(f"PowerShell script error: {e.stderr}")
        return None
    except Exception as e:
        logger.error(f"Error getting credentials: {e}")
        return None

def get_session_id(hostname: str, credentials: Dict) -> Optional[str]:
    """Get API session ID"""
    logger = logging.getLogger(__name__)
    try:
        url = f"https://{hostname}/api/session"
        logger.info(f"Attempting to get session for {hostname} with username {credentials['username']}")
        response = requests.post(
            url, 
            auth=(credentials['username'], credentials['password']), 
            verify=False
        )
        if response.ok:
            session_id = response.json()
            logger.info("Successfully got session ID")
            return session_id
        logger.error(f"Failed to get session ID: {response.text}")
        return None
    except Exception as e:
        logger.error(f"Error getting session ID: {e}")
        return None

def get_token_info(hostname: str, credentials: Dict) -> Dict:
    """Get Okta token information"""
    logger = logging.getLogger(__name__)
    try:
        # Get session ID
        session_id = get_session_id(hostname, credentials)
        if not session_id:
            return {"error": "Could not get session ID"}

        headers = {
            'vmware-api-session-id': session_id,
            'Accept': 'application/json'
        }

        # Check different possible endpoints for token info
        endpoints = [
            '/rest/com/vmware/cis/session/current',  # Current session info
            '/api/cis/session',  # Session info
            '/api/vcenter/tokenservice/token',  # Token info
            '/rest/vcenter/identity/providers/oauth2',  # OAuth2 providers
            '/api/cis/tagging/session-id',  # Session details
        ]

        results = {}
        for endpoint in endpoints:
            try:
                url = f"https://{hostname}{endpoint}"
                logger.info(f"Trying endpoint: {url}")
                response = requests.get(url, headers=headers, verify=False)
                if response.ok:
                    results[endpoint] = response.json()
                    logger.info(f"Success from {endpoint}")
                    logger.debug(f"Response: {response.json()}")
                else:
                    logger.warning(f"Failed for {endpoint}: {response.status_code}")
                    logger.debug(f"Response: {response.text}")
            except Exception as e:
                logger.error(f"Error for {endpoint}: {e}")

        # Try to get OAuth2 settings
        try:
            oauth_url = f"https://{hostname}/api/cis/session/oauth2"
            response = requests.get(oauth_url, headers=headers, verify=False)
            if response.ok:
                results['oauth2_settings'] = response.json()
                logger.info("Got OAuth2 settings")
        except Exception as e:
            logger.error(f"Error getting OAuth2 settings: {e}")

        return results

    except Exception as e:
        logger.error(f"Error in token info collection: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    logger = setup_logging()
    print("Getting credentials from PowerShell script...")
    
    # Get credentials
    credentials = get_credentials()
    if not credentials:
        print("Failed to get credentials")
        exit(1)

    print(f"Got credentials for user: {credentials['username']}")

    # Test vCenters
    vcenter_list = [
        'cr3-vcenter-11.csmodule.com',
        'std-vcenter-11.cydmodule.com'
    ]

    for vcenter in vcenter_list:
        print(f"\nChecking {vcenter}...")
        result = get_token_info(vcenter, credentials)
        
        # Save raw results to file
        output_file = f"token_info_{vcenter.split('.')[0]}.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"Raw results saved to {output_file}")

        # Display important information
        print("\nEndpoints with successful responses:")
        for endpoint, data in result.items():
            if endpoint != 'error':
                print(f"- {endpoint}")
                if isinstance(data, dict):
                    if 'expiry' in data:
                        print(f"  Expiry found: {data['expiry']}")
                    if 'token' in data:
                        print("  Token information available")
                    if 'type' in data:
                        print(f"  Type: {data['type']}")