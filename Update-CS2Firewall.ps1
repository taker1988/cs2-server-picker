# HIER ANPASSEN: IP/Domain und Port des Docker-Hosts eintragen.
$UrlBlocklist = "http://192.168.178.123:8115/blocklist.txt" 
$UrlSummary = "http://192.168.178.123:8115/summary.json" 

# HIER ANPASSEN: Gewuenschter Pfad fuer die Log-Dateien. Ordner muss existieren.
$LogDir = "C:\Users\DeinNutzer\Documents" 

$RuleName = "CS2_Server_Blocker"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = "$LogDir\CS2_Firewall_Update_$Timestamp.log"

Function Write-Log {
    param ([string]$Message)
    $LogTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$LogTime] $Message"
}

try {
    Write-Log "Starte Aktualisierung der CS2 Firewall-Regeln..."
    $BlockList = Invoke-RestMethod -Uri $UrlBlocklist
    $Ips = $BlockList -split "`n" | Where-Object { $_.Trim() -ne "" }
    
    try {
        $Summary = Invoke-RestMethod -Uri $UrlSummary
        Write-Log "Erlaubte Server-Regionen: $($Summary.allowed -join ', ')"
        foreach ($Region in $Summary.blocked.PSObject.Properties) {
            Write-Log "Blockiere Region: $($Region.Name) ($($Region.Value) IPs)"
        }
    } catch {
        Write-Log "Konnte Server-Zusammenfassung nicht abrufen."
    }
    
    if ($Ips.Count -gt 0) {
        Write-Log "Loesche alte Firewall-Regel '$RuleName' (falls vorhanden)..."
        netsh advfirewall firewall delete rule name=$RuleName | Out-Null
        
        Write-Log "Erstelle neue Firewall-Regeln fuer $($Ips.Count) IPs..."
        $ChunkSize = 150
        for ($i = 0; $i -lt $Ips.Count; $i += $ChunkSize) {
            $EndIndex = [math]::Min($i + $ChunkSize - 1, $Ips.Count - 1)
            $Chunk = $Ips[$i..$EndIndex] -join ","
            netsh advfirewall firewall add rule name=$RuleName dir=out action=block remoteip=$Chunk | Out-Null
        }
        Write-Log "Vorgang erfolgreich abgeschlossen. $($Ips.Count) IPs verarbeitet."
    } else {
        Write-Log "Warnung: Keine IPs vom Container empfangen."
    }
} catch {
    Write-Log "Fehler beim Abrufen der IP-Liste vom Docker-Container: $($_.Exception.Message)"
}
Write-Log "--------------------------------------------------"

# Log-Dateien rotieren (maximal 5 behalten)
$LogFiles = Get-ChildItem -Path $LogDir -Filter "CS2_Firewall_Update_*.log" | Sort-Object CreationTime -Descending
if ($LogFiles.Count -gt 5) {
    $FilesToDelete = $LogFiles | Select-Object -Skip 5
    foreach ($File in $FilesToDelete) {
        Remove-Item -Path $File.FullName -Force
    }
}
