# SQL and database paths
$SqlitePath = "C:\Docker\infraweb\data\sqlite3.exe"
$DatabasePath = "C:\Docker\infraweb\data\audit_reports.db"
$LogPath = "C:\Docker\infraweb\logs\users_update.log"

# File paths
$ProdCsvPath = "C:\Docker\tempReports\Users_Groups\users_and_groups_prod.csv"
$DevCsvNetworkPath = "\\10.71.4.23\WSUSTemp\users_and_groups_dev.csv"
$DevCsvLocalPath = "C:\Docker\tempReports\Users_Groups\users_and_groups_dev.csv"

function Write-Log {
    param($Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] $Message"
    Write-Host $logMessage
    Add-Content -Path $LogPath -Value $logMessage
}

function Clear-RedisCache {
    try {
        $pythonScript = @"
import redis
r = redis.Redis(host='localhost', port=6379, db=0)
cache_keys = r.keys('*users*')
for key in cache_keys:
    r.delete(key)
r.delete('dashboard')  # Also clear dashboard cache as it might show user counts
"@
        
        # Save the Python script to a temporary file
        $tempFile = Join-Path $env:TEMP "clear_cache.py"
        $pythonScript | Set-Content $tempFile

        # Execute the Python script using the virtual environment's Python
        $pythonPath = "C:\Docker\infraweb\venv\Scripts\python.exe"
        & $pythonPath $tempFile

        Remove-Item $tempFile -Force
        Write-Log "Cache cleared successfully"
        return $true
    }
    catch {
        Write-Log ("Error clearing cache: " + $_.Exception.Message)
        return $false
    }
}

function Update-DatabaseFromCsv {
    param (
        [string]$CsvPath,
        [string]$TableName
    )
    
    try {
        Write-Log ("Starting database update for " + $TableName)
        $tempSqlFile = Join-Path $env:TEMP ("users_update_" + $TableName + ".sql")
        
        @"
BEGIN TRANSACTION;
DELETE FROM $TableName;
"@ | Set-Content $tempSqlFile

        $users = Import-Csv -Path $CsvPath
        foreach ($user in $users) {
            $creationDate = if ($user.CreationDate) {
                [DateTime]::Parse($user.CreationDate).ToString("yyyy-MM-dd HH:mm:ss")
            } else { "NULL" }
            
            $lastLogin = if ($user.LastLogin) {
                [DateTime]::Parse($user.LastLogin).ToString("yyyy-MM-dd HH:mm:ss")
            } else { "NULL" }
            
            $enabled = if ($user.Enabled -eq "True") { "1" } else { "0" }
            
            $insertSql = @"
INSERT INTO $TableName (Name, Samaccountname, Role, Enabled, CreationDate, LastLogin)
VALUES ('$($user.Name -replace "'", "''")','$($user.Samaccountname -replace "'", "''")','$($user.Role -replace "'", "''")',
$enabled,$(if ($creationDate -eq "NULL") { "NULL" } else { "'$creationDate'" }),$(if ($lastLogin -eq "NULL") { "NULL" } else { "'$lastLogin'" }));
"@
            Add-Content -Path $tempSqlFile -Value $insertSql
        }

        Add-Content -Path $tempSqlFile -Value "COMMIT;"
        $result = & $SqlitePath $DatabasePath ".read $tempSqlFile"
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log ("Successfully updated " + $TableName + " table")
            Remove-Item -Path $tempSqlFile -Force
            return $true
        } else {
            Write-Log ("SQLite returned error code: " + $LASTEXITCODE)
            return $false
        }
    }
    catch {
        Write-Log ("Error updating " + $TableName + ": " + $_.Exception.Message)
        if (Test-Path $tempSqlFile) {
            Remove-Item -Path $tempSqlFile -Force
        }
        return $false
    }
}

try {
    Write-Log "Starting user update process"

    # Get production domain users
    Write-Log "Collecting production domain users"
    $Groups = Get-ADGroup -Filter "name -notlike 'Domain Users' -and name -notlike 'Domain Computers'" | 
             Select-Object -ExpandProperty Name

    $UserGroups = @{}

    foreach ($group in $Groups) {
        try {
            $Arrayofmembers = Get-ADGroupMember -Identity $group -Recursive -ErrorAction SilentlyContinue | 
                             Get-ADUser -Properties * -ErrorAction SilentlyContinue | 
                             Where-Object { $_.Enabled -eq $true }
            
            if ($Arrayofmembers) {
                foreach ($member in $Arrayofmembers) {
                    if (-not $UserGroups.ContainsKey($member.SamAccountName)) {
                        $UserGroups[$member.SamAccountName] = [PSCustomObject]@{
                            Name = $member.Name
                            SAMAccountName = $member.SamAccountName
                            Groups = @($group)
                            Enabled = $member.Enabled
                            CreationDate = $member.WhenCreated
                            LastLogin = $member.LastLogonDate
                        }
                    } else {
                        $UserGroups[$member.SamAccountName].Groups += $group
                    }
                }
            }
        }
        catch {
            Write-Log ("Skipping group $group : " + $_.Exception.Message)
            continue
        }
    }

    # Export production users to CSV
    Write-Log ("Exporting " + $UserGroups.Count + " production users to CSV")
    $UserGroups.Values | ForEach-Object {
        [PSCustomObject]@{
            Name = $_.Name
            'Samaccountname' = $_.SAMAccountName
            Role = ($_.'Groups' -join ", ")
            Enabled = $_.Enabled
            'CreationDate' = $_.CreationDate
            'LastLogin' = $_.LastLogin
        }
    } | Export-Csv $ProdCsvPath -NoTypeInformation

    # Wait for dev domain CSV file
    Write-Log "Waiting for development domain CSV file"
    $retryCount = 0
    $maxRetries = 12

    while (-not (Test-Path $DevCsvNetworkPath)) {
        if ($retryCount -ge $maxRetries) {
            throw "Development domain CSV file not found after timeout"
        }
        Start-Sleep -Seconds 5
        $retryCount++
        Write-Log ("Waiting for dev CSV file... Attempt " + $retryCount + " of " + $maxRetries)
    }

    Write-Log "Copying development CSV file locally"
    Copy-Item -Path $DevCsvNetworkPath -Destination $DevCsvLocalPath -Force

    # Clear Redis cache before updating database
    Write-Log "Clearing Redis cache"
    Clear-RedisCache

    $prodSuccess = Update-DatabaseFromCsv -CsvPath $ProdCsvPath -TableName "prod_users"
    $devSuccess = Update-DatabaseFromCsv -CsvPath $DevCsvLocalPath -TableName "dev_users"

    # Cleanup
    Write-Log "Cleaning up CSV files"
    if (Test-Path $ProdCsvPath) {
        Remove-Item -Path $ProdCsvPath -Force
        Write-Log "Deleted: Production CSV"
    }
    if (Test-Path $DevCsvLocalPath) {
        Remove-Item -Path $DevCsvLocalPath -Force
        Write-Log "Deleted: Local Dev CSV"
    }
    if (Test-Path $DevCsvNetworkPath) {
        Remove-Item -Path $DevCsvNetworkPath -Force
        Write-Log "Deleted: Network Dev CSV"
    }

    Write-Log ("Process completed - Prod: " + $prodSuccess + ", Dev: " + $devSuccess)
}
catch {
    Write-Log ("CRITICAL ERROR: " + $_.Exception.Message)
    if (Test-Path $ProdCsvPath) { Remove-Item -Path $ProdCsvPath -Force }
    if (Test-Path $DevCsvLocalPath) { Remove-Item -Path $DevCsvLocalPath -Force }
    throw
}