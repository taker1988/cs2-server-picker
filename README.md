# CS2 Server Picker (Docker Backend + Windows/Linux Client)

[English Version](#english-version) | [Deutsche Version](#deutsche-version)

---

## English Version

Automated setup to enforce Counter-Strike 2 (CS2) matchmaking on specific server regions (e.g., Frankfurt only) by blocking unwanted IP ranges via the local firewall. This works for solo queuing as well as full lobbies.

**Background:** When starting a match search, the game pings all available servers to find the "best" one. If only one player (who runs this script) blocks all other regions, the entire lobby will be routed to the remaining allowed server.

**Important Notice:** The scripts use a placeholder for the IP and Port `8115`. **Adjust the IP and Port in all scripts** to match your actual Docker host environment.

### Architecture

1. **Docker Container (Backend):** Queries the official Valve API (`GetSDRConfig`) hourly for Steam Datagram Relay (SDR) servers. Filters them based on a Whitelist (`ALLOW_REGIONS`) or Blacklist (`BLOCK_REGIONS`) and serves a `blocklist.txt` via a lightweight HTTP server. The backend runs as a pre-built Docker image.
2. **Windows/Linux Client:** Runs on a schedule (every 6 hours), downloads the list, and updates the local firewall (`netsh` for Windows, `iptables` for Linux) to block the IPs. Keeps a rotating log of the last 5 executions.

---

### Part 1: Docker Backend Setup

The container runs isolated and generates `blocklist.txt` and `summary.json`. Since the image is hosted on Docker Hub, you only need to deploy the `docker-compose.yml` stack.

Deploy the following stack (e.g., via Portainer). Adjust paths, variables, and ports to fit your host environment.

```yaml
services:
  cs2-server-picker:
    image: taker1988/cs2-server-picker:latest
    container_name: cs2-server-picker
    restart: always
    security_opt:
      - no-new-privileges:true
    environment:
      - TZ=Europe/Berlin
      - ALLOW_REGIONS=fra # ADJUST HERE: Whitelist (e.g., fra). Blocks everything else if set.
      - BLOCK_REGIONS=ams,atl,dfw,dxb,eze,gru,gum,hkg,iad,jnb,lax,lhr,lim,mad,ord,par,scl,sea,seo,sgp,sto,syd,tyo,vie,waw,bom2,maa2,sto2,ctum,pekm,pvgm,tgdm,ctut,pekt,pvgt,tgdt,ctuu,peku,pvgu,tgdu # ADJUST HERE: Blacklist. Only active if ALLOW_REGIONS is empty.
    volumes:
      - /volume2/docker/cs2-server-picker/html:/app/html # ADJUST HERE: Local host path for the generated text files
    ports:
      - "8115:8000" # ADJUST HERE: External port
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/blocklist.txt"]
      interval: 1m
      timeout: 10s
      retries: 3
```

---

### Part 2: Windows Client Setup

1. Save the following code as `Update-CS2Firewall.ps1`.
2. Adjust `$UrlBlocklist`, `$UrlSummary`, and `$LogDir`.

```powershell
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
        $Summary = Invoke-RestMethod -Uri$UrlSummary
        Write-Log "Allowed regions: $($Summary.allowed -join ', ')"
        foreach ($Region in$Summary.blocked.PSObject.Properties) {
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
        for ($i = 0; $i -lt$Ips.Count; $i +=$ChunkSize) {
            $EndIndex = [math]::Min($i + $ChunkSize - 1,$Ips.Count - 1)
            $Chunk =$Ips[$i..$EndIndex] -join ","
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
$LogFiles = Get-ChildItem -Path$LogDir -Filter "CS2_Firewall_Update_*.log" | Sort-Object CreationTime -Descending
if ($LogFiles.Count -gt 5) {
    $FilesToDelete =$LogFiles | Select-Object -Skip 5
    foreach ($File in$FilesToDelete) {
        Remove-Item -Path $File.FullName -Force
    }
}
```

**Task Scheduler Automation:**
* Open Task Scheduler -> *Create Task...*
* **General:** Name it, check **Run with highest privileges**.
* **Triggers:** New -> Daily -> Repeat task every 6 hours.
* **Actions:** Start a program -> `powershell.exe`. Arguments: `-ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\YourUser\Documents\Update-CS2Firewall.ps1"` **(Adjust path!)**

---

### Part 3: Linux Client Setup

**Prerequisites:** Install `jq` and `iptables`. (e.g., `sudo pacman -S jq iptables` or `sudo apt install jq iptables`).

1. Save the following script as `/usr/local/bin/update-cs2firewall.sh`. Adjust the `URL` variables and `$LOG_DIR`.

```bash
#!/bin/bash

# ADJUST HERE: IP/Domain and Port of your Docker Host
URL_BLOCKLIST="http://YOUR_DOCKER_IP:8115/blocklist.txt" 
URL_SUMMARY="http://YOUR_DOCKER_IP:8115/summary.json" 

# ADJUST HERE: Directory for log files
LOG_DIR="/var/log/cs2_firewall" 

CHAIN_NAME="CS2_BLOCK"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/cs2_firewall_log_$TIMESTAMP.log"

if [ "$EUID" -ne 0 ]; then
  echo "Error: Please run as root."
  exit 1
fi

mkdir -p "$LOG_DIR"

write_log() {
    local MESSAGE="$1"
    local LOG_TIME=$(date +"%Y-%m-%d %H:%M:%S")
    echo "[$LOG_TIME] $MESSAGE" >> "$LOG_FILE"
}

write_log "Starting CS2 firewall rules update..."

IPS=$(curl -s "$URL_BLOCKLIST")
if [ -z "$IPS" ]; then
    write_log "Error fetching IP list from Docker container."
    exit 1
fi

SUMMARY=$(curl -s "$URL_SUMMARY")
if [ -n "$SUMMARY" ] && command -v jq >/dev/null 2>&1; then
    ALLOWED=$(echo "$SUMMARY" | jq -r '.allowed | join(", ")')
    write_log "Allowed regions: $ALLOWED"
    
    echo "$SUMMARY" | jq -r '.blocked | to_entries | .[] | "Blocking region: \(.key) (\(.value) IPs)"' | while read -r line; do
        write_log "$line"
    done
else
    write_log "Could not fetch server summary or 'jq' is not installed."
fi

write_log "Deleting old iptables rules '$CHAIN_NAME' (if exists)..."
iptables -D OUTPUT -j $CHAIN_NAME 2>/dev/null
iptables -F $CHAIN_NAME 2>/dev/null
iptables -X $CHAIN_NAME 2>/dev/null

IP_COUNT=0
if [ -n "$IPS" ]; then
    iptables -N $CHAIN_NAME
    iptables -A OUTPUT -j $CHAIN_NAME
    
    for ip in $IPS; do
        if [[ $ip =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            iptables -A $CHAIN_NAME -d$ip -j DROP
            ((IP_COUNT++))
        fi
    done
    write_log "Process completed. $IP_COUNT IPs processed."
else
    write_log "Warning: No IPs received from container."
fi

write_log "--------------------------------------------------"

# Rotate log files (keep max 5)
ls -t "$LOG_DIR"/cs2_firewall_log_*.log 2>/dev/null | tail -n +6 | xargs -r rm -f
