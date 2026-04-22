"""
CRAVE — Universal Intelligence Agent
=====================================
Handles ANY real-world question by combining:
  1. Fast-path APIs (cricket, weather, crypto — instant structured data)
  2. Web search (Tavily → DuckDuckGo fallback) + LLM summarization
  3. Visual results display (opens browser tab for rich content)

This agent makes CRAVE as knowledgeable as any cloud AI for current events,
prices, news, sports, and any real-time data query.
"""

import os
import re
import time
import logging
import requests
import subprocess
import webbrowser
from typing import Optional

logger = logging.getLogger("crave.agents.public_api")


class PublicApiAgent:
    """
    CRAVE's universal internet intelligence agent.
    Two-stage pipeline:
      Stage 1: Fast-path (structured APIs for common queries)
      Stage 2: Web search + LLM summarization (anything else)
    """

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        self._router = getattr(orchestrator, '_router', None) if orchestrator else None

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN ENTRY POINT
    # ─────────────────────────────────────────────────────────────────────────

    def handle_request(self, command: str) -> str:
        """
        Intelligently determine the best way to answer any real-world question.
        Fast-path for structured queries, web search for everything else.
        """
        cmd = command.lower().strip()

        # ── Stage 1: Fast-Path APIs (instant, structured, free) ────────────
        # These are faster and more accurate than web search for their domains.

        # Live Cricket / IPL
        if any(kw in cmd for kw in ["ipl", "cricket score", "live score", "match score"]):
            return self._get_cricket_scores()

        # Weather
        if any(kw in cmd for kw in ["weather", "temperature outside", "forecast"]):
            return self._get_weather(cmd)

        # Crypto prices
        if any(kw in cmd for kw in ["bitcoin price", "btc price", "eth price",
                                     "crypto price", "solana price"]):
            return self._get_crypto_prices(cmd)

        # Jokes
        if any(kw in cmd for kw in ["joke", "crack a joke", "tell me a joke",
                                     "crack me a joke", "say a joke"]):
            return self._get_joke()

        # Network recon
        if any(kw in cmd for kw in ["what is my ip", "my ip address", "network recon"]):
            return self._get_network_recon()

        # ── Stage 2: Universal Web Search + LLM Summarization ──────────────
        # For EVERYTHING else: petrol prices, war updates, events, any question.
        return self._web_search_and_summarize(command)

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 2: UNIVERSAL WEB SEARCH + LLM SUMMARIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def _web_search_and_summarize(self, query: str) -> str:
        """
        The universal intelligence engine.
        1. Search the web (Tavily → DuckDuckGo fallback)
        2. Feed raw results into LLM as context
        3. Return a clean, factual, spoken-friendly summary
        4. Open browser tab for visual details
        """
        logger.info(f"[WebSearch] Universal query: {query}")

        # ── Step 1: Web Search ─────────────────────────────────────────────
        search_results, source_urls, search_engine = self._perform_web_search(query)

        if not search_results:
            return (
                f"I searched the web for '{query}' but couldn't find relevant results. "
                "Try rephrasing your question or say 'open Google' to search manually."
            )

        # ── Step 2: Open browser tab for visual confirmation ───────────────
        if source_urls:
            try:
                # Open the top result in browser so user can see details
                top_url = source_urls[0]
                webbrowser.open(top_url)
                logger.info(f"[WebSearch] Opened browser tab: {top_url}")
            except Exception as e:
                logger.debug(f"[WebSearch] Browser open failed: {e}")

        # ── Step 3: LLM Summarization ──────────────────────────────────────
        if self._router:
            summary = self._summarize_with_llm(query, search_results, source_urls)
            if summary:
                return summary

        # ── Fallback: return raw search results if no LLM available ────────
        return self._format_raw_results(query, search_results, source_urls, search_engine)

    def _perform_web_search(self, query: str) -> tuple:
        """
        Try Tavily first (best quality), then DuckDuckGo (free fallback).
        Returns: (search_results: str, source_urls: list, engine_name: str)
        """
        # ── Try 1: Tavily (highest quality, uses vault key) ────────────────
        tavily_result = self._search_tavily(query)
        if tavily_result:
            return tavily_result

        # ── Try 2: DuckDuckGo (free, no API key needed) ───────────────────
        ddg_result = self._search_duckduckgo(query)
        if ddg_result:
            return ddg_result

        return ("", [], "none")

    def _search_tavily(self, query: str) -> Optional[tuple]:
        """Search using Tavily AI Search API."""
        try:
            tavily_key = os.environ.get("TAVILY_API_KEY", "")
            if not tavily_key:
                return None

            from tavily import TavilyClient
            client = TavilyClient(api_key=tavily_key)

            logger.info(f"[WebSearch] Tavily search: {query}")
            start = time.time()
            response = client.search(
                query=query,
                search_depth="basic",
                max_results=5,
                include_answer=True,
            )
            elapsed = time.time() - start
            logger.info(f"[WebSearch] Tavily responded in {elapsed:.1f}s")

            results = response.get("results", [])
            if not results:
                return None

            # Build structured results
            lines = []
            urls = []
            for r in results[:5]:
                title = r.get("title", "")
                content = r.get("content", "")
                url = r.get("url", "")
                lines.append(f"Source: {title}\nContent: {content}\nURL: {url}")
                if url:
                    urls.append(url)

            # Include Tavily's direct answer if available
            direct_answer = response.get("answer", "")
            if direct_answer:
                lines.insert(0, f"Direct Answer: {direct_answer}")

            return ("\n\n".join(lines), urls, "Tavily")

        except Exception as e:
            logger.warning(f"[WebSearch] Tavily failed: {e}")
            return None

    def _search_duckduckgo(self, query: str) -> Optional[tuple]:
        """Search using DuckDuckGo (free, no API key)."""
        try:
            from duckduckgo_search import DDGS
            logger.info(f"[WebSearch] DuckDuckGo search: {query}")
            start = time.time()

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))

            elapsed = time.time() - start
            logger.info(f"[WebSearch] DuckDuckGo responded in {elapsed:.1f}s with {len(results)} results")

            if not results:
                return None

            lines = []
            urls = []
            for r in results[:5]:
                title = r.get("title", "")
                body = r.get("body", "")
                href = r.get("href", "")
                lines.append(f"Source: {title}\nContent: {body}\nURL: {href}")
                if href:
                    urls.append(href)

            return ("\n\n".join(lines), urls, "DuckDuckGo")

        except Exception as e:
            logger.warning(f"[WebSearch] DuckDuckGo failed: {e}")
            return None

    def _summarize_with_llm(self, query: str, search_results: str,
                            source_urls: list) -> Optional[str]:
        """
        Feed search results into LLM to produce a clean, spoken-friendly summary.
        """
        try:
            system_prompt = (
                "You are CRAVE, an AI assistant summarizing real-time web search results.\n"
                "RULES:\n"
                "1. Answer the user's question directly using ONLY the provided search results.\n"
                "2. Be concise — 2-4 sentences for simple questions, more for complex ones.\n"
                "3. Include specific numbers, names, dates, and facts from the results.\n"
                "4. If the results don't contain a clear answer, say so honestly.\n"
                "5. Do NOT make up information that isn't in the search results.\n"
                "6. Format your response to be spoken aloud (no markdown, no bullet points).\n"
                "7. At the end, briefly mention where the info came from (e.g., 'according to Reuters').\n"
            )

            prompt = (
                f"USER QUESTION: {query}\n\n"
                f"WEB SEARCH RESULTS:\n{search_results}\n\n"
                f"Based on these search results, answer the user's question clearly and concisely."
            )

            res = self._router.chat(
                prompt=prompt,
                system_prompt=system_prompt,
                task_type="primary",
            )

            answer = res.get("response", "").strip()
            if answer and len(answer) > 10:
                # Append source info
                if source_urls:
                    answer += f"\n\nI've also opened the top result in your browser for more details."
                return answer

        except Exception as e:
            logger.error(f"[WebSearch] LLM summarization failed: {e}")

        return None

    def _format_raw_results(self, query: str, search_results: str,
                            source_urls: list, engine: str) -> str:
        """Fallback: format raw search results when LLM is unavailable."""
        lines = [f"Here's what I found searching for '{query}' via {engine}:\n"]

        for chunk in search_results.split("\n\n")[:3]:
            # Extract just the content lines
            for line in chunk.split("\n"):
                if line.startswith("Content:"):
                    content = line.replace("Content:", "").strip()
                    if content:
                        lines.append(f"• {content[:200]}")
                    break

        if source_urls:
            lines.append(f"\nI've opened the top result in your browser for full details.")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 1: FAST-PATH APIs (structured, instant)
    # ─────────────────────────────────────────────────────────────────────────

    # ── CRICKET / IPL ────────────────────────────────────────────────────────

    def _get_cricket_scores(self) -> str:
        """Fetch live cricket scores from ESPN public APIs (No key required)."""
        try:
            urls = [
                'https://site.api.espn.com/apis/site/v2/sports/cricket/8048/scoreboard',  # IPL
                'https://site.api.espn.com/apis/site/v2/sports/cricket/8039/scoreboard',  # ICC
            ]

            lines = []
            for url in urls:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    for e in data.get('events', []):
                        name = e.get('name', 'Match')
                        status = e.get('status', {}).get('type', {}).get('description', 'Unknown')
                        score_str = ''

                        for comp in e.get('competitions', []):
                            for comp_d in comp.get('competitors', []):
                                team = comp_d.get('team', {}).get('abbreviation', '')
                                score = comp_d.get('score', '')
                                if score:
                                    score_str += f'{team}: {score}  '

                        if score_str.strip():
                            lines.append(f'• {name} | {status} | {score_str.strip()}')
                        else:
                            lines.append(f'• {name} | {status}')

            if lines:
                return "Here are the live cricket scores:\n" + "\n".join(lines)

            return "No prominent cricket matches are currently scheduled or playing right now."

        except Exception as e:
            logger.debug(f"Cricket API error: {e}")
            # Fallback to web search for cricket
            return self._web_search_and_summarize("IPL cricket matches today live scores")

    # ── LIVE SPORTS (general) ────────────────────────────────────────────────

    def _get_live_sports(self, command: str) -> str:
        """Route sports queries to the right handler or web search."""
        if any(kw in command for kw in ["ipl", "cricket"]):
            return self._get_cricket_scores()

        # For any other sport — use universal web search
        return self._web_search_and_summarize(command)

    # ── CRYPTO ───────────────────────────────────────────────────────────────

    def _get_crypto_prices(self, command: str) -> str:
        """Fetch prices from CoinGecko Public API."""
        try:
            logger.info("Fetching CoinGecko crypto data...")

            coins = "bitcoin,ethereum,solana"
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coins}&vs_currencies=usd&include_24hr_change=true"
            start_t = time.time()
            resp = requests.get(url, timeout=8)
            ms = int((time.time() - start_t) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                parts = []
                for coin_id, info in data.items():
                    price = info.get("usd", 0)
                    change = info.get("usd_24h_change", 0)
                    arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
                    parts.append(f"{coin_id.capitalize()}: ${price:,.2f} ({arrow}{abs(change):.1f}%)")
                return f"Live crypto prices ({ms}ms): {', '.join(parts)}."
            return f"CoinGecko API returned status {resp.status_code}."
        except Exception as e:
            logger.error(f"Crypto API failed: {e}")
            return self._web_search_and_summarize("cryptocurrency prices today bitcoin ethereum")

    # ── JOKES ────────────────────────────────────────────────────────────────

    def _get_joke(self) -> str:
        """Fetch a joke from JokeAPI."""
        try:
            url = "https://v2.jokeapi.dev/joke/Any?safe-mode&format=json&amount=1"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("type") == "single":
                    joke = data.get("joke", "No joke found.")
                else:
                    joke = f"{data.get('setup', '')} ... {data.get('delivery', '')}"
                return f"Here's one: {joke}"
            return "Joke API unreachable right now."
        except Exception as e:
            logger.error(f"Joke API failed: {e}")
            return "Couldn't fetch a joke right now."

    # ── NETWORK RECON ────────────────────────────────────────────────────────

    def _get_network_recon(self) -> str:
        """Fetch public IP from IPify."""
        try:
            start_t = time.time()
            resp = requests.get("https://api.ipify.org?format=json", timeout=5)
            ms = int((time.time() - start_t) * 1000)
            if resp.status_code == 200:
                ip = resp.json().get("ip", "Unknown")
                return f"Your current public IP address is {ip}. Resolved in {ms}ms."
            return "Network API unreachable."
        except Exception as e:
            logger.error(f"Network Recon failed: {e}")
            return "Failed to lookup network details."

    # ── WEATHER ──────────────────────────────────────────────────────────────

    def _get_weather(self, command: str) -> str:
        """Fetch weather from wttr.in (no API key needed)."""
        try:
            logger.info("Fetching weather...")

            city = ""
            for prefix in ["weather in ", "weather for ", "temperature in ",
                           "forecast for ", "weather of "]:
                if prefix in command:
                    city = command.split(prefix)[-1].strip().rstrip("?.!")
                    break

            url = f"https://wttr.in/{city}?format=j1"
            start_t = time.time()
            resp = requests.get(url, timeout=8, headers={"User-Agent": "CRAVE/1.0"})
            ms = int((time.time() - start_t) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current_condition", [{}])[0]
                area = data.get("nearest_area", [{}])[0]

                city_name = area.get("areaName", [{}])[0].get("value", "your area")
                temp_c = current.get("temp_C", "?")
                feels = current.get("FeelsLikeC", "?")
                desc = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
                humidity = current.get("humidity", "?")

                return (
                    f"Weather in {city_name}: {desc}, {temp_c}°C (feels like {feels}°C), "
                    f"humidity {humidity}%. Fetched in {ms}ms."
                )
            return "Weather service unreachable."
        except Exception as e:
            logger.error(f"Weather API failed: {e}")
            return self._web_search_and_summarize(f"current weather {command}")
