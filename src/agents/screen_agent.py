"""
CRAVE Phase 7 - Screen Agent
Captures the screen in-memory using mss and passes it natively to Gemma 3 Vision.
No files are saved to disk.
"""

import sys
import os
import base64
import ollama
import mss
from PIL import Image
import io

class ScreenAgent:
    def __init__(self):
        self.model = "gemma3:12b-it-q4_K_M"

    def _capture_screen_b64(self) -> str:
        """Takes a screenshot and returns it as a base64 encoded string."""
        with mss.mss() as sct:
            # Capture the primary monitor
            monitor = sct.monitors[1]  
            sct_img = sct.grab(monitor)
            
            # Convert mss Image to PIL Image
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Compress image slightly to save RAM/VRAM before sending to Gemma 3
            # 1920x1080 is often big enough; resize if extremely large to save token space
            max_size = (1920, 1080)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save to in-memory bytes buffer as JPEG
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=80)
            img_bytes = buffer.getvalue()
            
            # Convert to base64
            b64_str = base64.b64encode(img_bytes).decode('utf-8')
            return b64_str

    def analyze_screen(self, prompt: str = "Describe what is currently on my screen in detail.") -> str:
        """Captures screen and sends to Gemma 3 with the given prompt."""
        try:
            print("[ScreenAgent] Capturing screen in memory...")
            b64_image = self._capture_screen_b64()
            
            print(f"[ScreenAgent] Passing vision context to {self.model}...")
            response = ollama.chat(
                model=self.model,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [b64_image]
                }]
            )
            return response.get('message', {}).get('content', "No response.")
        
        except Exception as e:
            msg = f"[ScreenAgent] Error analyzing screen: {e}"
            print(msg)
            return msg
