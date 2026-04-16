"""
CRAVE Phase 7 - CapCut Automation Agent
Uses pywinauto to mechanically control the physical Windows CapCut GUI 
application to select templates and initiate exports automatically.
"""

from pywinauto import Application, Desktop
import time
import keyboard
import logging

logger = logging.getLogger("crave.agents.capcut")

class CapCutAgent:
    def __init__(self):
        self._connected = False
        self.app = None
        self.window = None

    def prompt_mouse_seizure(self) -> bool:
        """
        Pauses and asks the user for explicit permission to hijack the physical mouse.
        """
        print("\n" + "!"*50)
        print("  WARNING: CAPCUT AUTO-PILOT ENGAGED")
        print("!"*50)
        print("CRAVE is about to hijack your physical mouse and keyboard ")
        print("to operate CapCut UI buttons. Do NOT touch your mouse for the next 10 seconds.")
        
        reply = input("\nProceed? [Y / N]: ").strip().lower()
        if reply in ['y', 'yes', '']:
            return True
        return False

    def export_stylized_video(self, template_name: str, import_media: list) -> str:
        """Connects to CapCut (must be open) and initiates a template edit + export."""
        # 1. Ask User for permission to move the mouse
        if not self.prompt_mouse_seizure():
            return "ACTION ABORTED: User canceled CapCut UI automation."
            
        try:
            # 2. Connect to active CapCut window
            logger.info("Locating CapCut.exe window...")
            self.app = Application(backend="uia").connect(path="CapCut.exe", timeout=5)
            self.window = self.app.window(title_re="CapCut.*")
            
            # 3. Bring to front and Maximize
            self.window.set_focus()
            
            # The exact workflow requires clicking known coordinates or using standard shortcuts.
            # E.g. Ctrl+I (Import), Ctrl+E (Export).
            # Because CapCut buttons are dynamically rendered frameworks, pywinauto uses keystrokes optimally.
            
            print("[CapCut] Injecting simulated user keystrokes in 2 seconds...")
            time.sleep(2)
            
            # Example simulated workflow:
            # Import Media
            keyboard.send("ctrl+i")
            time.sleep(1)
            # Focus search bar / enter paths here via keyboard.write()
            # For demonstration, we simply trigger the export hotkey once media is allegedly on timeline
            
            print("[CapCut] Accessing Export Dialog...")
            keyboard.send("ctrl+e")
            time.sleep(2)
            
            # Hitting Enter inside the export dialog
            keyboard.send("enter")
            
            return "SUCCESS: CapCut rendering initiated via UI Pilot."
            
        except Exception as e:
            logger.error(f"PyWinAuto CapCut Hijack Failed: {e}")
            return f"ERROR: Could not automate CapCut. Make sure CapCut is currently open on desktop. ({e})"
