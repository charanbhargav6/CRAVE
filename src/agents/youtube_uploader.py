"""
CRAVE Phase 11 - YouTube Uploader
Save to: D:/CRAVE/src/agents/youtube_uploader.py

Securely uploads videos to YouTube using OAuth2 credentials.
Requires D:/CRAVE/config/youtube_client_secret.json to be present.
"""

import os
import sys
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from src.core.audio_utils import crave_root
from src.security.encryption import crypto_manager

# Required scopes for uploading to YouTube
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

class YouTubeUploader:
    def __init__(self):
        self.config_dir = os.path.join(crave_root(), "config")
        self.vault_dir = os.path.join(crave_root(), "data", "vault")
        
        self.raw_secret_file = os.path.join(self.config_dir, "youtube_client_secret.json")
        self.enc_secret_file = os.path.join(self.vault_dir, "youtube_client_secret.enc")
        
        self.youtube = None

    def _get_client_config(self) -> dict:
        """Securely reads the Google API secret JSON. Encrypts it if unencrypted."""
        # 1. If unencrypted file exists, encrypt it and delete original!
        if os.path.exists(self.raw_secret_file):
            print(f"[YouTube] Securing raw credentials into Vault...")
            crypto_manager.encrypt_file(self.raw_secret_file, self.enc_secret_file)
            
            # Secure delete
            size = os.path.getsize(self.raw_secret_file)
            with open(self.raw_secret_file, "wb") as f:
                f.write(os.urandom(size))
            os.remove(self.raw_secret_file)
            print(f"[YouTube] Raw credentials destroyed. Vault secured.")

        # 2. If encrypted file doesn't exist, we can't proceed
        if not os.path.exists(self.enc_secret_file):
            return {}

        # 3. Decrypt into memory (never drops plaintext to disk)
        temp_decrypted = os.path.join(self.vault_dir, "temp_yt.json")
        if crypto_manager.decrypt_file(self.enc_secret_file, temp_decrypted):
            try:
                with open(temp_decrypted, "r") as f:
                    config = json.load(f)
                return config
            finally:
                os.remove(temp_decrypted)
        return {}

    def authenticate(self, channel_name: str = "main") -> bool:
        """Authenticate using OAuth2 for a specific channel name."""
        client_config = self._get_client_config()
        if not client_config:
            print("[YouTube] Missing or corrupted credentials in Vault! Please add youtube_client_secret.json.")
            return False

        # Support multiple channels via unique token files
        token_file = os.path.join(self.config_dir, f"youtube_token_{channel_name}.json")

        creds = None
        # Load existing tokens if available
        if os.path.exists(token_file):
            try:
                creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            except Exception as e:
                print(f"[YouTube] Could not read existing token for '{channel_name}': {e}")

        # If there are no valid credentials, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"[YouTube] Token refresh failed: {e}")
                    creds = None
            
            if not creds:
                try:
                    print(f"[YouTube] Launching OAuth consent screen for channel: '{channel_name}'...")
                    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    print(f"[YouTube] Authentication failed: {e}")
                    return False
            
            # Save the credentials for the next run specific to this channel
            with open(token_file, 'w') as token:
                token.write(creds.to_json())

        try:
            self.youtube = build('youtube', 'v3', credentials=creds)
            return True
        except Exception as e:
            print(f"[YouTube] Failed to build YouTube service: {e}")
            return False

    def upload_video(self, video_path: str, title: str, description: str, tags: list, is_short: bool = True, privacy="private", channel_name="main") -> str:
        """
        Uploads a video file to a specific YouTube channel.
        """
        if not self.youtube:
            success = self.authenticate(channel_name)
            if not success:
                return "Auth Failed"

        if not os.path.exists(video_path):
            print(f"[YouTube] Video file not found: {video_path}")
            return "File Not Found"

        print(f"[YouTube] Preparing upload to '{channel_name}': '{title}'...")
        
        if is_short and "#shorts" not in description.lower():
            description += "\n\n#shorts"
            if "shorts" not in tags and "#shorts" not in tags:
                tags.append("shorts")

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': '22'
            },
            'status': {
                'privacyStatus': privacy,
                'selfDeclaredMadeForKids': False
            }
        }

        try:
            media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
            
            request = self.youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"[YouTube] Uploading... {int(status.progress() * 100)}%")

            video_id = response.get('id')
            print(f"[YouTube] Upload Complete on '{channel_name}'! Video ID: {video_id}")
            return video_id
            
        except Exception as e:
            print(f"[YouTube] Upload Failed: {e}")
            return f"Upload Error: {e}"

if __name__ == "__main__":
    client = YouTubeUploader()
    if client.authenticate("gaming"):
        print("Auth success! Token saved for 'gaming' channel.")
