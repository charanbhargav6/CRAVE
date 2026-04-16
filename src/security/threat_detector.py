"""
CRAVE Phase E — Autonomous Threat Detector
Tails security_events.log and triggers PentAGI counter-recon 
when a malicious threshold is breached.
"""

import os
import time
import re
import threading
import logging
from collections import defaultdict

logger = logging.getLogger("crave.security.threat_detector")

class ThreatDetector(threading.Thread):
    def __init__(self, log_path: str, pentagi_agent=None, telegram_agent=None):
        super().__init__(daemon=True, name="CRAVE_ThreatDetector")
        self.log_path = log_path
        self.pentagi = pentagi_agent
        self.telegram = telegram_agent
        self.running = False
        
        # Track IPs to prevent counter-attacking the same IP endlessly
        self.counter_attacked_ips = set()
        
        # Simple thresholding: block if > 5 malicious hits within 60 seconds
        self.suspicious_hits = defaultdict(list)
        self.trigger_threshold = 5

    def run(self):
        self.running = True
        logger.info(f"ThreatDetector active. Tailing {self.log_path}")
        
        # Ensure log exists
        if not os.path.exists(self.log_path):
            open(self.log_path, 'a').close()
            
        with open(self.log_path, "r", encoding="utf-8") as file:
            # Go to the end of the file
            file.seek(0, os.SEEK_END)
            
            while self.running:
                line = file.readline()
                if not line:
                    time.sleep(1)
                    continue
                
                self._process_line(line)

    def _process_line(self, line: str):
        # Look for typical malicious signatures in logs 
        # Example format: [WARN] Failed auth attempt from IP: 192.168.1.100
        # Example format: [CRIT] Network flooding detected from 10.0.0.55
        
        lower_line = line.lower()
        if "failed auth" in lower_line or "brute" in lower_line or "flooding" in lower_line or "ddos" in lower_line or "attack" in lower_line:
            # Extract IP
            ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', line)
            if ip_match:
                ip = ip_match.group(0)
                
                # Exclude localhost explicitly unless testing
                if ip == "127.0.0.1" or ip == "0.0.0.0":
                    return
                    
                self._register_hit(ip)

    def _register_hit(self, ip: str):
        now = time.time()
        # Clean old hits > 60 seconds
        self.suspicious_hits[ip] = [t for t in self.suspicious_hits[ip] if now - t < 60]
        self.suspicious_hits[ip].append(now)
        
        if len(self.suspicious_hits[ip]) >= self.trigger_threshold:
            if ip not in self.counter_attacked_ips:
                self._trigger_counter_recon(ip)

    def _trigger_counter_recon(self, ip: str):
        self.counter_attacked_ips.add(ip)
        msg = f"🚨 THREAT DETECTED: IP {ip} exceeded attack threshold. Waking PentAGI for autonomous counter-reconnaissance."
        logger.warning(msg)
        print(f"\n[ThreatDetector] {msg}")
        
        if self.telegram:
            self.telegram.send_message_sync(msg)
            
        if self.pentagi:
            def _async_strike():
                res = self.pentagi.start_mission(target=ip, mode="defensive")
                if res.get("success"):
                    # Wait for it to finish
                    task_id = res["task_id"]
                    status = "running"
                    while status in ["running", "pending", "starting"]:
                        time.sleep(10)
                        status = self.pentagi.poll_status(task_id)
                        
                    report = self.pentagi.get_report(task_id)
                    if report and self.telegram:
                        # Send summary to telegram
                        self.telegram.send_message_sync(f"🎯 PentAGI Counter-Recon Complete on {ip}.\nPreview:\n{report[:500]}...")
                else:
                    logger.error(f"PentAGI failed to launch counter-recon: {res.get('error')}")
            
            threading.Thread(target=_async_strike, daemon=True, name=f"CRAVE_CounterStrike_{ip}").start()
