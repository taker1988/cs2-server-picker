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
