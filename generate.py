import json
import urllib.request
import time
import os

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
