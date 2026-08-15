CS2 Server Picker (Docker Backend + Windows/Linux Client)

English Version | Deutsche Version
English Version

Automated setup to enforce Counter-Strike 2 (CS2) matchmaking on specific server regions (e.g., Frankfurt only) by blocking unwanted IP ranges via the local firewall. This works for solo queuing as well as full lobbies.

Background: When starting a match search, the game pings all available servers to find the "best" one. If only one player (who runs this script) blocks all other regions, the entire lobby will be routed to the remaining allowed server.

Important Notice: The scripts use 192.168.178.123 and Port 8115 as placeholders. Adjust the IP and Port in all scripts to match your actual Docker host environment.
Architecture

    Docker Container (Backend): Queries the official Valve API (GetSDRConfig) hourly for Steam Datagram Relay (SDR) servers. Filters them based on a Whitelist (ALLOW_REGIONS) or Blacklist (BLOCK_REGIONS) and serves a blocklist.txt via a lightweight HTTP server.

    Windows/Linux Client: Runs on a schedule (every 6 hours), downloads the list, and updates the local firewall (netsh for Windows, iptables for Linux) to block the IPs. Keeps a rotating log of the last 5 executions.

Part 1: Docker Backend Setup

The container runs isolated and generates blocklist.txt and summary.json.
1. Python Script

Create a directory on your host (e.g., /volume2/docker_nvme/cs2-server-picker/app/) and place this generate.py file inside:
import json
import urllib.request
import time
import os

# Internal container paths
SDR_URL = "https://api.steampowered.com/ISteamApps/GetSDRConfig/v1/?appid=730"
OUTPUT_FILE = "/app/html/blocklist.txt"
SUMMARY_FILE = "/app/html/summary.json"

def update_list():
    allow_env = os.environ.get("ALLOW_REGIONS", "").strip()
    block_env = os.environ.get("BLOCK_REGIONS", "").strip()
    
    allowed_pops = [p.strip() for p in allow_env.split(",") if p.strip()]
    blocked_pops = [p.strip() for p in block_env.split(",") if p.strip()]

    try:
        req = urllib.request.Request(SDR_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        ips_to_block = []
        summary = {"allowed": [], "blocked": {}}
        
        for pop_code, details in data.get("pops", {}).items():
            block_this_pop = False
            
            if allowed_pops:
                if pop_code not in allowed_pops:
                    block_this_pop = True
            elif blocked_pops:
                if pop_code in blocked_pops:
                    block_this_pop = True
            
            desc = details.get("desc", pop_code)
            if block_this_pop:
                relays = details.get("relays", [])
                ipv4_list = [r["ipv4"] for r in relays if "ipv4" in r]
                ips_to_block.extend(ipv4_list)
                if ipv4_list:
                    summary["blocked"][desc] = len(ipv4_list)
            else:
                summary["allowed"].append(desc)
        
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        
        with open(OUTPUT_FILE, "w") as f:
            f.write("\n".join(ips_to_block))
            
        with open(SUMMARY_FILE, "w") as f:
            json.dump(summary, f)
            
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] List updated. {len(ips_to_block)} IPs blocked.", flush=True)
    except Exception as e:
        print(f"Update error: {e}", flush=True)

if __name__ == "__main__":
    while True:
        update_list()
        time.sleep(3600)
        2. Docker Compose

Deploy the stack. Adjust paths, variables, and ports.
YAML

services:
  cs2-server-picker:
    image: python:3.11-alpine
    container_name: cs2-server-picker
    restart: always
    security_opt:
      - no-new-privileges:true
    environment:
      - TZ=Europe/Berlin
      - ALLOW_REGIONS=fra # ADJUST HERE: Whitelist (e.g., fra). Blocks everything else if set.
      - BLOCK_REGIONS=ams,atl,dfw,dxb,eze,gru,gum,hkg,iad,jnb,lax,lhr,lim,mad,ord,par,scl,sea,seo,sgp,sto,syd,tyo,vie,waw,bom2,maa2,sto2,ctum,pekm,pvgm,tgdm,ctut,pekt,pvgt,tgdt,ctuu,peku,pvgu,tgdu # ADJUST HERE: Blacklist. Only active if ALLOW_REGIONS is empty.
    volumes:
      - /volume2/docker_nvme/cs2-server-picker/app:/app # ADJUST HERE: Local host path
    ports:
      - "8115:8000" # ADJUST HERE: External port
    command: sh -c "python /app/generate.py & sleep 5 && python -m http.server 8000 --directory /app/html"
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/blocklist.txt"]
      interval: 1m
      timeout: 10s
      retries: 3

