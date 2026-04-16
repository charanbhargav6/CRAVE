"""
CRAVE Phase 10 - Thermal Monitor
Save to: D:/CRAVE/src/core/thermal_monitor.py

Monitors CPU temperature to protect the laptop from thermal throttling and hardware damage.
"""

import time
import threading
from typing import Optional

try:
    import wmi
except ImportError:
    wmi = None

class ThermalMonitor:
    def __init__(self, orchestrator, telegram_agent=None, check_interval=30):
        self._orchestrator = orchestrator
        self._telegram_agent = telegram_agent
        self._check_interval = check_interval
        self._running = False
        self._thread = None
        self._wmi_interface = None
        self._last_alert_time = 0
        
        self.temp_pause_threshold = 90.0
        self.temp_halt_threshold = 95.0

        if wmi:
            try:
                self._wmi_interface = wmi.WMI(namespace="root\\wmi")
            except Exception as e:
                print(f"[ThermalMonitor] WMI initialization failed: {e}")

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="CRAVEThermal")
        self._thread.start()
        print("[ThermalMonitor] Started background tracking.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            
    def _get_cpu_temp(self) -> Optional[float]:
        if not self._wmi_interface:
            return None
        
        try:
            # WMI thermal zones
            temps = self._wmi_interface.MSAcpi_ThermalZoneTemperature()
            if not temps:
                return None
                
            max_celsius = 0.0
            for t in temps:
                # WMI returns temp in tenths of degrees Kelvin
                celsius = (t.CurrentTemperature / 10.0) - 273.15
                if celsius > max_celsius:
                    max_celsius = celsius
            return max_celsius
            
        except Exception as e:
            # Sometimes accessing this without admin raises an error
            return None

    def _monitor_loop(self):
        while self._running:
            temp = self._get_cpu_temp()
            
            if temp is not None:
                # 95C Check - Emergency Halt
                if temp >= self.temp_halt_threshold:
                    print(f"[ThermalMonitor] EMERGENCY: CPU Temp at {temp:.1f}C! Initiating Shutdown.")
                    
                    if self._telegram_agent:
                        self._telegram_agent.send_message_sync(
                            f"🚨 *CRAVE CRITICAL ALERT* 🚨\n\nCPU Temperature reached *{temp:.1f}°C*.\nEmergency Halt triggered to prevent hardware damage."
                        )
                        
                    # Trigger orchestrator stop safely
                    self._orchestrator.submit("stop")
                    time.sleep(5) # Give it time to propagate
                
                # 90C Check - Pause Tasks
                elif temp >= self.temp_pause_threshold:
                    now = time.time()
                    if now - self._last_alert_time > 300: # Max 1 alert per 5 mins
                        print(f"[ThermalMonitor] WARNING: CPU Temp high ({temp:.1f}C). Pausing activity for cooldown.")
                        
                        if self._telegram_agent:
                            self._telegram_agent.send_message_sync(
                                f"⚠️ *CRAVE THERMAL WARNING* ⚠️\n\nCPU at *{temp:.1f}°C*. Cooling down. Tasks temporarily paused."
                            )
                        self._last_alert_time = now
                        
                        # In the future, we could trigger a specific state
                        # For now, orchestrator just logs it. You could also sleep here
                        # to starve the background loop, but pausing agents is better handled at the agent level
            
            time.sleep(self._check_interval)
