"""
CRAVE Phase 7 - Browser Automation Agent
Uses Headless Chromium via Playwright to navigate websites, handle dynamic 
JavaScript rendering, bypass simple checks, and scrape raw HTML or Markdown.
"""

import os
import threading
from playwright.sync_api import sync_playwright
import logging
from bs4 import BeautifulSoup
import re

logger = logging.getLogger("crave.agents.browser")

class BrowserAgent:
    def __init__(self):
        # Enforce that Playwright uses the localized D: drive browser installation
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ.get("CRAVE_ROOT", "D:\\CRAVE"), "tools", "playwright")
        self._lock = threading.Lock()

    def scrape_url(self, url: str, wait_for_network_idle: bool = True) -> str:
        """
        Navigates to a URL headlessly, waits for JS to execute, 
        and extracts clean textual content (Markdown-like).
        """
        if not url.startswith("http"):
            url = "https://" + url

        logger.info(f"Navigating to {url}...")
        
        try:
            with self._lock:
                with sync_playwright() as p:
                    # Launch Headless Chromium
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        viewport={"width": 1920, "height": 1080}
                    )
                    page = context.new_page()
                    
                    # Some modern sites require waiting until 'networkidle' (no more than 2 connections for 500ms)
                    wait_event = "networkidle" if wait_for_network_idle else "domcontentloaded"
                    
                    try:
                        page.goto(url, wait_until=wait_event, timeout=15000)
                    except Exception as e:
                        logger.warning(f"Timeout on {url}, falling back to raw DOM dump. Error: {e}")
                    
                    # Grab full raw HTML after JS rendering
                    raw_html = page.content()
                    browser.close()
            
            # Use BeautifulSoup to strip out script, style, and huge SVGs
            soup = BeautifulSoup(raw_html, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
                tag.decompose()
            
            # Extract clean text
            text = soup.get_text(separator="\n")
            
            # Cleanup excessive newlines and spaces
            clean_text = re.sub(r'\n\s*\n', '\n\n', text).strip()
            
            if len(clean_text) > 20000:
                # Truncate to save Ollama/Reasoning token limits (approx 5,000 words limit)
                clean_text = clean_text[:20000] + "\n\n[TRUNCATED BY CRAVE FOR CONTEXT LIMITS]"
                
            return clean_text
            
        except Exception as e:
            return f"CRITICAL BROWSER SCRAPING ERROR: {e}"