Part 2: Windows Client Setup

    Save the following code as Update-CS2Firewall.ps1.

    Adjust $UrlBlocklist, $UrlSummary, and $LogDir.

PowerShell

# ADJUST HERE: IP/Domain and Port of your Docker Host
$UrlBlocklist = "http://192.168.178.123:8115/blocklist.txt" 
$UrlSummary = "http://192.168.178.123:8115/summary.json" 

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

Task Scheduler Automation:

    Open Task Scheduler -> Create Task...

    General: Name it, check Run with highest privileges.

    Triggers: New -> Daily -> Repeat task every 6 hours.

    Actions: Start a program -> powershell.exe. Arguments: -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\YourUser\Documents\Update-CS2Firewall.ps1" (Adjust path!)

Part 3: Linux Client Setup

Prerequisites: Install jq and iptables. (e.g., sudo pacman -S jq iptables or sudo apt install jq iptables).

    Save the following script as /usr/local/bin/update-cs2firewall.sh. Adjust the URL variables and $LOG_DIR.

Bash

#!/bin/bash

# ADJUST HERE: IP/Domain and Port of your Docker Host
URL_BLOCKLIST="http://192.168.178.123:8115/blocklist.txt" 
URL_SUMMARY="http://192.168.178.123:8115/summary.json" 

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
            iptables -A $CHAIN_NAME -d $ip -j DROP
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

Make it executable:
Bash

sudo chmod +x /usr/local/bin/update-cs2firewall.sh

Systemd Automation:
Create the service file /etc/systemd/system/cs2-blocker.service:
Ini, TOML

[Unit]
Description=Update CS2 Firewall Rules
After=network.target

[Service]
Type=oneshot
# ADJUST HERE: Path to the executable script
ExecStart=/usr/local/bin/update-cs2firewall.sh

Create the timer file /etc/systemd/system/cs2-blocker.timer:
Ini, TOML

[Unit]
Description=Run CS2 Firewall Update every 6 hours

[Timer]
OnBootSec=5min
OnUnitActiveSec=6h

[Install]
WantedBy=timers.target

Enable and start:
Bash

sudo systemctl daemon-reload
sudo systemctl enable --now cs2-blocker.timer

Plaintext

ams = Amsterdam (Netherlands)
atl = Atlanta (USA)
bom2 = Mumbai (India)
ctum = Chengdu - Mobile (China)
ctut = Chengdu - Telecom (China)
ctuu = Chengdu - Unicom (China)
dfw = Dallas (USA)
dxb = Dubai (United Arab Emirates)
eze = Buenos Aires (Argentina)
fra = Frankfurt am Main (Germany)
gru = São Paulo (Brazil)
gum = Guam (USA)
hkg = Hong Kong (China)
iad = Sterling (USA)
jnb = Johannesburg (South Africa)
lax = Los Angeles (USA)
lhr = London (UK)
lim = Lima (Peru)
maa2 = Chennai (India)
mad = Madrid (Spain)
ord = Chicago (USA)
par = Paris (France)
pekm = Beijing - Mobile (China)
pekt = Beijing - Telecom (China)
peku = Beijing - Unicom (China)
pvgm = Shanghai - Mobile (China)
pvgt = Shanghai - Telecom (China)
pvgu = Shanghai - Unicom (China)
scl = Santiago (Chile)
sea = Seattle (USA)
seo = Seoul (South Korea)
sgp = Singapore
sto = Stockholm - Kista (Sweden)
sto2 = Stockholm - Bromma (Sweden)
syd = Sydney (Australia)
tgdm = Guangzhou - Mobile (China)
tgdt = Guangzhou - Telecom (China)
tgdu = Guangzhou - Unicom (China)
tyo = Tokyo (Japan)
vie = Vienna (Austria)
waw = Warsaw (Poland)

