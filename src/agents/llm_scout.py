"""
CRAVE Phase 12 — Multi-Platform LLM Scout
Save to: D:\\CRAVE\\src\\agents\\llm_scout.py

Researches trending LLM projects across trusted platforms:
  - GitHub (trending repos)
  - HuggingFace (trending models)
  - Papers with Code (latest papers)
  - Reddit r/LocalLLaMA (community discoveries)

Feeds actionable findings to the SelfModifier for sandbox testing.
"""

import os
import json
import logging
import time
from datetime import datetime

logger = logging.getLogger("crave.agents.llm_scout")

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")


class LLMScout:
    """Searches multiple trusted platforms for LLM improvements."""

    def __init__(self, router=None):
        self.router = router
        self.results_dir = os.path.join(CRAVE_ROOT, "data", "scout_reports")
        os.makedirs(self.results_dir, exist_ok=True)

    # ── Platform Scrapers ────────────────────────────────────────────────────

    def _search_github(self, query: str = "LLM", limit: int = 5) -> list[dict]:
        """Search GitHub for trending repos via public REST API (no auth needed)."""
        import urllib.request
        
        url = (
            f"https://api.github.com/search/repositories"
            f"?q={query}+language:python&sort=stars&order=desc&per_page={limit}"
        )
        
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "CRAVE-LLM-Scout/1.0",
                "Accept": "application/vnd.github.v3+json"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            
            repos = []
            for item in data.get("items", [])[:limit]:
                repos.append({
                    "platform": "GitHub",
                    "name": item.get("full_name", ""),
                    "description": item.get("description", "")[:200],
                    "stars": item.get("stargazers_count", 0),
                    "url": item.get("html_url", ""),
                    "updated": item.get("updated_at", ""),
                })
            return repos
        except Exception as e:
            logger.error(f"GitHub search failed: {e}")
            return []

    def _search_huggingface(self, query: str = "llm", limit: int = 5) -> list[dict]:
        """Search HuggingFace for trending models via public API."""
        import urllib.request
        
        url = f"https://huggingface.co/api/models?search={query}&sort=trending&limit={limit}"
        
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "CRAVE-LLM-Scout/1.0"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            
            models = []
            for item in data[:limit]:
                models.append({
                    "platform": "HuggingFace",
                    "name": item.get("modelId", ""),
                    "description": item.get("pipeline_tag", "N/A"),
                    "stars": item.get("likes", 0),
                    "url": f"https://huggingface.co/{item.get('modelId', '')}",
                    "updated": item.get("lastModified", ""),
                })
            return models
        except Exception as e:
            logger.error(f"HuggingFace search failed: {e}")
            return []

    def _search_papers_with_code(self, limit: int = 5) -> list[dict]:
        """Search Papers with Code for latest trending ML papers."""
        import urllib.request
        
        url = "https://paperswithcode.com/api/v1/papers/?ordering=-proceeding&items_per_page=5"
        
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "CRAVE-LLM-Scout/1.0"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            
            papers = []
            for item in data.get("results", [])[:limit]:
                papers.append({
                    "platform": "PapersWithCode",
                    "name": item.get("title", "")[:100],
                    "description": item.get("abstract", "")[:200],
                    "stars": 0,
                    "url": item.get("url_abs", ""),
                    "updated": item.get("published", ""),
                })
            return papers
        except Exception as e:
            logger.error(f"PapersWithCode search failed: {e}")
            return []

    def _search_reddit(self, subreddit: str = "LocalLLaMA", limit: int = 5) -> list[dict]:
        """Search Reddit for trending posts (public JSON API, no auth)."""
        import urllib.request
        
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
        
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "CRAVE-LLM-Scout/1.0"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            
            posts = []
            for child in data.get("data", {}).get("children", [])[:limit]:
                item = child.get("data", {})
                posts.append({
                    "platform": "Reddit",
                    "name": item.get("title", "")[:100],
                    "description": item.get("selftext", "")[:200],
                    "stars": item.get("score", 0),
                    "url": f"https://reddit.com{item.get('permalink', '')}",
                    "updated": "",
                })
            return posts
        except Exception as e:
            logger.error(f"Reddit search failed: {e}")
            return []

    # ── Main Scout Pipeline ──────────────────────────────────────────────────

    def scout(self, query: str = "LLM optimization") -> dict:
        """
        Full multi-platform research run.
        Returns combined findings + LLM analysis of actionable improvements.
        """
        logger.info(f"Starting multi-platform LLM scout for: '{query}'")
        
        all_findings = []
        all_findings.extend(self._search_github(query))
        all_findings.extend(self._search_huggingface(query))
        all_findings.extend(self._search_papers_with_code())
        all_findings.extend(self._search_reddit())

        if not all_findings:
            return {"findings": [], "analysis": "No results found across any platform.", "report_path": ""}

        # Sort by stars/relevance
        all_findings.sort(key=lambda x: x.get("stars", 0), reverse=True)

        # Save raw findings
        report_name = f"scout_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = os.path.join(self.results_dir, report_name)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(all_findings, f, indent=2)

        # Ask reasoning model to analyze
        analysis = ""
        if self.router:
            findings_text = json.dumps(all_findings[:15], indent=2)
            prompt = f"""You are CRAVE's Self-Improvement Analyst. 
I just scraped these trending LLM projects from GitHub, HuggingFace, PapersWithCode, and Reddit:

{findings_text}

Based on these findings, identify:
1. The top 3 most actionable techniques/tools that could improve a local AI assistant (me)
2. For each, explain WHY it would help and HOW to integrate it
3. Rate the difficulty (Easy/Medium/Hard)

Be concise and practical. Focus on things that can run on 16GB RAM with Ollama."""

            res = self.router.chat(
                prompt=prompt,
                system_prompt="You are a technical analyst. Be concise and actionable.",
                task_type="reasoning"
            )
            analysis = res.get("response", "Analysis failed.")

        return {
            "findings": all_findings,
            "analysis": analysis,
            "report_path": report_path,
        }
