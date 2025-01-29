import ssl
from typing import Optional, Dict
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import logging

class VCenterConnection:
    def __init__(self, host: str, credentials: Dict[str, str]):
        self.host = host
        self.credentials = credentials
        self.service_instance = None
        self.logger = logging.getLogger(__name__)
        self._context = self._create_ssl_context()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context for vCenter connection"""
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        context.verify_mode = ssl.CERT_NONE
        return context

    def connect(self) -> Optional[vim.ServiceInstance]:
        """Connect to vCenter"""
        try:
            self.service_instance = SmartConnect(
                host=self.host,
                user=self.credentials['vcenter']['username'],
                pwd=self.credentials['vcenter']['password'],
                sslContext=self._context
            )
            self.logger.info(f"Connected to vCenter: {self.host}")
            return self.service_instance
        except Exception as e:
            self.logger.error(f"Failed to connect to {self.host}: {str(e)}")
            raise

    def disconnect(self):
        """Disconnect from vCenter"""
        if self.service_instance:
            Disconnect(self.service_instance)
            self.logger.info(f"Disconnected from vCenter: {self.host}")
            self.service_instance = None

    def __enter__(self):
        """Context manager entry"""
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
        if exc_type:
            self.logger.error(f"Error during vCenter operations: {str(exc_val)}")
            return False
        return True