Deutsche Version

Automatisiertes Setup, um Counter-Strike 2 (CS2) Matchmaking auf bestimmte Serverregionen (z. B. nur Frankfurt) zu erzwingen, indem unerwünschte IP-Bereiche über die lokale Firewall blockiert werden. Funktioniert sowohl bei der Solo-Suche als auch in Lobbys mit mehreren Spielern.

Hintergrund: Beim Start der Suche für ein Match werden die Clients und Server angepingt, um den bestmöglichen Server zu finden. Blockiert der ausführende Spieler alle Regionen außer der gewünschten, wird die gesamte Lobby auf diesen verbleibenden Server gezwungen.

Wichtiger Hinweis vorab (IP und Port):
In den Skripten und Beispielen wird die IP 192.168.178.123 und der Port 8115 verwendet. Passe diese Werte in allen Skripten an, damit sie deiner Docker-Umgebung entsprechen.
Funktionsweise der Komponenten

    Docker Container (Backend): Fragt stündlich die offizielle Valve-API (GetSDRConfig) ab, welche alle Steam-Datagram-Relay (SDR) Server auflistet. Filtert die Daten basierend auf einer Whitelist (ALLOW_REGIONS) oder Blacklist (BLOCK_REGIONS) und stellt eine blocklist.txt über einen integrierten HTTP-Server bereit.

    Windows/Linux-Skript (Client): Wird per Aufgabenplanung bzw. systemd alle 6 Stunden ausgeführt. Lädt die Liste herunter und aktualisiert die lokale Firewall (netsh für Windows, iptables für Linux), um die IPs zu blockieren. Es werden rotierende Logs der letzten 5 Durchläufe gespeichert.

Teil 1: Das Docker-Backend

Der Container benötigt keine speziellen Berechtigungen, läuft isoliert und generiert die Dateien blocklist.txt und summary.json.
1. Python-Skript erstellen

Erstelle auf deinem Server den Pfad für das Volume (z.B. /volume2/docker_nvme/cs2-server-picker/app/).
Lege dort die Datei generate.py mit folgendem Inhalt an:
Python

import json
import urllib.request
import time
import os

# Interne Container-Pfade (muessen normalerweise nicht geaendert werden)
SDR_URL = "https://api.steampowered.com/ISteamApps/GetSDRConfig/v1/?appid=730"
OUTPUT_FILE = "/app/html/blocklist.txt"
SUMMARY_FILE = "/app/html/summary.json"

