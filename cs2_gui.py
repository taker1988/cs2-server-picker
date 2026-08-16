import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import urllib.request
import json
import platform
import subprocess
import os
import sys
import webbrowser
import time

if platform.system() == "Windows":
    CONFIG_PATH = os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "cs2_picker_config.json")
    LOG_PATH = os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "cs2_firewall_gui.log")
else:
    CONFIG_PATH = "/etc/cs2_picker_config.json"
    LOG_PATH = "/var/log/cs2_firewall_gui.log"

def is_admin_check():
    if platform.system() == "Windows":
        import ctypes
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    else:
        return os.geteuid() == 0

def silent_log(msg):
    try:
        with open(LOG_PATH, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except:
        pass

def fetch_and_apply(host, current_os, log_func):
    if not host.startswith("http"):
        host = "http://" + host

    url_blocklist = f"{host}/blocklist.txt"
    url_summary = f"{host}/summary.json"

    log_func("Starte Aktualisierung der CS2 Firewall-Regeln...")
    
    try:
        req_sum = urllib.request.Request(url_summary)
        with urllib.request.urlopen(req_sum, timeout=5) as response:
            summary = json.loads(response.read().decode('utf-8'))
            allowed = ", ".join(summary.get("allowed", []))
            log_func(f"Erlaubte Regionen: {allowed}")
    except Exception as e:
        log_func(f"Warnung: Server-Zusammenfassung nicht abrufbar ({e})")

    try:
        req_ip = urllib.request.Request(url_blocklist)
        with urllib.request.urlopen(req_ip, timeout=5) as response:
            blocklist = response.read().decode('utf-8')
            ips = [ip.strip() for ip in blocklist.split('\n') if ip.strip()]
    except Exception as e:
        log_func(f"Fehler beim Abrufen der IP-Liste: {e}")
        return

    if not ips:
        log_func("Warnung: Keine IPs empfangen.")
        return

    if current_os == "Windows":
        rule_name = "CS2_Server_Blocker"
        subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"], capture_output=True)
        chunk_size = 150
        for i in range(0, len(ips), chunk_size):
            chunk = ",".join(ips[i:i+chunk_size])
            subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={rule_name}", "dir=out", "action=block", f"remoteip={chunk}"], capture_output=True)
        log_func("Vorgang unter Windows erfolgreich abgeschlossen.")
    elif current_os == "Linux":
        chain_name = "CS2_BLOCK"
        subprocess.run(["iptables", "-D", "OUTPUT", "-j", chain_name], stderr=subprocess.DEVNULL)
        subprocess.run(["iptables", "-F", chain_name], stderr=subprocess.DEVNULL)
        subprocess.run(["iptables", "-X", chain_name], stderr=subprocess.DEVNULL)
        subprocess.run(["iptables", "-N", chain_name])
        subprocess.run(["iptables", "-A", "OUTPUT", "-j", chain_name])
        count = 0
        for ip in ips:
            res = subprocess.run(["iptables", "-A", chain_name, "-d", ip, "-j", "DROP"])
            if res.returncode == 0:
                count += 1
        log_func(f"Vorgang unter Linux erfolgreich abgeschlossen. {count} IPs verarbeitet.")

def run_silent():
    if not is_admin_check():
        silent_log("Fehler: Keine Administrator-/Root-Rechte.")
        sys.exit(1)
    if not os.path.exists(CONFIG_PATH):
        silent_log("Fehler: Keine Konfigurationsdatei gefunden.")
        sys.exit(1)
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
        host = config.get("host", "")
        if host:
            fetch_and_apply(host, platform.system(), silent_log)
    except Exception as e:
        silent_log(f"Fehler im Silent-Mode: {e}")
    sys.exit(0)

if len(sys.argv) > 1 and sys.argv[1] == "--silent":
    run_silent()

class CS2ServerPickerGUI:
    def __init__(self, root):
        self.root = root
        self.root.geometry("750x850")
        self.root.minsize(700, 800)
        self.current_version = "v1.0.0"
        self.current_os = platform.system()
        self.lang = tk.StringVar(value="DE")

        self.texts = {
            "EN": {
                "title": "CS2 Server Picker Client",
                "ip_label": "Docker Host IP and Port (e.g. 192.168.178.123:8115):",
                "btn_refresh_disp": "Refresh Lists",
                "lbl_allowed": "Allowed Regions",
                "lbl_blocked": "Blocked Regions",
                "lbl_info": "Note: Server regions must be changed directly in the Docker stack configuration.",
                "btn_update_fw": "Apply Firewall Rules",
                "btn_delete_fw": "Delete Firewall Rules",
                "btn_about": "About",
                "btn_update_check": "Check for Updates",
                "err_admin": "The program must be run as Administrator (Windows) or Root (Linux).",
                "err_no_ip": "Error: No IP/Port specified.",
                "start_update": "Starting CS2 firewall rules update...",
                "allowed_regions": "Allowed regions: ",
                "block_region": "Blocking region: ",
                "err_summary": "Warning: Server summary could not be fetched",
                "err_blocklist": "Error fetching IP list: ",
                "warn_no_ip": "Warning: No IPs received.",
                "unknown_os": "Unknown Operating System: ",
                "win_del_old": "Deleting old Windows firewall rule",
                "win_create_new": "Creating new rules for",
                "win_success": "Process completed successfully on Windows.",
                "win_success_del": "Firewall rules successfully deleted on Windows.",
                "lin_del_old": "Deleting old iptables rules",
                "lin_create_new": "Creating new rules for",
                "lin_success": "Process completed successfully on Linux. Processed IPs: ",
                "lin_success_del": "Firewall rules successfully deleted on Linux.",
                "timer_frame": "Automation (Background Update)",
                "timer_create": "Create Timer",
                "timer_delete": "Delete Timer",
                "timer_success": "Timer created successfully (Every {h}h).",
                "timer_del_success": "Timer deleted successfully.",
                "timer_err": "Error creating timer: ",
                "about_text": "CS2 Server Picker Client\nVersion: {version}\n\nDeveloped by: taker1988",
                "update_avail": "A new version is available!",
                "update_ask": "Do you want to open the GitHub releases page to download it?",
                "update_not_avail": "You are using the latest version.",
                "update_err": "Could not check for updates: ",
                "update_404": "No releases found on GitHub yet.",
                "refresh_success": "Lists successfully refreshed.",
                "warn_overlap_title": "Configuration Warning",
                "warn_overlap_text": "Conflict detected in Docker Container!\nThe following regions are both allowed and blocked:\n{regions}\n\nPlease fix your container configuration."
            },
            "DE": {
                "title": "CS2 Server Picker Client",
                "ip_label": "Docker Host IP und Port (z.B. 192.168.178.123:8115):",
                "btn_refresh_disp": "Listen aktualisieren",
                "lbl_allowed": "Erlaubte Regionen",
                "lbl_blocked": "Blockierte Regionen",
                "lbl_info": "Hinweis: Die Serverauswahl muss direkt in der Konfiguration des Docker-Stacks geändert werden.",
                "btn_update_fw": "Firewall Regeln anwenden",
                "btn_delete_fw": "Firewall Regeln löschen",
                "btn_about": "Über",
                "btn_update_check": "Auf Updates prüfen",
                "err_admin": "Das Programm muss als Administrator (Windows) oder Root (Linux) ausgeführt werden.",
                "err_no_ip": "Fehler: Keine IP/Port angegeben.",
                "start_update": "Starte Aktualisierung der CS2 Firewall-Regeln...",
                "allowed_regions": "Erlaubte Regionen: ",
                "block_region": "Blockiere Region: ",
                "err_summary": "Warnung: Server-Zusammenfassung nicht abrufbar",
                "err_blocklist": "Fehler beim Abrufen der IP-Liste: ",
                "warn_no_ip": "Warnung: Keine IPs empfangen.",
                "unknown_os": "Unbekanntes Betriebssystem: ",
                "win_del_old": "Lösche alte Windows-Firewall-Regel",
                "win_create_new": "Erstelle neue Regeln für",
                "win_success": "Vorgang unter Windows erfolgreich abgeschlossen.",
                "win_success_del": "Firewall-Regeln unter Windows erfolgreich gelöscht.",
                "lin_del_old": "Lösche alte iptables-Regeln",
                "lin_create_new": "Erstelle neue Regeln für",
                "lin_success": "Vorgang unter Linux erfolgreich abgeschlossen. Verarbeitete IPs: ",
                "lin_success_del": "Firewall-Regeln unter Linux erfolgreich gelöscht.",
                "timer_frame": "Automatisierung (Hintergrund-Update)",
                "timer_create": "Timer erstellen",
                "timer_delete": "Timer löschen",
                "timer_success": "Timer erfolgreich erstellt (Alle {h} Std.).",
                "timer_del_success": "Timer erfolgreich gelöscht.",
                "timer_err": "Fehler beim Erstellen des Timers: ",
                "about_text": "CS2 Server Picker Client\nVersion: {version}\n\nEntwickelt von: taker1988",
                "update_avail": "Eine neue Version ist verfügbar!",
                "update_ask": "Möchtest du die GitHub-Releases-Seite öffnen, um sie herunterzuladen?",
                "update_not_avail": "Du nutzt bereits die neueste Version.",
                "update_err": "Fehler bei der Update-Prüfung: ",
                "update_404": "Bisher wurden keine Releases auf GitHub veröffentlicht.",
                "refresh_success": "Listen erfolgreich aktualisiert.",
                "warn_overlap_title": "Konfigurationswarnung",
                "warn_overlap_text": "Konflikt im Docker Container erkannt!\nFolgende Regionen sind als erlaubt UND blockiert konfiguriert:\n{regions}\n\nBitte korrigiere deine Container-Konfiguration."
            }
        }

        if not is_admin_check():
            messagebox.showerror("Fehler / Error", self.texts[self.lang.get()]["err_admin"])
            sys.exit(1)

        top_frame = tk.Frame(root)
        top_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Radiobutton(top_frame, text="DE", variable=self.lang, value="DE", command=self.update_ui).pack(side="left")
        tk.Radiobutton(top_frame, text="EN", variable=self.lang, value="EN", command=self.update_ui).pack(side="left")

        self.btn_about = tk.Button(top_frame, text="", command=self.show_about)
        self.btn_about.pack(side="right", padx=5)

        self.btn_check = tk.Button(top_frame, text="", command=self.check_update)
        self.btn_check.pack(side="right", padx=5)

        self.label_ip = tk.Label(root, text="")
        self.label_ip.pack(pady=(15, 0))
        
        ip_frame = tk.Frame(root)
        ip_frame.pack(pady=5)
        self.entry_ip = tk.Entry(ip_frame, width=40)
        self.entry_ip.insert(0, "192.168.178.123:8115")
        self.entry_ip.pack(side="left", padx=5)
        self.btn_refresh_disp = tk.Button(ip_frame, text="", command=self.refresh_display)
        self.btn_refresh_disp.pack(side="left", padx=5)

        self.lists_frame = tk.Frame(root)
        self.lists_frame.pack(pady=10, fill="x", padx=20)
        
        self.frame_allowed = tk.LabelFrame(self.lists_frame, text="")
        self.frame_allowed.pack(side="left", fill="both", expand=True, padx=5)
        self.list_allowed = tk.Listbox(self.frame_allowed, height=8, bg="#e8f5e9")
        self.list_allowed.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.frame_blocked = tk.LabelFrame(self.lists_frame, text="")
        self.frame_blocked.pack(side="right", fill="both", expand=True, padx=5)
        self.list_blocked = tk.Listbox(self.frame_blocked, height=8, bg="#ffebee")
        self.list_blocked.pack(fill="both", expand=True, padx=5, pady=5)

        self.lbl_info = tk.Label(root, text="", fg="gray", font=("Arial", 9, "italic"), wraplength=650, justify="center")
        self.lbl_info.pack(pady=(0, 10))

        action_frame = tk.Frame(root)
        action_frame.pack(pady=10)

        self.btn_update_fw = tk.Button(action_frame, text="", command=self.update_firewall)
        self.btn_update_fw.pack(side="left", padx=10)

        self.btn_delete_fw = tk.Button(action_frame, text="", command=self.delete_firewall)
        self.btn_delete_fw.pack(side="left", padx=10)

        self.timer_frame = tk.LabelFrame(root, text="")
        self.timer_frame.pack(pady=10, padx=20, fill="x")

        self.timer_var = tk.StringVar()
        self.combo_timer = ttk.Combobox(self.timer_frame, textvariable=self.timer_var, state="readonly", width=25)
        self.combo_timer.pack(side="left", padx=10, pady=10)

        self.btn_create_timer = tk.Button(self.timer_frame, text="", command=self.create_timer)
        self.btn_create_timer.pack(side="left", padx=5, pady=10)

        self.btn_delete_timer = tk.Button(self.timer_frame, text="", command=self.delete_timer)
        self.btn_delete_timer.pack(side="left", padx=5, pady=10)

        self.log_area = scrolledtext.ScrolledText(root, width=75, height=12, state='disabled')
        self.log_area.pack(pady=10)

        self.update_ui()
        self.combo_timer.current(5)

    def update_ui(self):
        t = self.texts[self.lang.get()]
        self.root.title(t["title"])
        self.label_ip.config(text=t["ip_label"])
        self.btn_refresh_disp.config(text=t["btn_refresh_disp"])
        self.frame_allowed.config(text=t["lbl_allowed"])
        self.frame_blocked.config(text=t["lbl_blocked"])
        self.lbl_info.config(text=t["lbl_info"])
        self.btn_update_fw.config(text=t["btn_update_fw"])
        self.btn_delete_fw.config(text=t["btn_delete_fw"])
        self.btn_about.config(text=t["btn_about"])
        self.btn_check.config(text=t["btn_update_check"])
        
        self.timer_frame.config(text=t["timer_frame"])
        self.btn_create_timer.config(text=t["timer_create"])
        self.btn_delete_timer.config(text=t["timer_delete"])

        options = []
        for i in range(1, 25):
            suffix = " Std." if self.lang.get() == "DE" else "h"
            rec = " (Empfohlen)" if self.lang.get() == "DE" else " (Recommended)"
            text = f"{i}{suffix}{rec if i == 6 else ''}"
            options.append(text)
        
        current_idx = self.combo_timer.current()
        self.combo_timer['values'] = options
        if current_idx >= 0:
            self.combo_timer.current(current_idx)

    def log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')
        self.root.update()

    def refresh_display(self):
        host = self.entry_ip.get().strip()
        t = self.texts[self.lang.get()]
        if not host:
            self.log(t["err_no_ip"])
            return

        if not host.startswith("http"):
            host = "http://" + host

        url_summary = f"{host}/summary.json"
        
        self.list_allowed.delete(0, tk.END)
        self.list_blocked.delete(0, tk.END)

        try:
            req = urllib.request.Request(url_summary)
            with urllib.request.urlopen(req, timeout=5) as response:
                summary = json.loads(response.read().decode('utf-8'))
                
                allowed_list = summary.get("allowed", [])
                blocked_dict = summary.get("blocked", {})
                
                overlap = [region for region in allowed_list if region in blocked_dict]
                if overlap:
                    overlap_str = "\n".join(f"- {r}" for r in overlap)
                    messagebox.showwarning(t["warn_overlap_title"], t["warn_overlap_text"].format(regions=overlap_str))

                for region in allowed_list:
                    self.list_allowed.insert(tk.END, region)
                    
                for region, count in blocked_dict.items():
                    self.list_blocked.insert(tk.END, f"{region} ({count} IPs)")
            
            self.log(t["refresh_success"])
        except Exception as e:
            self.log(f"{t['err_summary']} ({e})")

    def show_about(self):
        t = self.texts[self.lang.get()]
        msg = t["about_text"].format(version=self.current_version)
        messagebox.showinfo(t["btn_about"], msg)

    def check_update(self):
        t = self.texts[self.lang.get()]
        url = "https://api.github.com/repos/taker1988/cs2-server-picker/releases/latest"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                latest_version = data.get("tag_name", "")
                
                if latest_version and latest_version != self.current_version:
                    if messagebox.askyesno(t["btn_update_check"], f"{t['update_avail']} ({latest_version})\n\n{t['update_ask']}"):
                        webbrowser.open("https://github.com/taker1988/cs2-server-picker/releases/latest")
                else:
                    messagebox.showinfo(t["btn_update_check"], t["update_not_avail"])
        except urllib.error.HTTPError as e:
            if e.code == 404:
                messagebox.showinfo(t["btn_update_check"], t["update_404"])
            else:
                messagebox.showerror("Error", f"{t['update_err']}{e}")
        except Exception as e:
            messagebox.showerror("Error", f"{t['update_err']}{e}")

    def save_config(self):
        host = self.entry_ip.get().strip()
        if not host:
            return False
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump({"host": host}, f)
            return True
        except Exception as e:
            self.log(f"Config Error: {e}")
            return False

    def get_exe_path(self):
        return os.path.abspath(sys.argv[0])

    def create_timer(self):
        t = self.texts[self.lang.get()]
        if not self.save_config():
            self.log(t["err_no_ip"])
            return

        hours = self.combo_timer.current() + 1
        exe_path = self.get_exe_path()

        try:
            if self.current_os == "Linux":
                service = f"""[Unit]\nDescription=CS2 Firewall Blocker Update\n\n[Service]\nType=oneshot\nExecStart={exe_path} --silent\n"""
                timer = f"""[Unit]\nDescription=Run CS2 Firewall Blocker\n\n[Timer]\nOnBootSec=5min\nOnUnitActiveSec={hours}h\n\n[Install]\nWantedBy=timers.target\n"""
                
                with open("/etc/systemd/system/cs2-blocker.service", "w") as f:
                    f.write(service)
                with open("/etc/systemd/system/cs2-blocker.timer", "w") as f:
                    f.write(timer)
                
                subprocess.run(["systemctl", "daemon-reload"])
                subprocess.run(["systemctl", "enable", "--now", "cs2-blocker.timer"])
            
            elif self.current_os == "Windows":
                task_name = "CS2_Server_Blocker_Update"
                cmd = f'schtasks /create /tn "{task_name}" /tr "\\"{exe_path}\\" --silent" /sc HOURLY /mo {hours} /rl HIGHEST /F'
                subprocess.run(cmd, shell=True, capture_output=True)

            self.log(t["timer_success"].format(h=hours))
        except Exception as e:
            self.log(f"{t['timer_err']}{e}")

    def delete_timer(self):
        t = self.texts[self.lang.get()]
        try:
            if self.current_os == "Linux":
                subprocess.run(["systemctl", "disable", "--now", "cs2-blocker.timer"], stderr=subprocess.DEVNULL)
                os.remove("/etc/systemd/system/cs2-blocker.timer") if os.path.exists("/etc/systemd/system/cs2-blocker.timer") else None
                os.remove("/etc/systemd/system/cs2-blocker.service") if os.path.exists("/etc/systemd/system/cs2-blocker.service") else None
                subprocess.run(["systemctl", "daemon-reload"])
            
            elif self.current_os == "Windows":
                task_name = "CS2_Server_Blocker_Update"
                cmd = f'schtasks /delete /tn "{task_name}" /F'
                subprocess.run(cmd, shell=True, capture_output=True)

            self.log(t["timer_del_success"])
        except Exception as e:
            self.log(f"Error: {e}")

    def delete_firewall(self):
        self.log_area.config(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state='disabled')
        
        self.list_allowed.delete(0, tk.END)
        self.list_blocked.delete(0, tk.END)

        if self.current_os == "Windows":
            rule_name = "CS2_Server_Blocker"
            subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"], capture_output=True)
            self.log(self.texts[self.lang.get()]["win_success_del"])
        elif self.current_os == "Linux":
            chain_name = "CS2_BLOCK"
            subprocess.run(["iptables", "-D", "OUTPUT", "-j", chain_name], stderr=subprocess.DEVNULL)
            subprocess.run(["iptables", "-F", chain_name], stderr=subprocess.DEVNULL)
            subprocess.run(["iptables", "-X", chain_name], stderr=subprocess.DEVNULL)
            self.log(self.texts[self.lang.get()]["lin_success_del"])

    def update_firewall(self):
        self.log_area.config(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state='disabled')
        host = self.entry_ip.get().strip()
        if not host:
            self.log(self.texts[self.lang.get()]["err_no_ip"])
            return
        
        self.refresh_display()
        fetch_and_apply(host, self.current_os, self.log)

if __name__ == "__main__":
    root = tk.Tk()
    app = CS2ServerPickerGUI(root)
    root.mainloop()
