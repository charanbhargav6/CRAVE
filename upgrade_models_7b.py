"""
CRAVE — Model Downsize Script
Run this when connected to WiFi to swap 14B models → 7B models.

What it does:
  1. Pulls qwen2.5:7b and deepseek-r1:7b from Ollama registry
  2. Updates hardware.json to point to the new models
  3. Removes the old 14B models to free ~18GB of disk space
  4. Runs a quick benchmark to confirm the speedup

Usage:
  python upgrade_models_7b.py

Estimated download: ~4.7GB (qwen2.5:7b) + ~4.7GB (deepseek-r1:7b) = ~9.4GB total
Estimated time on WiFi: 10-20 minutes
"""

import os
import sys
import json
import time
import subprocess
import requests

OLLAMA_URL = "http://127.0.0.1:11434"
HARDWARE_JSON = os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "config", "hardware.json")

# ── Models to install and remove ──────────────────────────────────────────────
NEW_MODELS = {
    "primary":   "qwen2.5:7b",
    "reasoning": "deepseek-r1:7b",
    # Vision stays the same — llama3.2-vision:11b has no smaller alternative
}

OLD_MODELS_TO_REMOVE = [
    "qwen2.5:14b",
    "deepseek-r1:14b",
]


def check_ollama_running():
    """Verify Ollama server is accessible."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except:
        return False


def pull_model(model_name: str):
    """Pull a model from the Ollama registry with progress output."""
    print(f"\n{'='*60}")
    print(f"  PULLING: {model_name}")
    print(f"{'='*60}")
    
    # Use subprocess to show live progress
    ollama_path = os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "Ollama", "App", "ollama.exe")
    result = subprocess.run(
        f"{ollama_path} pull {model_name}",
        shell=True,
        capture_output=False,  # Show output live
        text=True,
    )
    
    if result.returncode == 0:
        print(f"  ✅ {model_name} downloaded successfully!")
        return True
    else:
        print(f"  ❌ Failed to pull {model_name}")
        return False


def remove_model(model_name: str):
    """Remove an old model to free disk space."""
    print(f"  Removing {model_name}...", end=" ")
    try:
        ollama_path = os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "Ollama", "App", "ollama.exe")
        result = subprocess.run(
            f"{ollama_path} rm {model_name}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print("✅ Removed")
            return True
        else:
            print(f"⚠️ {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"⚠️ {e}")
        return False


def update_hardware_json():
    """Update hardware.json to point to the new 7B models."""
    print(f"\n{'='*60}")
    print(f"  UPDATING: hardware.json")
    print(f"{'='*60}")
    
    try:
        with open(HARDWARE_JSON, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # Backup the original
        backup_path = HARDWARE_JSON + ".backup_14b"
        if not os.path.exists(backup_path):
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            print(f"  📋 Backup saved: {backup_path}")
        
        # Update model references
        old_primary = config["models"]["primary"]
        old_reasoning = config["models"]["reasoning"]
        
        config["models"]["primary"] = NEW_MODELS["primary"]
        config["models"]["reasoning"] = NEW_MODELS["reasoning"]
        # Vision stays as-is (no 7B vision model available)
        
        with open(HARDWARE_JSON, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        
        print(f"  primary:   {old_primary} → {config['models']['primary']}")
        print(f"  reasoning: {old_reasoning} → {config['models']['reasoning']}")
        print(f"  vision:    {config['models']['vision']} (unchanged)")
        print(f"  ✅ hardware.json updated!")
        return True
        
    except Exception as e:
        print(f"  ❌ Failed to update hardware.json: {e}")
        return False


def quick_benchmark():
    """Run a quick speed test on the new models."""
    print(f"\n{'='*60}")
    print(f"  SPEED TEST: {NEW_MODELS['primary']}")
    print(f"{'='*60}")
    
    tests = [
        ("2+2", "What is 2+2?"),
        ("Intent", "Classify: what is the weather today"),
        ("Physics", "Explain gravity in 2 sentences"),
    ]
    
    for label, prompt in tests:
        try:
            start = time.time()
            r = requests.post(f"{OLLAMA_URL}/api/generate", json={
                "model": NEW_MODELS["primary"],
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 128}
            }, timeout=60)
            elapsed = time.time() - start
            
            data = r.json()
            tok_per_sec = data.get("eval_count", 0) / max(data.get("eval_duration", 1) / 1e9, 0.001)
            preview = data.get("response", "")[:60].replace("\n", " ")
            
            print(f"  {label:10s} | {elapsed:5.1f}s | {tok_per_sec:.1f} tok/s | {preview}...")
        except Exception as e:
            print(f"  {label:10s} | ERROR: {e}")
    
    # RAM check
    try:
        import psutil
        mem = psutil.virtual_memory()
        print(f"\n  RAM: {mem.available/1024**3:.1f}GB free / {mem.total/1024**3:.1f}GB total ({mem.percent}% used)")
    except:
        pass


def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║          CRAVE — Model Downsize: 14B → 7B               ║
║          Requires WiFi connection for downloads          ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # Step 0: Check Ollama is running
    if not check_ollama_running():
        print("❌ Ollama server is not running!")
        print("   Start it first: open Ollama app or run 'ollama serve'")
        sys.exit(1)
    print("✅ Ollama server detected\n")
    
    # Step 1: Pull new 7B models
    print("STEP 1/4: Downloading 7B models (requires WiFi)")
    print("-" * 60)
    
    success_count = 0
    for key, model in NEW_MODELS.items():
        if pull_model(model):
            success_count += 1
    
    if success_count < len(NEW_MODELS):
        print("\n⚠️ Some models failed to download. Fix your connection and re-run.")
        print("   The script is safe to run multiple times — it won't re-download existing models.")
        sys.exit(1)
    
    # Step 2: Update hardware.json
    print("\nSTEP 2/4: Updating configuration")
    print("-" * 60)
    update_hardware_json()
    
    # Step 3: Remove old 14B models
    print(f"\nSTEP 3/4: Removing old 14B models (~18GB freed)")
    print("-" * 60)
    for model in OLD_MODELS_TO_REMOVE:
        remove_model(model)
    
    # Step 4: Benchmark
    print("\nSTEP 4/4: Speed test")
    print("-" * 60)
    quick_benchmark()
    
    print(f"""
╔══════════════════════════════════════════════════════════╗
║                    ✅ UPGRADE COMPLETE                    ║
╠══════════════════════════════════════════════════════════╣
║  Primary : qwen2.5:7b      (~4.5GB RAM)                 ║
║  Reasoning: deepseek-r1:7b  (~4.5GB RAM)                ║
║  Vision  : llama3.2-vision:11b (unchanged)               ║
║                                                          ║
║  Expected speed: 20-30 tok/s (was 4 tok/s)               ║
║  RAM freed: ~4.5GB more headroom                         ║
║                                                          ║
║  Restart CRAVE to use the new models:                    ║
║    python main.py                                        ║
╚══════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    main()
