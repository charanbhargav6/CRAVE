"""
CRAVE Phase 12 — WhatsApp Desktop Agent
Save to: D:\\CRAVE\\src\\agents\\whatsapp_agent.py

Sends WhatsApp messages by automating the WhatsApp Desktop app directly.
Uses pyautogui + pywinauto to:
  1. Open/focus WhatsApp Desktop
  2. Search for the contact by name
  3. Type and send the message
"""

import time
import os
import logging
import subprocess

logger = logging.getLogger("crave.agents.whatsapp")


class WhatsAppAgent:
    def __init__(self):
        from src.core.memory_bank import MemoryBank
        self.memory = MemoryBank()

    def _focus_whatsapp(self) -> bool:
        """Bring WhatsApp Desktop window to the foreground."""
        try:
            import pyautogui
            import pygetwindow as gw

            # Try to find existing WhatsApp window
            wins = gw.getWindowsWithTitle("WhatsApp")
            if wins:
                win = wins[0]
                if win.isMinimized:
                    win.restore()
                win.activate()
                time.sleep(0.5)
                return True

            # If not open, launch it
            logger.info("WhatsApp not open. Launching...")
            # Try Windows Store app first
            try:
                subprocess.Popen(["cmd", "/c", "start", "whatsapp:"], shell=True)
            except Exception:
                # Fallback: try common install paths
                paths = [
                    os.path.expandvars(r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe"),
                    os.path.expandvars(r"%PROGRAMFILES%\WhatsApp\WhatsApp.exe"),
                ]
                launched = False
                for p in paths:
                    if os.path.exists(p):
                        subprocess.Popen([p])
                        launched = True
                        break
                if not launched:
                    subprocess.Popen(["cmd", "/c", "start", "whatsapp:"], shell=True)

            # Wait for window to appear
            for _ in range(15):
                time.sleep(1)
                wins = gw.getWindowsWithTitle("WhatsApp")
                if wins:
                    wins[0].activate()
                    time.sleep(1)
                    return True

            logger.error("Could not find WhatsApp Desktop window.")
            return False

        except ImportError:
            logger.error("pyautogui or pygetwindow not installed.")
            return False
        except Exception as e:
            logger.error(f"Failed to focus WhatsApp: {e}")
            return False

    def send_whatsapp(self, phone_number: str = "", message: str = "", contact_name: str = "") -> str:
        """
        Send a WhatsApp message via the Desktop app.
        
        Args:
            phone_number: Phone number (used as fallback search term)
            message: The message text to send
            contact_name: Contact name to search for (preferred over phone_number)
        """
        task_id = f"wa_{int(time.time() * 1000)}"
        search_term = contact_name if contact_name else phone_number
        self.memory.log_task_start(task_id, "send_whatsapp", {"target": search_term, "msg_len": len(message)})

        try:
            import pyautogui

            # Step 1: Focus WhatsApp Desktop
            if not self._focus_whatsapp():
                self.memory.log_task_end(task_id, success=False, error_msg="Could not open WhatsApp")
                return "Failed to open WhatsApp Desktop. Is it installed?"

            time.sleep(1)

            # Step 2: Open search / new chat (Ctrl+K or Ctrl+F to search contacts)
            pyautogui.hotkey('ctrl', 'k')
            time.sleep(0.8)

            # Step 3: Type the contact name or phone number to search
            pyautogui.typewrite(search_term, interval=0.03) if search_term.isascii() else self._type_unicode(search_term)
            time.sleep(1.5)

            # Step 4: Press Enter to select the first matching contact
            pyautogui.press('enter')
            time.sleep(1)

            # Step 5: Type the message
            # Use clipboard for unicode support
            self._type_unicode(message)
            time.sleep(0.5)

            # Step 6: Send (Enter)
            pyautogui.press('enter')
            time.sleep(0.5)

            self.memory.log_task_end(task_id, success=True)
            return f"WhatsApp message sent to {search_term}."

        except Exception as e:
            self.memory.log_task_end(task_id, success=False, error_msg=str(e))
            logger.error(f"WhatsApp Desktop automation failed: {e}")
            return f"Failed to send WhatsApp message: {str(e)}"

    def _type_unicode(self, text: str):
        """Type unicode text by copying to clipboard and pasting."""
        import pyperclip
        import pyautogui

        # Save current clipboard
        try:
            original = pyperclip.paste()
        except Exception:
            original = ""

        # Copy message to clipboard and paste
        pyperclip.copy(text)
        time.sleep(0.2)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.3)

        # Restore original clipboard
        try:
            pyperclip.copy(original)
        except Exception:
            pass
