"""
CRAVE — Tool-Calling Router (Agentic AI Upgrade)
==================================================
Replaces the old keyword-based intent classifier with LLM tool-calling.

How modern agentic AIs work (Claude, Gemini, Claw):
  1. User says something (even with typos)
  2. LLM reads it, UNDERSTANDS it, decides which tool to call
  3. LLM outputs a structured JSON with tool name + parameters
  4. System executes the tool and returns result

This module defines CRAVE's tool registry and the LLM prompt that
teaches the model how to pick the right tool.
"""

import os
import json
import logging
from typing import Optional

logger = logging.getLogger("crave.tool_router")

# ── User path aliases ────────────────────────────────────────────────────────
USER_HOME = os.path.expanduser("~")
PATH_ALIASES = {
    "desktop":   os.path.join(USER_HOME, "Desktop"),
    "documents": os.path.join(USER_HOME, "Documents"),
    "downloads": os.path.join(USER_HOME, "Downloads"),
    "crave":     os.environ.get("CRAVE_ROOT", r"D:\CRAVE"),
}


# ── Tool Definitions ─────────────────────────────────────────────────────────
# Each tool is what the LLM can "call". The LLM picks one based on
# UNDERSTANDING the user's message — no keywords needed.

TOOLS = [
    {
        "name": "chat",
        "description": "General conversation, greetings, opinions, knowledge questions, explanations, learning. Use this for anything that is a normal conversation or question that does NOT need a specific action.",
        "parameters": {}
    },
    {
        "name": "create_file",
        "description": "Create, write, save, or generate a file, document, script, code, text file, PDF, presentation, spreadsheet, or any file to disk. Use when the user wants something SAVED as a file.",
        "parameters": {
            "filename": "The file name with extension (e.g. notes.txt, script.py, report.md)",
            "save_location": "Where to save: 'desktop', 'documents', 'downloads', or an absolute path. Default: 'desktop'",
            "description": "What the file should contain — the user's request rephrased as a content instruction"
        }
    },
    {
        "name": "open_app",
        "description": "Open, launch, or start an application, website, or program on the computer.",
        "parameters": {
            "target": "The app name or website URL to open"
        }
    },
    {
        "name": "close_app",
        "description": "Close, kill, or stop a running application or process.",
        "parameters": {
            "target": "The app name or process to close"
        }
    },
    {
        "name": "web_search",
        "description": "Search the internet for current/live/real-time information: news, weather, scores, prices, events, facts that change over time. Also use for jokes, random facts.",
        "parameters": {
            "query": "The search query"
        }
    },
    {
        "name": "screen_analyze",
        "description": "Look at, analyze, read, or describe what is currently on the user's screen or monitor.",
        "parameters": {
            "prompt": "What to look for or describe about the screen"
        }
    },
    {
        "name": "send_message",
        "description": "Send a message via email, WhatsApp, or Telegram to someone.",
        "parameters": {
            "platform": "email, whatsapp, or telegram",
            "recipient": "Who to send to (name, number, or email)",
            "message": "The message content"
        }
    },
    {
        "name": "trading",
        "description": "Anything about stock trading, forex, crypto, buying/selling financial instruments, backtesting, market analysis, positions, portfolio.",
        "parameters": {
            "action": "The specific trading request"
        }
    },
    {
        "name": "system_command",
        "description": "Run a shell/terminal command, system operation, or OS-level task.",
        "parameters": {
            "command": "The command or operation to perform"
        }
    },
    {
        "name": "generate_image",
        "description": "Generate, create, or make an image, picture, photo, artwork, or visual using AI.",
        "parameters": {
            "prompt": "Description of the image to generate",
            "style": "Optional style (realistic, cartoon, artistic, etc.)"
        }
    },
    {
        "name": "video_edit",
        "description": "Edit, cut, trim, subtitle, or manipulate a video file. Also create YouTube videos.",
        "parameters": {
            "action": "The specific video editing request"
        }
    },
    {
        "name": "hack_pentest",
        "description": "Penetration testing, security scanning, nmap, exploits, CTF challenges, Kali Linux operations.",
        "parameters": {
            "action": "The specific security/pentest request"
        }
    },
    {
        "name": "silent_mode",
        "description": "Toggle silent/quiet/mute mode on or off.",
        "parameters": {
            "enable": "true to enable silent mode, false to disable"
        }
    },
    {
        "name": "system_status",
        "description": "Check CRAVE's system status, health, or diagnostics.",
        "parameters": {}
    },
    {
        "name": "shutdown",
        "description": "Shutdown, exit, quit, or turn off CRAVE.",
        "parameters": {}
    },
    {
        "name": "self_modify",
        "description": "Add a feature, modify CRAVE's own code, implement something new in CRAVE itself.",
        "parameters": {
            "task": "What feature or modification to implement"
        }
    },
    {
        "name": "automate_gui",
        "description": "GUI automation, mouse control, keyboard macros, clicking on screen elements, TradingView drawing.",
        "parameters": {
            "action": "The automation task to perform"
        }
    },
    {
        "name": "download_file",
        "description": "Download a file from the internet — .exe, .zip, .pdf, .msi, any file type. Requires L3 security clearance for executable files.",
        "parameters": {
            "url": "The download URL",
            "filename": "Optional. Name to save the file as. If not provided, extracted from URL.",
            "save_location": "Where to save: 'desktop', 'documents', 'downloads'. Default: 'downloads'"
        }
    },
    {
        "name": "resume_session",
        "description": "Resume from last session, recall where we stopped, what we were working on, what tabs were open. Use when user asks 'where did we stop', 'what were we doing', 'continue from last time', 'resume'.",
        "parameters": {}
    },
    {
        "name": "refine_content",
        "description": "Use the Generator-Evaluator (GAN) quality loop to produce high-quality content. Use when user says 'make it perfect', 'refine this', 'write a polished email/report/document', or when the task explicitly requires high quality output.",
        "parameters": {
            "task": "What to write or generate",
            "rubric": "Quality criteria to judge against"
        }
    },
]

