"""CRAVE Ollama Benchmark — measures local inference speed"""
import time
import json
import requests

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "qwen2.5:14b"

tests = [
    ("Simple", "What is 2+2?"),
    ("Medium Math", "Solve: integral of x^2 * e^x dx"),
    ("Physics", "Explain quantum entanglement in 3 sentences"),
    ("Complex", "A ball is thrown at 45 degrees with 20 m/s. Calculate max height, range, and time of flight. Show work."),
    ("Coding", "Write a Python binary search function"),
    ("Intent (1 token)", "Classify this command into one word (chat/system/public_api): what is the weather today"),
]

print(f"=== OLLAMA BENCHMARK ({MODEL}) ===")
print(f"{'Test':20s} | {'Time':7s} | {'Words':6s} | Preview")
print("-" * 80)

results = []
for label, prompt in tests:
    try:
        start = time.time()
        r = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 256, "temperature": 0.1}
        }, timeout=120)
        elapsed = time.time() - start
        
        data = r.json()
        response = data.get("response", "")
        word_count = len(response.split())
        tok_per_sec = data.get("eval_count", 0) / max(data.get("eval_duration", 1) / 1e9, 0.001)
        
        results.append((label, elapsed, word_count, tok_per_sec))
        preview = response.replace("\n", " ")[:60]
        print(f"{label:20s} | {elapsed:5.1f}s | {word_count:5d} | {preview}...")
        print(f"{'':20s} | tok/s: {tok_per_sec:.1f}")
    except Exception as e:
        print(f"{label:20s} | ERROR: {e}")
        results.append((label, -1, 0, 0))

print("\n" + "=" * 80)
avg_time = sum(r[1] for r in results if r[1] > 0) / max(len([r for r in results if r[1] > 0]), 1)
avg_tps = sum(r[3] for r in results if r[3] > 0) / max(len([r for r in results if r[3] > 0]), 1)
print(f"AVERAGE: {avg_time:.1f}s per query | {avg_tps:.1f} tokens/sec")

# RAM check
import psutil
mem = psutil.virtual_memory()
print(f"\nRAM: {mem.total/1024**3:.1f}GB total | {mem.used/1024**3:.1f}GB used | {mem.available/1024**3:.1f}GB free | {mem.percent}% utilized")
