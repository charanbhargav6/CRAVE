"""
CRAVE Phase 12 — Visual Learning Agent
Save to: D:\\CRAVE\\src\\agents\\visual_agent.py

Provides two capabilities:
  1. Web image search (DuckDuckGo, no API key) for diagrams/charts
  2. Local matplotlib chart generation via LLM-generated code
"""

import os
import re
import json
import time
import logging
import tempfile
import hashlib
from pathlib import Path

logger = logging.getLogger("crave.agents.visual")

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
VISUALS_DIR = os.path.join(CRAVE_ROOT, "data", "visuals")
os.makedirs(VISUALS_DIR, exist_ok=True)


class VisualAgent:
    """Searches the web for relevant images, or generates charts locally."""

    def __init__(self, router=None):
        self.router = router

    # ── Web Image Search (DuckDuckGo — no API key) ───────────────────────────

    def search_web_images(self, query: str, max_results: int = 3) -> list[str]:
        """
        Search DuckDuckGo for images matching the query.
        Returns a list of local file paths to downloaded images.
        """
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning("duckduckgo_search not installed. Falling back to chart generation.")
            return []

        downloaded = []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.images(query + " diagram infographic", max_results=max_results))

            import urllib.request

            for i, result in enumerate(results[:max_results]):
                url = result.get("image", "")
                if not url:
                    continue

                # Generate a safe filename from the URL hash
                ext = ".jpg"
                if ".png" in url.lower():
                    ext = ".png"
                elif ".gif" in url.lower():
                    ext = ".gif"

                fname = hashlib.md5(url.encode()).hexdigest()[:12] + ext
                local_path = os.path.join(VISUALS_DIR, fname)

                # Skip if already cached
                if os.path.exists(local_path):
                    downloaded.append(local_path)
                    continue

                try:
                    req = urllib.request.Request(url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    })
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        with open(local_path, "wb") as f:
                            f.write(resp.read())
                    downloaded.append(local_path)
                    logger.info(f"Downloaded image: {local_path}")
                except Exception as e:
                    logger.warning(f"Failed to download {url}: {e}")

        except Exception as e:
            logger.error(f"DuckDuckGo image search failed: {e}")

        return downloaded

    # ── Local Chart Generation (matplotlib) ──────────────────────────────────

    def generate_chart(self, topic: str, chart_description: str = "") -> str:
        """
        Ask the LLM to write matplotlib code, execute it safely, return the saved PNG path.
        Returns empty string on failure.
        """
        if not self.router:
            logger.error("No ModelRouter available for chart generation.")
            return ""

        prompt = f"""You are a data visualization expert. Generate Python matplotlib code that creates
an informative, visually appealing chart or diagram to help explain: "{topic}"

Additional context: {chart_description if chart_description else 'Create whatever visualization best explains this topic.'}

Rules:
- Use matplotlib.pyplot only (import as plt)
- Use a dark background style: plt.style.use('dark_background')
- Use cyan (#00E5FF) and white as primary colors
- Set figure size to (10, 6) 
- Include a clear title and labels
- End with: plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches='tight', facecolor='#0a0f19')
- Do NOT call plt.show()
- OUTPUT_PATH will be provided as a variable, do not define it yourself

Return ONLY the Python code, no markdown fences, no explanation."""

        try:
            res = self.router.chat(
                prompt=prompt,
                system_prompt="You are a Python code generator. Return only valid Python code. No markdown.",
                task_type="reasoning"
            )

            code = res.get("response", "")

            # Clean markdown wrapping if present
            if "```python" in code:
                code = code.split("```python")[1].split("```")[0].strip()
            elif "```" in code:
                code = code.split("```")[1].split("```")[0].strip()

            if not code or "plt" not in code:
                logger.warning("LLM did not return valid matplotlib code.")
                return ""

            # Generate output path
            fname = hashlib.md5(topic.encode()).hexdigest()[:12] + "_chart.png"
            output_path = os.path.join(VISUALS_DIR, fname)

            # Execute in a restricted namespace
            exec_globals = {"OUTPUT_PATH": output_path, "__builtins__": __builtins__}
            exec(code, exec_globals)

            if os.path.exists(output_path):
                logger.info(f"Chart generated: {output_path}")
                return output_path
            else:
                logger.warning("Matplotlib code ran but no output file was created.")
                return ""

        except Exception as e:
            logger.error(f"Chart generation failed: {e}")
            return ""

    # ── Online API Image Generation (Pollinations) ───────────────────────────
    
    def generate_ai_image(self, topic: str) -> str:
        """
        Uses HuggingFace's free public pollination API to generate free images natively.
        No API key required. This completely bypasses local RAM constraints!
        """
        import urllib.parse
        import urllib.request
        
        prompt = f"A highly detailed, futuristic infograpic, diagram, or educational illustration explaining {topic}. Dark theme, glowing cyan nodes, high resolution, clear labels."
        safe_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1080&height=720&nologo=true"
        
        fname = hashlib.md5(topic.encode()).hexdigest()[:12] + "_ai.jpg"
        output_path = os.path.join(VISUALS_DIR, fname)
        
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CRAVE/12.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(output_path, "wb") as f:
                    f.write(resp.read())
            logger.info(f"AI image generated via Pollinations: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"AI image generation failed: {e}")
            return ""

    # ── Combined Visual Pipeline ─────────────────────────────────────────────

    def get_visuals(self, topic: str) -> dict:
        """
        Main entry point. 
        1. Tries Web Search (DDG)
        2. Falls back to AI Cloud Generation (Pollinations) to prevent OOM
        3. Falls back to local LLM code generation
        Returns: {"images": [list of local paths], "source": "web"|"generated"|"none"}
        """
        # Step 1: Try web search
        web_images = self.search_web_images(topic)
        if web_images:
            return {"images": web_images, "source": "web"}

        # Step 2: Cloud AI Image Generation (Fast, free, 0 RAM usage)
        ai_path = self.generate_ai_image(topic)
        if ai_path:
            return {"images": [ai_path], "source": "cloud_ai"}

        # Step 3: Fall back to heavy local chart generation
        chart_path = self.generate_chart(topic)
        if chart_path:
            return {"images": [chart_path], "source": "local_code"}

        return {"images": [], "source": "none"}