# ── Build the LLM system prompt from tool definitions ────────────────────────

def _build_tool_prompt() -> str:
    """
    Generates the system prompt that teaches the LLM to pick tools.
    This is what makes CRAVE understand natural language like Claude/Gemini.
    """
    tool_descriptions = []
    for t in TOOLS:
        params = ""
        if t["parameters"]:
            params = ", ".join([f'"{k}": "{v}"' for k, v in t["parameters"].items()])
            params = f" Parameters: {{{params}}}"
        tool_descriptions.append(f"  - {t['name']}: {t['description']}{params}")

    tools_text = "\n".join(tool_descriptions)

    return f"""You are CRAVE's action router. Given the user's message, decide which tool to call.

AVAILABLE TOOLS:
{tools_text}

RULES:
1. Output ONLY valid JSON. Nothing else. No explanation. No markdown.
2. Format: {{"tool": "tool_name", "params": {{...}}}}
3. If the user wants to CREATE/WRITE/SAVE any kind of file, ALWAYS use "create_file" — NOT "open_app".
4. If no specific action is needed, use "chat".
5. Understand the user's INTENT even if they have typos, grammatical errors, or unclear phrasing.
6. For "create_file": always extract filename, save_location, and description.
   - If user says "desktop" or "on my desktop", set save_location to "desktop"
   - If user says "documents" or "in documents", set save_location to "documents"
   - If no location specified, default save_location to "desktop"
7. "creat a fle" = create_file. "opn chrome" = open_app. Understand through typos.
8. For questions about prices, weather, scores, news, or anything that changes daily, use "web_search".

EXAMPLES:
User: "create a file named n.txt and save on desktop"
Output: {{"tool": "create_file", "params": {{"filename": "n.txt", "save_location": "desktop", "description": "Empty text file"}}}}

User: "open youtube"  
Output: {{"tool": "open_app", "params": {{"target": "youtube"}}}}

User: "what is the weather in hyderabad"
Output: {{"tool": "web_search", "params": {{"query": "weather in hyderabad today"}}}}

User: "creat a python scrpt that prints hello world and save it on desktp"
Output: {{"tool": "create_file", "params": {{"filename": "hello.py", "save_location": "desktop", "description": "Python script that prints hello world"}}}}

User: "hey how are you"
Output: {{"tool": "chat", "params": {{}}}}

User: "analyz my scren"
Output: {{"tool": "screen_analyze", "params": {{"prompt": "Describe what is on screen"}}}}

USER MESSAGE: """


TOOL_ROUTER_PROMPT = _build_tool_prompt()


def resolve_save_path(filename: str, save_location: str) -> str:
    """
    Resolves user-friendly path aliases to actual filesystem paths.
    
    "desktop"    -> C:/Users/chara/Desktop/filename
    "documents"  -> C:/Users/chara/Documents/filename
    "D:\\projects" -> D:\\projects\\filename
    """
    loc = save_location.lower().strip()

    # Check aliases
    if loc in PATH_ALIASES:
        base = PATH_ALIASES[loc]
    elif os.path.isabs(save_location):
        base = save_location
    else:
        # Default to desktop
        base = PATH_ALIASES.get("desktop", USER_HOME)

    os.makedirs(base, exist_ok=True)
    return os.path.join(base, filename)


def parse_tool_response(raw: str) -> dict:
    """
    Robustly parse the LLM's tool-calling JSON output.
    Handles markdown wrapping, extra text, and common LLM formatting quirks.
    """
    # Strip markdown code blocks
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    # Try to find JSON object in the text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    try:
        data = json.loads(text)
        tool = data.get("tool", "chat")
        params = data.get("params", {})
        return {"tool": tool, "params": params}
    except json.JSONDecodeError:
        logger.warning(f"[ToolRouter] Failed to parse LLM tool response: {raw[:200]}")
        return {"tool": "chat", "params": {}}
