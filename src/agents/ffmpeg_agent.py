"""
CRAVE Phase 7 - FFmpeg Automation Agent
Provides programmatic, headless video editing using local FFmpeg binaries.
Instead of manual UI, it accepts AI-generated JSON "Editing Scripts" to apply 
complex mathematical cuts and stylistic overlays completely autonomously.
"""

import os
import subprocess
import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger("crave.agents.ffmpeg")

class FFmpegAgent:
    def __init__(self):
        # The user has mapped this in verify_env previously.
        self.ffmpeg_path = os.environ.get("FFMPEG_PATH", "ffmpeg") 

    def _run_cmd(self, args: List[str]) -> str:
        """Executes a raw FFmpeg subprocess command."""
        try:
            cmd = [self.ffmpeg_path] + args
            logger.info(f"Running FFmpeg script: {' '.join(cmd)}")
            
            # Run without opening a visible cmd window
            proc = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True,
                # Hide console window on Windows
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if proc.returncode == 0:
                return f"SUCCESS: Video rendered successfully to output."
            else:
                return f"ERROR (Code {proc.returncode}): {proc.stderr[-1000:]}"
                
        except Exception as e:
            return f"CRITICAL FFmpeg ERROR: {e}"

    def apply_ai_edit_script(self, input_video: str, output_video: str, edit_script: Dict[str, Any]) -> str:
        """
        Takes an AI-generated editing script and maps it into FFmpeg arguments.
        Example Script:
        {
            "clips": [ {"start": "00:00:00", "end": "00:00:15"} ],
            "subtitles": "path/to/whisper.srt",
            "style": { "font": "Arial", "color": "yellow", "size": 24 }
        }
        """
        if not os.path.exists(input_video):
            return "ERROR: Source video file not found."

        # Base arguments
        args = ["-y", "-i", input_video]
        
        # 1. Trimming Logic
        clips = edit_script.get("clips", [])
        if clips:
            # For simplicity in this v1 agent, if there's only 1 clip, just trim it.
            # (Complex multi-clip concatenation requires an intermediate text file for FFmpeg to read)
            if len(clips) == 1:
                args.extend(["-ss", clips[0]["start"], "-to", clips[0]["end"]])
        
        # 2. Advanced Filters (Subtitles & Styling)
        filters = []
        subs = edit_script.get("subtitles")
        if subs and os.path.exists(subs):
            # Escape paths for FFmpeg filter syntax
            safe_subs = subs.replace("\\", "/").replace(":", "\\:")
            # Inject basic styling params
            style = edit_script.get("style", {})
            font = style.get("font", "Arial")
            color = style.get("color", "yellow")
            size = str(style.get("size", "24"))
            
            sub_filter = f"subtitles='{safe_subs}':force_style='FontName={font},FontSize={size},PrimaryColour=&H00{color}&'"
            filters.append(sub_filter)
            
        if filters:
            args.extend(["-vf", ",".join(filters)])
            
        # Optimization: Fast rendering, streaming copy if no filters, etc.
        if not filters:
            args.extend(["-c", "copy"]) # Blazing fast raw cut
        else:
            args.extend(["-c:v", "libx264", "-crf", "23", "-preset", "fast", "-c:a", "aac"])

        args.append(output_video)
        
        return self._run_cmd(args)

    def extract_audio(self, input_video: str, output_audio: str) -> str:
        """Extracts audio to feed to Faster-Whisper for automated transcript generation."""
        args = ["-y", "-i", input_video, "-q:a", "0", "-map", "a", output_audio]
        return self._run_cmd(args)
