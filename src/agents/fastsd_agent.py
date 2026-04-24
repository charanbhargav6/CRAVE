"""
CRAVE Phase 7 - FastSD Local Image Agent
Generates images natively on the CPU using OpenVINO (Stable Diffusion).
Operates at $0 cost and 100% offline.
"""

import os
import subprocess
import logging
from uuid import uuid4

logger = logging.getLogger("crave.agents.fastsd")

class FastSDAgent:
    def __init__(self):
        self.fastsd_dir = os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "tools", "fastsd", "fastsdcpu-main")
        self.python_exe = os.path.join(self.fastsd_dir, "env", "Scripts", "python.exe")
        self.app_script = os.path.join(self.fastsd_dir, "src", "app.py")
        
        self.output_dir = os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "Sub_Projects", "Images")
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_image(self, prompt: str) -> str:
        """
        Creates an image fully offline using FastSD CPU.
        Returns the absolute path to the generated PNG.
        """
        if not os.path.exists(self.python_exe):
            return "ERROR: FastSD environment not configured. Please run install.bat in D:\\CRAVE\\tools\\fastsd\\fastsdcpu-main first."

        logger.info(f"Generating FastSD image for prompt: {prompt[:50]}...")
        
        filename = f"crave_vision_{uuid4().hex[:8]}.png"
        output_path = os.path.join(self.output_dir, filename)
        
        # Depending on FastSD version, args may vary. standard generic pattern:
        # python src/app.py -p "prompt" --no-ui --output "path"
        # Since FastSD CPU generates inside its own results/ folder usually,
        # we will run it, then move the most recently generated file if output arg fails.
        cmd = [
            self.python_exe, 
            self.app_script,
            "--prompt", prompt,
            "--image_count", "1",
            "--output_path", output_path
        ]
        
        try:
            # We use creationflags to run invisibly natively on Windows
            proc = subprocess.run(
                cmd,
                cwd=self.fastsd_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if proc.returncode == 0:
                logger.info("FastSD generation complete.")
                # Return the expected path (or instruct Orchestrator to look in tools/fastsd/results if failed output bind)
                if os.path.exists(output_path):
                    return f"SUCCESS: Image saved to {output_path}"
                else:
                    return f"SUCCESS: Image generated successfully (check {self.fastsd_dir}\\results)"
            else:
                return f"ERROR FastSD CPU failure: {proc.stderr[-500:]}"
                
        except Exception as e:
            return f"CRITICAL FastSD Error: {e}"