def update_list():
    allow_env = os.environ.get("ALLOW_REGIONS", "").strip()
    block_env = os.environ.get("BLOCK_REGIONS", "").strip()
    
    allowed_pops = [p.strip() for p in allow_env.split(",") if p.strip()]
    blocked_pops = [p.strip() for p in block_env.split(",") if p.strip()]

    try:
        req = urllib.request.Request(SDR_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        ips_to_block = []
        summary = {"allowed": [], "blocked": {}}
        
        for pop_code, details in data.get("pops", {}).items():
            block_this_pop = False
            
            if allowed_pops:
                if pop_code not in allowed_pops:
                    block_this_pop = True
            elif blocked_pops:
                if pop_code in blocked_pops:
                    block_this_pop = True
            
            desc = details.get("desc", pop_code)
            if block_this_pop:
                relays = details.get("relays", [])
                ipv4_list = [r["ipv4"] for r in relays if "ipv4" in r]
                ips_to_block.extend(ipv4_list)
                if ipv4_list:
                    summary["blocked"][desc] = len(ipv4_list)
            else:
                summary["allowed"].append(desc)
        
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        
        with open(OUTPUT_FILE, "w") as f:
            f.write("\n".join(ips_to_block))
            
        with open(SUMMARY_FILE, "w") as f:
            json.dump(summary, f)
            
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Liste aktualisiert. {len(ips_to_block)} IPs blockiert.", flush=True)
    except Exception as e:
        print(f"Fehler beim Update: {e}", flush=True)

if __name__ == "__main__":
    while True:
        update_list()
        time.sleep(3600)

2. Docker Compose Stack

Erstelle den folgenden Stack (z.B. in Portainer). Passe Pfade und Ports entsprechend an.
YAML

services:
  cs2-server-picker:
    image: python:3.11-alpine
    container_name: cs2-server-picker
    restart: always
    security_opt:
      - no-new-privileges:true
    environment:
      - TZ=Europe/Berlin
      - ALLOW_REGIONS=fra # HIER ANPASSEN: Whitelist (z.B. fra). Wenn gesetzt, wird alles andere blockiert.
      - BLOCK_REGIONS=ams,atl,dfw,dxb,eze,gru,gum,hkg,iad,jnb,lax,lhr,lim,mad,ord,par,scl,sea,seo,sgp,sto,syd,tyo,vie,waw,bom2,maa2,sto2,ctum,pekm,pvgm,tgdm,ctut,pekt,pvgt,tgdt,ctuu,peku,pvgu,tgdu # HIER ANPASSEN: Blacklist. Greift nur, wenn ALLOW_REGIONS leer ist.
    volumes:
      - /volume2/docker_nvme/cs2-server-picker/app:/app # HIER ANPASSEN: Lokaler Pfad auf dem Host/NAS
    ports:
      - "8115:8000" # HIER ANPASSEN: Gewuenschter externer Port.
    command: sh -c "python /app/generate.py & sleep 5 && python -m http.server 8000 --directory /app/html"
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/blocklist.txt"]
      interval: 1m
      timeout: 10s
      retries: 3

Teil 2: Windows Client Einrichtung

    Speichere diesen Code als Update-CS2Firewall.ps1.

    Passe die Variablen $UrlBlocklist, $UrlSummary und $LogDir an deine Umgebung an.

PowerShell

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

Automatisierung (Windows-Aufgabenplanung):

    Öffne die Aufgabenplanung -> Aufgabe erstellen...

    Allgemein: Name eintragen, Haken bei "Mit höchsten Privilegien ausführen" setzen.

    Trigger: Neu -> Täglich -> Wiederholen alle 6 Stunden.

    Aktion: Programm starten -> powershell.exe. Argumente: -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\DeinNutzer\Documents\Update-CS2Firewall.ps1" (Pfad anpassen!)

Teil 3: Linux Client Einrichtung

Voraussetzungen installieren:
sudo pacman -S jq iptables (Bei Debian/Ubuntu entsprechend sudo apt install jq iptables).

    Skript erstellen:
    Lege die Datei /usr/local/bin/update-cs2firewall.sh an. Passe die Variablen an.

Bash

#!/bin/bash

# HIER ANPASSEN: IP/Domain und Port des Docker-Hosts eintragen.
URL_BLOCKLIST="http://192.168.178.123:8115/blocklist.txt" 
URL_SUMMARY="http://192.168.178.123:8115/summary.json" 

# HIER ANPASSEN: Gewuenschtes Verzeichnis fuer die Log-Dateien.
LOG_DIR="/var/log/cs2_firewall" 

CHAIN_NAME="CS2_BLOCK"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/cs2_firewall_log_$TIMESTAMP.log"

if [ "$EUID" -ne 0 ]; then
  echo "Fehler: Das Skript muss mit Root-Rechten ausgefuehrt werden."
  exit 1
fi

mkdir -p "$LOG_DIR"

write_log() {
    local MESSAGE="$1"
    local LOG_TIME=$(date +"%Y-%m-%d %H:%M:%S")
    echo "[$LOG_TIME] $MESSAGE" >> "$LOG_FILE"
}

write_log "Starte Aktualisierung der CS2 Firewall-Regeln..."

IPS=$(curl -s "$URL_BLOCKLIST")
if [ -z "$IPS" ]; then
    write_log "Fehler beim Abrufen der IP-Liste vom Docker-Container."
    exit 1
fi

SUMMARY=$(curl -s "$URL_SUMMARY")
if [ -n "$SUMMARY" ] && command -v jq >/dev/null 2>&1; then
    ALLOWED=$(echo "$SUMMARY" | jq -r '.allowed | join(", ")')
    write_log "Erlaubte Server-Regionen: $ALLOWED"
    
    echo "$SUMMARY" | jq -r '.blocked | to_entries | .[] | "Blockiere Region: \(.key) (\(.value) IPs)"' | while read -r line; do
        write_log "$line"
    done
else
    write_log "Konnte Server-Zusammenfassung nicht abrufen oder 'jq' ist nicht installiert."
fi

write_log "Loesche alte iptables-Regeln '$CHAIN_NAME' (falls vorhanden)..."
iptables -D OUTPUT -j $CHAIN_NAME 2>/dev/null
iptables -F $CHAIN_NAME 2>/dev/null
iptables -X $CHAIN_NAME 2>/dev/null

IP_COUNT=0
if [ -n "$IPS" ]; then
    iptables -N $CHAIN_NAME
    iptables -A OUTPUT -j $CHAIN_NAME
    
    for ip in $IPS; do
        if [[ $ip =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            iptables -A $CHAIN_NAME -d $ip -j DROP
            ((IP_COUNT++))
        fi
    done
    write_log "Vorgang erfolgreich abgeschlossen. $IP_COUNT IPs verarbeitet."
else
    write_log "Warnung: Keine IPs vom Container empfangen."
fi

write_log "--------------------------------------------------"

# Log-Dateien rotieren (maximal 5 behalten)
ls -t "$LOG_DIR"/cs2_firewall_log_*.log 2>/dev/null | tail -n +6 | xargs -r rm -f

Skript ausführbar machen:
Bash

sudo chmod +x /usr/local/bin/update-cs2firewall.sh

    Systemd Automatisierung einrichten:
    Erstelle die Service-Datei /etc/systemd/system/cs2-blocker.service:

Ini, TOML

[Unit]
Description=Update CS2 Firewall Rules
After=network.target

[Service]
Type=oneshot
# HIER ANPASSEN: Pfad zum ausfuehrbaren Bash-Skript
ExecStart=/usr/local/bin/update-cs2firewall.sh

Erstelle die Timer-Datei /etc/systemd/system/cs2-blocker.timer:
Ini, TOML

[Unit]
Description=Run CS2 Firewall Update every 6 hours

[Timer]
OnBootSec=5min
OnUnitActiveSec=6h

[Install]
WantedBy=timers.target

Aktivieren und starten:
Bash

sudo systemctl daemon-reload
sudo systemctl enable --now cs2-blocker.timer

Plaintext

ams = Amsterdam (Niederlande)
atl = Atlanta (USA)
bom2 = Mumbai (Indien)
ctum = Chengdu - Mobile (China)
ctut = Chengdu - Telecom (China)
ctuu = Chengdu - Unicom (China)
dfw = Dallas (USA)
dxb = Dubai (Vereinigte Arabische Emirate)
eze = Buenos Aires (Argentinien)
fra = Frankfurt am Main (Deutschland)
gru = São Paulo (Brasilien)
gum = Guam (USA)
hkg = Hongkong (China)
iad = Sterling (USA)
jnb = Johannesburg (Südafrika)
lax = Los Angeles (USA)
lhr = London (Großbritannien)
lim = Lima (Peru)
maa2 = Chennai (Indien)
mad = Madrid (Spanien)
ord = Chicago (USA)
par = Paris (Frankreich)
pekm = Peking - Mobile (China)
pekt = Peking - Telecom (China)
peku = Peking - Unicom (China)
pvgm = Shanghai - Mobile (China)
pvgt = Shanghai - Telecom (China)
pvgu = Shanghai - Unicom (China)
scl = Santiago (Chile)
sea = Seattle (USA)
seo = Seoul (Südkorea)
sgp = Singapur (Singapur)
sto = Stockholm - Kista (Schweden)
sto2 = Stockholm - Bromma (Schweden)
syd = Sydney (Australien)
tgdm = Guangzhou - Mobile (China)
tgdt = Guangzhou - Telecom (China)
tgdu = Guangzhou - Unicom (China)
tyo = Tokio (Japan)
vie = Wien (Österreich)
waw = Warschau (Polen)
