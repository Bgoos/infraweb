import os
import json
import subprocess
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from ...utils.config import VCENTER_PASSWORD_ID, WINDOWS_PASSWORD_ID

class CredentialsManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._credentials = None
        self._last_refresh = None
        self._refresh_interval = timedelta(hours=1)
        self.ps_script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            'scripts',
            'credential_script.ps1'
        )

    def get_credentials(self, force_refresh: bool = False) -> Dict[str, Dict[str, str]]:
        """Get credentials from cache or fetch new ones"""
        try:
            if self._should_refresh() or force_refresh:
                self._refresh_credentials()
            
            if not self._credentials:
                raise Exception("No credentials available")
                
            return self._credentials
            
        except Exception as e:
            self.logger.error(f"Error getting credentials: {str(e)}")
            raise

    def _should_refresh(self) -> bool:
        """Check if credentials should be refreshed"""
        if not self._credentials or not self._last_refresh:
            return True
        
        return datetime.now() - self._last_refresh > self._refresh_interval

    def _refresh_credentials(self):
        """Refresh credentials using PowerShell script"""
        try:
            # Verify script exists
            if not os.path.exists(self.ps_script_path):
                self.logger.error(f"PowerShell script not found at: {self.ps_script_path}")
                raise FileNotFoundError(f"Script not found: {self.ps_script_path}")

            # Log the command we're about to run
            command = [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                self.ps_script_path,
                "-VCenterPasswordId",
                VCENTER_PASSWORD_ID,
                "-WindowsPasswordId",
                WINDOWS_PASSWORD_ID
            ]
            self.logger.debug(f"Executing command: {' '.join(command)}")

            # Run PowerShell script
            result = subprocess.run(
                command,
                capture_output=True,
                text=True
            )

            # Log the raw output for debugging
            self.logger.debug(f"PowerShell stdout: {result.stdout}")
            if result.stderr:
                self.logger.warning(f"PowerShell stderr: {result.stderr}")

            if result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode, 
                    command, 
                    result.stdout, 
                    result.stderr
                )

            # Try to find JSON in the output
            try:
                # Look for JSON-like content in the output
                json_start = result.stdout.find('{')
                json_end = result.stdout.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_content = result.stdout[json_start:json_end]
                    credentials = json.loads(json_content)
                else:
                    raise ValueError("No JSON content found in script output")
                
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse credentials JSON: {str(e)}")
                self.logger.debug(f"JSON content attempted to parse: {json_content if 'json_content' in locals() else 'No JSON found'}")
                raise
            
            # Validate credential structure
            if not self._validate_credentials(credentials):
                raise ValueError("Invalid credential format received")
            
            self._credentials = credentials
            self._last_refresh = datetime.now()
            self.logger.info("Credentials refreshed successfully")
            
        except Exception as e:
            self.logger.error(f"Error refreshing credentials: {str(e)}")
            raise

    def _validate_credentials(self, credentials: Dict) -> bool:
        """Validate the structure of retrieved credentials"""
        try:
            required_services = ['vcenter', 'windows']
            required_fields = ['username', 'password']

            for service in required_services:
                if service not in credentials:
                    self.logger.error(f"Missing {service} credentials")
                    return False
                
                for field in required_fields:
                    if field not in credentials[service]:
                        self.logger.error(f"Missing {field} in {service} credentials")
                        return False
                    
                    if not credentials[service][field]:
                        self.logger.error(f"Empty {field} in {service} credentials")
                        return False

            return True
            
        except Exception as e:
            self.logger.error(f"Error validating credentials: {str(e)}")
            return False

# Create singleton instance
credentials_manager = CredentialsManager()