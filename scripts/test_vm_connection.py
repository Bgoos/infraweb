#!/usr/bin/env python3
import os
import sys
import ssl
from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect
import time
import urllib3
import requests

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Add the parent directory to the Python path for imports
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from app import create_app
from app.services.credentials import credentials_manager

# Test VMs configuration
TEST_VMS = [
    {
        "name": "cr3-util-11",
        "vcenter": "cr3-vcenter-11.csmodule.com",
        "ip": "10.13.4.11"
    },
    {
        "name": "std-util-11.cydmodule.com",
        "vcenter": "std-vcenter-11.cydmodule.com",
        "ip": "10.71.80.115"
    }
]

def test_vm_connection(credentials):
    """Test connection and operations for each VM"""
    for test_vm in TEST_VMS:
        print(f"\nTesting connection to {test_vm['name']} via {test_vm['vcenter']}")
        print("-" * 50)

        try:
            # Connect to vCenter
            print(f"1. Connecting to vCenter {test_vm['vcenter']}...")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS)
            context.verify_mode = ssl.CERT_NONE
            si = SmartConnect(
                host=test_vm['vcenter'],
                user=credentials['vcenter']['username'],
                pwd=credentials['vcenter']['password'],
                sslContext=context
            )
            content = si.RetrieveContent()
            print("   ? Connected to vCenter")

            # Find VM
            container = content.viewManager.CreateContainerView(
                content.rootFolder, [vim.VirtualMachine], True
            )
            vm = None
            for v in container.view:
                if v.name == test_vm['name']:
                    vm = v
                    break

            if not vm:
                print(f"   ? VM {test_vm['name']} not found!")
                continue
            print(f"   ? Found VM: {vm.name}")

            # Setup credentials
            creds = vim.vm.guest.NamePasswordAuthentication(
                username=credentials['windows']['username'],
                password=credentials['windows']['password']
            )

            pm = content.guestOperationsManager.processManager

            # Test commands
            commands = [
                # OS Version
                ('ver > C:\\Windows\\Temp\\os_ver.txt', 'os_ver.txt', "OS Version"),
                
                # Cortex Service Status
                ('sc query cyserver > C:\\Windows\\Temp\\cortex.txt', 'cortex.txt', "Cortex Status"),
                
                # VR Service Status
                ('sc query vrevo > C:\\Windows\\Temp\\vr.txt', 'vr.txt', "VR Status"),
                
                # Update Target Group
                ('reg query "HKLM\\Software\\Policies\\Microsoft\\Windows\\WindowsUpdate" > C:\\Windows\\Temp\\update.txt', 'update.txt', "Update Settings"),
                
                # SSL/TLS Settings
                ('reg query "HKLM\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\SCHANNEL\\Protocols\\SSL 3.0\\Client" > C:\\Windows\\Temp\\ssl.txt', 'ssl.txt', "SSL Settings"),
                ('reg query "HKLM\\SYSTEM\\CurrentControlSet\\Control\\SecurityProviders\\SCHANNEL\\Protocols\\TLS 1.1\\Client" > C:\\Windows\\Temp\\tls.txt', 'tls.txt', "TLS Settings")
            ]

            print("\n2. Executing commands and collecting data...")
            results = {}
            
            for cmd, output_file, description in commands:
                try:
                    print(f"\n   Testing {description}...")
                    # Execute command
                    spec = vim.vm.guest.ProcessManager.ProgramSpec(
                        programPath="C:\\Windows\\System32\\cmd.exe",
                        arguments=f"/c {cmd}"
                    )
                    pid = pm.StartProgram(vm=vm, auth=creds, spec=spec)
                    time.sleep(1)  # Wait for command to complete

                    # Read output
                    try:
                        fm = content.guestOperationsManager.fileManager
                        file_transfer = fm.InitiateFileTransferFromGuest(
                            vm=vm,
                            auth=creds,
                            guestFilePath=f"C:\\Windows\\Temp\\{output_file}"
                        )
                        
                        if file_transfer:
                            response = requests.get(file_transfer.url, verify=False)
                            results[description] = response.text
                            print(f"   ? Success - Output:")
                            print("   " + "\n   ".join(response.text.splitlines()))
                        else:
                            print("   ? No output file")
                    
                    except vim.fault.FileNotFound:
                        print(f"   ? Output file not found: {output_file}")
                    except Exception as e:
                        print(f"   ? Error reading output: {str(e)}")

                except Exception as e:
                    print(f"   ? Command execution failed: {str(e)}")

            # Cleanup
            print("\n3. Cleaning up temporary files...")
            cleanup_cmd = "del /F /Q "
            for _, output_file, _ in commands:
                cleanup_cmd += f"C:\\Windows\\Temp\\{output_file} "
            
            cleanup_spec = vim.vm.guest.ProcessManager.ProgramSpec(
                programPath="C:\\Windows\\System32\\cmd.exe",
                arguments=f"/c {cleanup_cmd}"
            )
            pm.StartProgram(vm=vm, auth=creds, spec=cleanup_spec)
            print("   ? Cleanup completed")

            Disconnect(si)
            print("\n   ? Disconnected from vCenter")

        except Exception as e:
            print(f"   ? Error: {str(e)}")

def main():
    """Main test function"""
    print("=== Starting VM Connection Tests ===")
    app = create_app()
    
    with app.app_context():
        try:
            print("\nGetting credentials...")
            credentials = credentials_manager.get_credentials()
            print("? Credentials retrieved")
            
            test_vm_connection(credentials)
            
        except Exception as e:
            print(f"ERROR: {str(e)}")
            raise

if __name__ == "__main__":
    main()