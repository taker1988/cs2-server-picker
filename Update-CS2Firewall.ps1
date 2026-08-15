# ADJUST HERE: IP/Domain and Port of your Docker Host
$UrlBlocklist = "http://YOUR_DOCKER_IP:8115/blocklist.txt" 
$UrlSummary = "http://YOUR_DOCKER_IP:8115/summary.json" 

# ADJUST HERE: Directory for log files (must exist)
$LogDir = "C:\Users\YourUser\Documents" 

$RuleName = "CS2_Server_Blocker"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = "$LogDir\CS2_Firewall_Update_$Timestamp.log"

Function Write-Log {
    param ([string]$Message)
    $LogTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$LogTime] $Message"
}

try {
    Write-Log "Starting CS2 firewall rules update..."
    $BlockList = Invoke-RestMethod -Uri $UrlBlocklist
    $Ips = $BlockList -split "`n" | Where-Object { $_.Trim() -ne "" }
    
    try {
        $Summary = Invoke-RestMethod -Uri $UrlSummary
        Write-Log "Allowed regions: $($Summary.allowed -join ', ')"
        foreach ($Region in $Summary.blocked.PSObject.Properties) {
            Write-Log "Blocking region: $($Region.Name) ($($Region.Value) IPs)"
        }
    } catch {
        Write-Log "Could not fetch server summary."
    }
    
    if ($Ips.Count -gt 0) {
        Write-Log "Deleting old firewall rule '$RuleName' (if exists)..."
        netsh advfirewall firewall delete rule name=$RuleName | Out-Null
        
        Write-Log "Creating new firewall rules for $($Ips.Count) IPs..."
        $ChunkSize = 150
        for ($i = 0; $i -lt $Ips.Count; $i += $ChunkSize) {
            $EndIndex = [math]::Min($i + $ChunkSize - 1, $Ips.Count - 1)
            $Chunk = $Ips[$i..$EndIndex] -join ","
            netsh advfirewall firewall add rule name=$RuleName dir=out action=block remoteip=$Chunk | Out-Null
        }
        Write-Log "Process completed. $($Ips.Count) IPs processed."
    } else {
        Write-Log "Warning: No IPs received from container."
    }
} catch {
    Write-Log "Error fetching IP list from Docker container: $($_.Exception.Message)"
}
Write-Log "--------------------------------------------------"

# Rotate log files (keep max 5)
$LogFiles = Get-ChildItem -Path $LogDir -Filter "CS2_Firewall_Update_*.log" | Sort-Object CreationTime -Descending
if ($LogFiles.Count -gt 5) {
    $FilesToDelete = $LogFiles | Select-Object -Skip 5
    foreach ($File in $FilesToDelete) {
        Remove-Item -Path $File.FullName -Force
    }
}
