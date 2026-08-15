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
