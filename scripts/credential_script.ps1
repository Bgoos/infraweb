param (
    [Parameter(Mandatory=$true)]
    [string]$VCenterPasswordId,
    
    [Parameter(Mandatory=$true)]
    [string]$WindowsPasswordId
)


$IPs =  Resolve-DnsName internal-tpm-production-ALB-660013560.eu-central-1.elb.amazonaws.com
$hostname = "tpm.evolution.com"


    # Path to the hosts file
    $hostsFilePath = "C:\Windows\System32\drivers\etc\hosts"
$existingEntries = Get-Content -Path $hostsFilePath

 # Define the entry to add to the hosts file
foreach ($IPad in $IPs){

$entry1 = $IPad.IPAddress +"   " + $hostname
    if ($existingEntries -notcontains $entry1) {
        # Add the entry to the hosts file
        Add-Content -Path $hostsFilePath -Value $entry1
        Write-Output "Added entry to hosts file: $entry1"
    } 

}



    # Create the entry line
    $entry = "$ipAddress `t $hostname"
    
    # Check if the entry already exists
    $existingEntries = Get-Content -Path $hostsFilePath
    if ($existingEntries -notcontains $entry) {
        # Add the entry to the hosts file
        Add-Content -Path $hostsFilePath -Value $entry1
        Write-Output "Added entry to hosts file: $entry1"
    } 
        if ($existingEntries -notcontains $entry2) {
        # Add the entry to the hosts file
        Add-Content -Path $hostsFilePath -Value $entry2
        Write-Output "Added entry to hosts file: $entry2"
    } 


sleep 4

function Invoke-TPMApi {
    param (
        [string]$Endpoint,
        [string]$Method = "GET",
        [string]$Body
    )

    $credkey = Get-StoredCredential -Target "TPMAPIKeys"
    $publicKey = $credkey.UserName
    $privateKey = $credkey.GetNetworkCredential().Password

    $baseUrl = "https://tpm.evolution.com/tpm/index.php"
    $url = "$baseUrl/api/v4/$Endpoint"
    

    Write-Host "Calling API: $Method $url"

    $timestamp = [int][double]::Parse((Get-Date (Get-Date).ToUniversalTime() -UFormat %s))
    
    $unhashed = "api/v4/$Endpoint$timestamp$Body"
    Write-Host "Unhashed string: $unhashed"

    $hmacsha256 = New-Object System.Security.Cryptography.HMACSHA256
    $hmacsha256.Key = [System.Text.Encoding]::UTF8.GetBytes($privateKey)
    $hash = [System.BitConverter]::ToString($hmacsha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($unhashed))).Replace("-", "").ToLower()

    Write-Host "Generated hash: $hash"

    $headers = @{
        "Content-Type" = "application/json; charset=utf-8"
        "X-Public-Key" = $publicKey
        "X-Request-Hash" = $hash
        "X-Request-Timestamp" = $timestamp
    }

    Write-Host "Headers:"
    $headers.GetEnumerator() | ForEach-Object { Write-Host "$($_.Key): $($_.Value)" }

    $params = @{
        Uri = $url
        Method = $Method
        Headers = $headers
    }

    if ($Body) {
        $params.Body = $Body
        Write-Host "Request Body: $Body"
    }

    try {
        $response = Invoke-RestMethod @params
        return $response
    }
    catch {
        Write-Host "Error calling API: $_"
        Write-Host "Status Code: $($_.Exception.Response.StatusCode)"
        Write-Host "Status Description: $($_.Exception.Response.StatusDescription)"
        if ($_.Exception.Response) {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $reader.BaseStream.Position = 0
            $reader.DiscardBufferedData()
            $responseBody = $reader.ReadToEnd()
            Write-Host "Response body: $responseBody"
        }
        throw
    }
}

function Get-TPMCredentialById {
    param (
        [Parameter(Mandatory=$true)]
        [int]$PasswordId
    )

    $endpoint = "passwords/$PasswordId.json"
    $response = Invoke-TPMApi -Endpoint $endpoint

    if ($response -and $response.username -and $response.password) {
        $securePassword = ConvertTo-SecureString $response.password -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ($response.username, $securePassword)
        Write-Host "Credential object created for username: $($response.username)"
        #return $credential
         $inspass = $response.password
        return $inspass
     
    }
    else {
        Write-Host "No valid password entry found with ID: $PasswordId"
        return $null
    }
}

$vcenterCred = "" | select UserName, Password
$windowsCred = "" | select UserName, Password

$vcenterCred.username = "svc_veeam@vsphere.local"
$vcenterCred.password = Get-TPMCredentialById -PasswordId $VCenterPasswordId
$windowsCred.UserName = "svc_veeam_dc"
$windowsCred.Password = Get-TPMCredentialById -PasswordId $WindowsPasswordId
$credentials = @{
    vcenter = @{
        username = $vcenterCred.UserName
        password = $vcenterCred.Password
    }
    windows = @{
        username = $windowsCred.UserName
        password = $windowsCred.Password
    }
}

$credentialsJson = $credentials | ConvertTo-Json
Write-Output $credentialsJson