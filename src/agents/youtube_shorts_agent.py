"""
CRAVE Phase 11 - Autonomous YouTube Content Creator
Save to: D:/CRAVE/src/agents/youtube_shorts_agent.py

Features:
1. Script Generation (OpenRouter / Local LLM)
2. Image Prompting & Image Generation (Free APIs)
3. TTS Voiceover Generation (Edge-TTS)
4. FFmpeg Video Assembly (Image + Audio)
5. YouTube Secure Upload
"""

import os
import time
import json
import subprocess
import tempfile
import urllib.request
from typing import Optional

from src.core.audio_utils import crave_root
from src.core.tts import EdgeTTSEngine
from src.agents.youtube_uploader import YouTubeUploader

import asyncio

class YouTubeShortsAgent:
    def __init__(self, orchestrator=None):
        self._orchestrator = orchestrator # Access to ModelRouter
        self.workspace = os.path.join(crave_root(), "data", "youtube_workspace")
        os.makedirs(self.workspace, exist_ok=True)
        
    def generate_script(self, topic: str) -> dict:
        """Generates the script and image prompts."""
        print(f"[YouTubeAgent] Brainstorming script on topic: {topic}")
        
        sys_prompt = (
            "You are an expert YouTube Shorts and Video creator. Create a highly engaging script (under 60 seconds). "
            "Also generate a detailed prompt for an AI image generator to act as the primary visual for the video.\n"
            "Format EXACTLY as JSON:\n"
            '{"title": "Catchy SEO Title", "description": "SEO Description #shorts #trending", "tags": ["tag1", "tag2"], '
            '"voiceover_text": "The actual script to be spoken", '
            '"image_prompt": "A cinematic high resolution 9:16 aspect ratio image of..."}'
        )
        
        if self._orchestrator and self._orchestrator._router:
            res = self._orchestrator._router.chat(prompt=f"Topic: {topic}", system_prompt=sys_prompt)
            data_str = res.get("response", "")
        else:
            return {}
            
        data_str = data_str.strip()
        if data_str.startswith("```json"): data_str = data_str[7:]
        elif data_str.startswith("```"): data_str = data_str[3:]
        if data_str.endswith("```"): data_str = data_str[:-3]
        
        try:
            return json.loads(data_str.strip())
        except Exception as e:
            print(f"[YouTubeAgent] Failed to parse script JSON: {e}")
            return {}

    def fetch_image_free(self, prompt: str, output_path: str) -> bool:
        """
        Uses HuggingFace's free public pollination or Pollinations.ai API to generate free images natively.
        No API key required for Pollinations.ai!
        """
        print("[YouTubeAgent] Generating free AI Image via Pollinations...")
        safe_prompt = urllib.parse.quote(prompt)
        # Using 9:16 aspect ratio size: width=1080, height=1920
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1080&height=1920&nologo=true"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response, open(output_path, 'wb') as out_file:
                out_file.write(response.read())
            return os.path.exists(output_path)
        except Exception as e:
            print(f"[YouTubeAgent] Image Generation failed: {e}")
            return False

    def assemble_video(self, image_path: str, audio_path: str, output_path: str) -> bool:
        """Stitch 1 image and 1 audio track into a looping MP4 video using FFmpeg."""
        print("[YouTubeAgent] Assembling video track via FFmpeg...")
        
        ffmpeg_path = os.environ.get("FFMPEG_PATH", "ffmpeg")
        cmd = [
            ffmpeg_path, "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", "-shortest", 
            output_path
        ]
        
        try:
            subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return os.path.exists(output_path)
        except Exception as e:
            print(f"[YouTubeAgent] FFmpeg failed: {e}")
            return False

    def run_pipeline(self, topic: str, is_short: bool = True, upload_private: bool = True, channel_name: str = "main") -> str:
        """E2E Execution Pipeline."""
        # 1. Scripting
        script = self.generate_script(topic)
        if not script: return "Failed to generate script."
        
        safe_title = "".join(x for x in script["title"] if x.isalnum()).lower()[:20]
        timestamp = str(int(time.time()))
        
        image_file = os.path.join(self.workspace, f"{safe_title}_{timestamp}.jpg")
        audio_file = os.path.join(self.workspace, f"{safe_title}_{timestamp}.mp3")
        video_file = os.path.join(self.workspace, f"{safe_title}_{timestamp}.mp4")
        
        # 2. Voices
        print(f"[YouTubeAgent] Generating neural voiceover: {len(script['voiceover_text'])} chars...")
        try:
            engine = EdgeTTSEngine()
            engine.generate(script["voiceover_text"], audio_file)
        except Exception as e:
            return f"Audio generation failed: {e}"
            
        # 3. Images
        if not self.fetch_image_free(script["image_prompt"], image_file):
            return "Image generation failed."
            
        # 4. Assembly
        if not self.assemble_video(image_file, audio_file, video_file):
            return "Video assembly failed."
            
        # 5. Upload
        uploader = YouTubeUploader()
        privacy = "private" if upload_private else "public"
        vid = uploader.upload_video(
            video_path=video_file, 
            title=script["title"], 
            description=script["description"], 
            tags=script["tags"], 
            is_short=is_short, 
            privacy=privacy,
            channel_name=channel_name
        )
        
        # Clean up heavy temp files optionally
        try:
            os.remove(image_file)
            os.remove(audio_file)
            # Keep the MP4 just in case they want a local copy!
        except: pass
        
        return f"Pipeline Complete! YouTube Status: {vid}. Video saved locally to {video_file}."
