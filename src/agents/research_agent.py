"""
CRAVE Phase 9 - Self-Learning & Research Engine (ResearchAgent)
Automates the discovery of new capabilities. It takes a massive query ("Learn MT5"),
mutes the local Voice system to conserve CPU context, invokes blazing fast API Models
via the ModelRouter, and perfectly formats the newly gained intelligence into 
a SKILL.md Markdown file in the $CRAVE_ROOT/Knowledge/skills/ directory.
"""

import os
import time
import logging
from src.core.model_router import ModelRouter

logger = logging.getLogger("crave.agents.research")

class ResearchAgent:
    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        # Reuse the orchestrator's router (has vault-loaded API keys) instead of creating a new empty one
        if orchestrator and hasattr(orchestrator, '_router') and orchestrator._router:
            self.router = orchestrator._router
        else:
            self.router = ModelRouter()
        
        # Determine Knowledge directory
        self.knowledge_dir = os.path.join(
            os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "Knowledge", "skills"
        )
        if not os.path.exists(self.knowledge_dir):
            os.makedirs(self.knowledge_dir, exist_ok=True)

    def learn_topic(self, topic: str):
        """
        The Karpathy Autoresearch Loop.
        1. Suppresses Orchestrator Voice.
        2. Fires complex prompts demanding pure mechanical code structure to the API models.
        3. Persists the JSON/MD permanently.
        """
        logger.info(f"Researching: '{topic}'... Muting Output Voice.")
        
        # Mute TTS if we are connected to the central loop to prevent glitching
        if self.orchestrator:
            self.orchestrator.set_silent_mode(True)
            self.orchestrator.set_state("thinking")
            
        try:
            # Stage 1: The Deep Seek Reasoner (API Route)
            prompt = f"""You are CRAVE's internal Research Engine. 
You need to master this topic: "{topic}".
Provide a completely mechanical, step-by-step tutorial written for a Python AI system. 
Output your entire response formatted natively as a Markdown Document titled SKILL.md.
Do not use fluff. Provide code blocks, API endpoints, or algorithmic structure only."""

            logger.info("Routing Deep Research query to Hybrid API...")
            
            # The ModelRouter naturally prioritizes the fastest API (Groq/OpenRouter) 
            # if is_private is explicitly False, heavily bypassing Ollama slowness!
            result = self.router.chat(prompt=prompt)
            report = result.get("response", "Research failed: no response from model.")
            
            # Stage 2: Artifact Generation
            filename = topic.replace(" ", "_").replace("/", "").lower()[:20] + "_skill.md"
            filepath = os.path.join(self.knowledge_dir, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(report)
                
            logger.info(f"SKILL Acquired: {filepath}")
            
            # Stage 3: Index into ChromaDB vector store for semantic recall
            try:
                from src.core.knowledge_store import index_skill
                index_skill(filepath)
            except Exception:
                pass  # ChromaDB not installed — skill still saved to disk
            
            # Return system to normal
            if self.orchestrator:
                self.orchestrator.set_silent_mode(False)
                self.orchestrator.set_state("idle")
            
            return f"Research complete. I have acquired a new skill. The intelligence artifact is permanently saved at: {filepath}"
            
        except Exception as e:
            logger.error(f"Research Loop Crash: {e}")
            if self.orchestrator:
                self.orchestrator.set_silent_mode(False)
            return f"My deep research loop failed: {str(e)}"
