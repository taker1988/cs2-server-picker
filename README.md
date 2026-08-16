# CS2 Server Picker (Docker Backend + Windows/Linux Client)

[English Version](#english-version) | [Deutsche Version](#deutsche-version)

---

## English Version

Automated setup to enforce Counter-Strike 2 (CS2) matchmaking on specific server regions (e.g., Frankfurt only) by blocking unwanted IP ranges via the local firewall. This works for solo queuing as well as full lobbies.

**Background:** When starting a match search, the game pings all available servers to find the "best" one. If only one player (who runs this script) blocks all other regions, the entire lobby will be routed to the remaining allowed server.

### Architecture

1. **Docker Container (Backend):** Queries the official Valve API (`GetSDRConfig`) hourly for Steam Datagram Relay (SDR) servers. Filters them based on a Whitelist (`ALLOW_REGIONS`) or Blacklist (`BLOCK_REGIONS`) and serves a `blocklist.txt` and `summary.json` via a lightweight HTTP server. The backend runs as a pre-built Docker image.
2. **Client Options:** You can either use the graphical standalone client (GUI) or the manual scripts (PowerShell/Bash) to fetch the blocklist and apply the firewall rules.

---

### Part 1: Docker Backend Setup

The container runs isolated and generates the necessary IP lists. Deploy the following stack (e.g., via Portainer). Adjust paths, variables, and ports to fit your host environment.

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

### Part 2: Client Setup (Choose Option A or B)

#### Option A: GUI Client (Windows & Linux)

The CS2 Server Picker Client provides an easy-to-use graphical interface.

**Anti-Virus / Windows Defender Note:**
Because this application modifies local firewall rules and is packaged as a standalone executable, Windows Defender or third-party antivirus software may flag it as a false positive. **You must add the `CS2_Server_Picker_Windows.exe` to your antivirus exclusions/exceptions list for it to function correctly.**

**Usage:**
1. Download the latest release for your OS from the [Releases](https://github.com/taker1988/cs2-server-picker/releases) page.
2. **Windows:** Run `CS2_Server_Picker_Windows.exe` with a double click (it will ask for Administrator privileges).
3. **Linux:** Open a terminal in the downloaded directory and run: `sudo ./CS2_Server_Picker_Linux`
4. Enter the IP and Port of your Docker backend (e.g., `192.168.178.123:8115`) and click **Apply Firewall Rules**.
5. **Automation:** Select a background timer interval in the GUI (e.g., `6h`) and click **Create Timer** to automate the process.

---

#### Option B: Manual Scripts (PowerShell / Bash)

If you prefer not to use the GUI, you can use the manual scripts.

**Windows Setup (PowerShell):**
1. Save the following code as `Update-CS2Firewall.ps1`.
2. Adjust `$UrlBlocklist`, `$UrlSummary`, and `$LogDir`.
3. Open Task Scheduler -> *Create Task...* -> Name it, check **Run with highest privileges**.
4. Set a daily trigger to repeat every 6 hours.
5. Action: Start a program -> `powershell.exe`. Arguments: `-ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Path\To\Update-CS2Firewall.ps1"`

```powershell
$UrlBlocklist = "http://YOUR_DOCKER_IP:8115/blocklist.txt" 
$UrlSummary = "http://YOUR_DOCKER_IP:8115/summary.json" 
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

$LogFiles = Get-ChildItem -Path$LogDir -Filter "CS2_Firewall_Update_*.log" | Sort-Object CreationTime -Descending
if ($LogFiles.Count -gt 5) {
    $FilesToDelete =$LogFiles | Select-Object -Skip 5
    foreach ($File in$FilesToDelete) {
        Remove-Item -Path $File.FullName -Force
    }
}
```

**Linux Setup (Bash):**
1. Install `jq` and `iptables` (`sudo pacman -S jq iptables` or `sudo apt install jq iptables`).
2. Save the following script as `/usr/local/bin/update-cs2firewall.sh`.
3. Adjust the `URL` variables and `$LOG_DIR`.
4. Run via cronjob (`sudo crontab -e`): `0 */6 * * * /usr/local/bin/update-cs2firewall.sh`

```bash
#!/bin/bash

URL_BLOCKLIST="http://YOUR_DOCKER_IP:8115/blocklist.txt" 
URL_SUMMARY="http://YOUR_DOCKER_IP:8115/summary.json" 
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

ls -t "$LOG_DIR"/cs2_firewall_log_*.log 2>/dev/null | tail -n +6 | xargs -r rm -f
```

---
---

## Deutsche Version

Ein automatisiertes Setup, um das Matchmaking in Counter-Strike 2 (CS2) auf bestimmte Server-Regionen (z.B. nur Frankfurt) zu beschränken, indem unerwünschte IP-Bereiche über die lokale Firewall blockiert werden. Dies funktioniert sowohl für Solo-Spieler als auch für komplette Lobbys.

**Hintergrund:** Bei der Matchsuche pingt das Spiel alle verfügbaren Server an, um den "besten" zu finden. Wenn auch nur ein Spieler der Lobby (der dieses Tool nutzt) alle anderen Regionen blockiert, wird die gesamte Lobby auf den verbleibenden, erlaubten Server geleitet.

### Architektur

1. **Docker Container (Backend):** Fragt stündlich die offizielle Valve-API (`GetSDRConfig`) nach SDR-Servern ab. Filtert diese basierend auf einer Whitelist (`ALLOW_REGIONS`) oder Blacklist (`BLOCK_REGIONS`) und stellt eine `blocklist.txt` sowie eine `summary.json` bereit.
2. **Client-Optionen:** Die Firewall-Regeln können wahlweise über den grafischen GUI-Client oder komplett manuell per Skript (PowerShell/Bash) auf dem jeweiligen PC angewendet werden.

---

### Teil 1: Docker Backend Setup

Der Container läuft isoliert und generiert die IP-Listen. Stelle den folgenden Stack bereit (z.B. über Portainer) und passe Pfade, Variablen sowie Ports an.

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
      - ALLOW_REGIONS=fra # HIER ANPASSEN: Whitelist (z.B. fra). Blockiert alles andere, wenn gesetzt.
      - BLOCK_REGIONS=ams,atl,dfw,dxb,eze,gru,gum,hkg,iad,jnb,lax,lhr,lim,mad,ord,par,scl,sea,seo,sgp,sto,syd,tyo,vie,waw,bom2,maa2,sto2,ctum,pekm,pvgm,tgdm,ctut,pekt,pvgt,tgdt,ctuu,peku,pvgu,tgdu # HIER ANPASSEN: Blacklist. Nur aktiv, wenn ALLOW_REGIONS leer ist.
    volumes:
      - /volume2/docker/cs2-server-picker/html:/app/html # HIER ANPASSEN: Lokaler Host-Pfad
    ports:
      - "8115:8000" # HIER ANPASSEN: Externer Port
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/blocklist.txt"]
      interval: 1m
      timeout: 10s
      retries: 3
```

---

### Teil 2: Client Setup (Wähle Option A oder B)

#### Option A: GUI Client (Windows & Linux)

Die grafische Oberfläche ist die empfohlene und einfachste Variante.

**Hinweis zu Antiviren-Programmen / Windows Defender:**
Da diese Anwendung lokale Firewall-Regeln ändert, wird sie von Windows Defender häufig als "False Positive" (Fehlalarm) blockiert. **Die Datei `CS2_Server_Picker_Windows.exe` muss zwingend als Ausnahme im Antiviren-Programm hinzugefügt werden.**

**Nutzung:**
1. Lade das neueste Release für dein Betriebssystem von der [Releases-Seite](https://github.com/taker1988/cs2-server-picker/releases) herunter.
2. **Windows:** Starte die `CS2_Server_Picker_Windows.exe` per Doppelklick (Administrator-Rechte werden automatisch angefragt).
3. **Linux:** Öffne ein Terminal im Download-Verzeichnis und starte die Datei als Root: `sudo ./CS2_Server_Picker_Linux`
4. Gib die IP und den Port deines Backends ein (z.B. `192.168.178.123:8115`) und klicke auf **Firewall Regeln anwenden**.
5. **Automatisierung:** Wähle ein Intervall im Dropdown-Menü und klicke auf **Timer erstellen**, um die Aktualisierung im Hintergrund einzurichten.

---

#### Option B: Manuelle Skripte (PowerShell / Bash)

Alternativ können die reinen Code-Skripte ohne GUI genutzt werden.

**Windows Setup (PowerShell):**
1. Kopiere den PowerShell-Code und speichere ihn als `Update-CS2Firewall.ps1`.
2. Passe die IP-Adressen und Pfade im Skript an.
3. Richte über die Windows Aufgabenplanung einen Task ein, der das Skript mit höchsten Privilegien alle 6 Stunden über `powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Pfad\Update-CS2Firewall.ps1"` ausführt.

```powershell
$UrlBlocklist = "http://DEINE_DOCKER_IP:8115/blocklist.txt" 
$UrlSummary = "http://DEINE_DOCKER_IP:8115/summary.json" 
$LogDir = "C:\Users\DeinUser\Documents" 

$RuleName = "CS2_Server_Blocker"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = "$LogDir\CS2_Firewall_Update_$Timestamp.log"

Function Write-Log {
    param ([string]$Message)$LogTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$LogTime]$Message"
}

try {
    Write-Log "Starte Aktualisierung der CS2 Firewall-Regeln..."
    $BlockList = Invoke-RestMethod -Uri$UrlBlocklist
    $Ips =$BlockList -split "`n" | Where-Object { $_.Trim() -ne "" }
    
    try {
        $Summary = Invoke-RestMethod -Uri $UrlSummary
        Write-Log "Erlaubte Regionen: $($Summary.allowed -join ', ')"
        foreach ($Region in $Summary.blocked.PSObject.Properties) {
            Write-Log "Blockiere Region: $($Region.Name) ($($Region.Value) IPs)"
        }
    } catch {
        Write-Log "Server-Zusammenfassung konnte nicht abgerufen werden."
    }
    
    if ($Ips.Count -gt 0) {
        Write-Log "Lösche alte Firewall-Regel '$RuleName' (falls vorhanden)..."
        netsh advfirewall firewall delete rule name=$RuleName | Out-Null
        
        Write-Log "Erstelle neue Firewall-Regeln für $($Ips.Count) IPs..."
        $ChunkSize = 150
        for ($i = 0; $i -lt $Ips.Count; $i += $ChunkSize) {
            $EndIndex = [math]::Min($i + $ChunkSize - 1, $Ips.Count - 1)
            $Chunk = $Ips[$i..$EndIndex] -join ","
            netsh advfirewall firewall add rule name=$RuleName dir=out action=block remoteip=$Chunk | Out-Null
        }
        Write-Log "Vorgang abgeschlossen. $($Ips.Count) IPs verarbeitet."
    } else {
        Write-Log "Warnung: Keine IPs vom Container empfangen."
    }
} catch {
    Write-Log "Fehler beim Abrufen der IP-Liste vom Docker-Container: $($_.Exception.Message)"
}
Write-Log "--------------------------------------------------"

$LogFiles = Get-ChildItem -Path $LogDir -Filter "CS2_Firewall_Update_*.log" | Sort-Object CreationTime -Descending
if ($LogFiles.Count -gt 5) {
    $FilesToDelete = $LogFiles | Select-Object -Skip 5
    foreach ($File in $FilesToDelete) {
        Remove-Item -Path $File.FullName -Force
    }
}
```

**Linux Setup (Bash):**
1. Installiere `jq` und `iptables` (`sudo pacman -S jq iptables` oder `sudo apt install jq iptables`).
2. Kopiere den Bash-Code und speichere ihn als `/usr/local/bin/update-cs2firewall.sh`.
3. Passe die IP-Adressen im Skript an.
4. Richte über `sudo crontab -e` einen Cronjob ein: `0 */6 * * * /usr/local/bin/update-cs2firewall.sh`.

```bash
#!/bin/bash

URL_BLOCKLIST="http://DEINE_DOCKER_IP:8115/blocklist.txt" 
URL_SUMMARY="http://DEINE_DOCKER_IP:8115/summary.json" 
LOG_DIR="/var/log/cs2_firewall" 

CHAIN_NAME="CS2_BLOCK"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/cs2_firewall_log_$TIMESTAMP.log"

if [ "$EUID" -ne 0 ]; then
  echo "Fehler: Bitte als Root ausführen."
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
    write_log "Erlaubte Regionen: $ALLOWED"
    
    echo "$SUMMARY" | jq -r '.blocked | to_entries | .[] | "Blockiere Region: \(.key) (\(.value) IPs)"' | while read -r line; do
        write_log "$line"
    done
else
    write_log "Server-Zusammenfassung konnte nicht abgerufen werden oder 'jq' ist nicht installiert."
fi

write_log "Lösche alte iptables-Regeln '$CHAIN_NAME' (falls vorhanden)..."
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
    write_log "Vorgang abgeschlossen. $IP_COUNT IPs verarbeitet."
else
    write_log "Warnung: Keine IPs vom Container empfangen."
fi

write_log "--------------------------------------------------"

ls -t "$LOG_DIR"/cs2_firewall_log_*.log 2>/dev/null | tail -n +6 | xargs -r rm -f
```
