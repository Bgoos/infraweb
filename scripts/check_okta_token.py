import requests
import logging
import subprocess
import json
import os
import re

# Disable SSL warnings
requests.packages.urllib3.disable_warnings()

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
VCENTER_HOST = "cr3-vcenter-11.csmodule.com"  # Replace with your vCenter hostname
PS_SCRIPT_PATH = os.path.join("Scripts", "credential_script.ps1")  # Path to PowerShell script


def get_credentials(ps_script, vcenter_password_id="28417", windows_password_id="13579"):
    """Fetch credentials using the provided PowerShell script."""
    logger.info("Fetching credentials using PowerShell script.")
    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script,
             "-VCenterPasswordId", vcenter_password_id,
             "-WindowsPasswordId", windows_password_id],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout
        logger.info("Successfully fetched credentials.")

        # Parse credential info using regex
        vcenter_match = re.search(r'"vcenter":\s*{\s*"password":\s*"([^"]+)",\s*"username":\s*"([^"]+)"\s*}', output)
        if vcenter_match:
            return {
                'username': vcenter_match.group(2),
                'password': vcenter_match.group(1)
            }
        else:
            logger.error("Could not parse credentials from script output.")
            return None
    except subprocess.CalledProcessError as e:
        logger.error(f"PowerShell script error: {e.stderr}")
        return None
    except Exception as e:
        logger.error(f"Error fetching credentials: {e}")
        return None


def get_session_id(hostname, username, password):
    """Fetch a session ID from vCenter."""
    logger.info(f"Attempting to get session ID for {hostname}")
    url = f"https://{hostname}/api/session"
    try:
        response = requests.post(url, auth=(username, password), verify=False)
        if response.ok:
            logger.info("Successfully retrieved session ID")
            return response.text.strip('"')  # Remove quotes from the response
        else:
            logger.error(f"Failed to get session ID: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error fetching session ID: {e}")
        return None


def get_operator_client_token(hostname, session_id):
    """Fetch operator client token info from the vCenter API."""
    logger.info("Fetching operator client token info")
    url = f"https://{hostname}/api/vcenter/identity/broker/tenants/operator-client"
    headers = {
        "vmware-api-session-id": session_id,
        "Accept": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, verify=False)
        if response.ok:
            logger.info("Successfully fetched operator client token info")
            return response.json()
        else:
            logger.error(f"Failed to fetch operator client token: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error fetching operator client token: {e}")
        return None


def main():
    # Step 1: Fetch credentials
    credentials = get_credentials(PS_SCRIPT_PATH)
    if not credentials:
        logger.error("Could not retrieve credentials. Exiting.")
        return

    username = credentials['username']
    password = credentials['password']

    # Step 2: Get session ID
    session_id = get_session_id(VCENTER_HOST, username, password)
    if not session_id:
        logger.error("Could not retrieve session ID. Exiting.")
        return

    # Step 3: Fetch operator client token info
    token_info = get_operator_client_token(VCENTER_HOST, session_id)
    if token_info:
        print("\nOperator Client Token Info:")
        print(json.dumps(token_info, indent=2))

        # Extract token expiration
        expires_in = token_info.get("expires_in")
        if expires_in:
            print(f"\nToken expires in: {expires_in} seconds")
        else:
            print("\nToken expiration details not available.")
    else:
        logger.error("Could not retrieve operator client token info.")


if __name__ == "__main__":
    main()
