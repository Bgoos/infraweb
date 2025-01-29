# Define the API URL and credentials
$apiUrl = "https://cha-infraweb-11.csmodule.com/api/virtual_machines"
$cred = Get-Credential

# Fetch the list of VMs from the API
$vms = Invoke-RestMethod -Uri $apiUrl -Method Get

# Load SQLite Assembly Manually
$assemblyPath = "C:\path\to\System.Data.SQLite.dll"  # Update this path to point to the correct SQLite DLL
if (-Not (Get-Module -Name SQLite)) {
    [System.Reflection.Assembly]::LoadFrom($assemblyPath) | Out-Null
}

# Establish connection to SQLite database
$databasePath = "C:\Docker\audit-reports-app\data\audit_reports.db"
$connectionString = "Data Source=$databasePath;Version=3;"
$connection = New-Object System.Data.SQLite.SQLiteConnection($connectionString)
$connection.Open()

# Iterate through each VM, collect required details and update the database
foreach ($vm in $vms) {
    if ($vm.state -eq "poweredOn" -and $vm.os -match "Microsoft Windows") {
        # Gathering VM details
        $vmName = $vm.vm_name
        $diskSize = $vm.size_gb
        $site = $vm.site
        $firstIPv4Address = $vm.ip
        $nicType = $vm.nic
        $state = $vm.state
        $vmToolsVersion = $vm.vm_tools
        $vmHardwareVersion = $vm.vm_version
        
        # Invoke commands on the VM via WinRM to gather additional information
        try {
            $sessionOptions = New-PSSessionOption -SkipCACheck -SkipCNCheck -OperationTimeoutSec 180
            $vmSession = New-PSSession -ComputerName $firstIPv4Address -Credential $cred -Authentication Default -SessionOption $sessionOptions -ErrorAction Stop
            
            $script = {
                Function lastlogin {
                    $loginProfiles = Get-WmiObject -Class Win32_NetworkLoginProfile
                    $recentLogin = $loginProfiles | Where-Object {
                        $_.Name -notmatch 'NT AUTHORITY\\SYSTEM' -and
                        $_.Name -notmatch 'NT AUTHORITY\\LOCAL SERVICE' -and
                        $_.Name -notlike '*$'
                    } | Sort-Object -Property LastLogon -Descending | Select-Object -First 1

                    if ($recentLogin) {
                        try {
                            $convertedDate = [Management.ManagementDateTimeConverter]::ToDateTime($recentLogin.LastLogon)
                            $formattedDate = $convertedDate.ToString('yyyy-MM-dd HH:mm:ss')
                            return @{ 'Name' = $recentLogin.Name; 'LastLogonDate' = $formattedDate }
                        }
                        catch {
                            return @{ 'Name' = $recentLogin.Name; 'LastLogonDate' = "Conversion Failed" }
                        }
                    }
                    else {
                        return @{ 'Name' = $null; 'LastLogonDate' = $null }
                    }
                }

                $cortex = Get-Service -Name 'cyserver' -ErrorAction SilentlyContinue
                $velociraptor = Get-Service -Name 'vrevo' -ErrorAction SilentlyContinue
                $updateTG = (Get-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate' -ErrorAction SilentlyContinue).TargetGroup
                $lastLoginInfo = lastlogin

                return @{
                    'CortexInstalled' = $cortex -ne $null
                    'VRInstalled' = $velociraptor -ne $null
                    'UpdateTG' = $updateTG
                    'LastLoginUser' = $lastLoginInfo['Name']
                    'LastLoginDate' = $lastLoginInfo['LastLogonDate']
                } | ConvertTo-Json -Compress
            }
            
            $scriptOutput = Invoke-Command -Session $vmSession -ScriptBlock $script -ErrorAction Stop
            $scriptOutputData = $scriptOutput | ConvertFrom-Json
        }
        catch {
            Write-Error "Failed to connect to VM $vmName at IP $firstIPv4Address"
            continue
        }
        finally {
            if ($vmSession) {
                Remove-PSSession -Session $vmSession
            }
        }
        
        # Preparing SQL Update Command
        $updateCommand = $connection.CreateCommand()
        $updateCommand.CommandText = @"
            UPDATE windows_vms 
            SET 
                Size = @Size,
                Site = @Site,
                IP = @IP,
                NICType = @NICType,
                State = @State,
                VMToolsVersion = @VMToolsVersion,
                VMHardwareVersion = @VMHardwareVersion,
                Cortex = @Cortex,
                VR = @VR,
                UpdateTG = @UpdateTG,
                Notes = @Notes
            WHERE VMName = @VMName;
"@

        # Adding parameters to prevent SQL injection
        $updateCommand.Parameters.Add((New-Object System.Data.SQLite.SQLiteParameter("@VMName", [System.Data.DbType]::String) { Value = $vmName }))
        $updateCommand.Parameters.Add((New-Object System.Data.SQLite.SQLiteParameter("@Size", [System.Data.DbType]::Double) { Value = $diskSize }))
        $updateCommand.Parameters.Add((New-Object System.Data.SQLite.SQLiteParameter("@Site", [System.Data.DbType]::String) { Value = $site }))
        $updateCommand.Parameters.Add((New-Object System.Data.SQLite.SQLiteParameter("@IP", [System.Data.DbType]::String) { Value = $firstIPv4Address }))
        $updateCommand.Parameters.Add((New-Object System.Data.SQLite.SQLiteParameter("@NICType", [System.Data.DbType]::String) { Value = $nicType }))
        $updateCommand.Parameters.Add((New-Object System.Data.SQLite.SQLiteParameter("@State", [System.Data.DbType]::String) { Value = $state }))
        $updateCommand.Parameters.Add((New-Object System.Data.SQLite.SQLiteParameter("@VMToolsVersion", [System.Data.DbType]::String) { Value = $vmToolsVersion }))
        $updateCommand.Parameters.Add((New-Object System.Data.SQLite.SQLiteParameter("@VMHardwareVersion", [System.Data.DbType]::String) { Value = $vmHardwareVersion }))
        $updateCommand.Parameters.Add((New-Object System.Data.SQLite.SQLiteParameter("@Cortex", [System.Data.DbType]::Boolean) { Value = [System.Convert]::ToBoolean($scriptOutputData.CortexInstalled) }))
        $updateCommand.Parameters.Add((New-Object System.Data.SQLite.SQLiteParameter("@VR", [System.Data.DbType]::Boolean) { Value = [System.Convert]::ToBoolean($scriptOutputData.VRInstalled) }))
        $updateCommand.Parameters.Add((New-Object System.Data.SQLite.SQLiteParameter("@UpdateTG", [System.Data.DbType]::String) { Value = $scriptOutputData.UpdateTG }))
        $updateCommand.Parameters.Add((New-Object System.Data.SQLite.SQLiteParameter("@Notes", [System.Data.DbType]::String) { Value = $vm.notes }))

        # Execute the SQL Update Command
        try {
            $updateCommand.ExecuteNonQuery() | Out-Null
            Write-Host "Successfully updated VM $vmName in the database."
        }
        catch {
            Write-Error "Failed to update database for VM $vmName"
        }
    }
}

# Close the database connection
$connection.Close()
