"""
CRAVE Phase 7 - D-ID AI Avatar Agent
Interacts securely via the encrypted Secure Vault API key to generate 
talking avatars from source images and local Kokoro synthesized audio.
"""

import os
import requests
import time
import logging

logger = logging.getLogger("crave.agents.did")

class DidAgent:
    def __init__(self):
        # Read from decrypted memory securely injected by Vault in main.py
        self.api_key = os.environ.get("DID_API_KEY", "")
        self.base_url = "https://api.d-id.com"
        self.headers = {
            "Authorization": f"Basic {self.api_key}",
            "Content-Type": "application/json"
        }

    def generate_avatar_video(self, source_image_url: str, text_to_say: str) -> str:
        """
        Calls D-ID /talks endpoint to create a speaking avatar.
        NOTE: Passing an audio_url from Kokoro TTS is better, but this v1
        uses D-ID's native text-to-speech for simplicity of API upload.
        """
        if not self.api_key:
            return "ERROR: D-ID API Key not found in Secure Vault (.env)."
            
        logger.info(f"Initiating D-ID Avatar Synthesis...")
        
        payload = {
            "source_url": source_image_url,
            "script": {
                "type": "text",
                "input": text_to_say,
                # Using a generic Microsoft Guy voice as fallback
                "provider": { "type": "microsoft", "voice_id": "en-US-GuyNeural" }
            }
        }
        
        try:
            # 1. Start generation
            response = requests.post(f"{self.base_url}/talks", json=payload, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            talk_id = data.get("id")
            
            if not talk_id:
                return f"API ERROR: Could not parse generation ID: {data}"
                
            print(f"[D-ID] Job {talk_id} submitted. Wait (10-20s) for rendering...")
            
            # 2. Polling for completion
            for _ in range(30): # max 60 seconds
                time.sleep(2)
                check_res = requests.get(f"{self.base_url}/talks/{talk_id}", headers=self.headers)
                check_data = check_res.json()
                status = check_data.get("status")
                
                if status == "done":
                    return f"SUCCESS: Download your video here: {check_data.get('result_url')}"
                elif status == "error":
                    return f"D-ID RENDERING ERROR: {check_data}"
                    
            return "ERROR: D-ID rendering timed out after 60 seconds."
            
        except Exception as e:
            return f"CRITICAL D-ID API Error: {e}"
