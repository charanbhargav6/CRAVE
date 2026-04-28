import psutil
found = False
for p in psutil.process_iter(['name', 'cmdline']):
    try:
        cmdline = p.info.get('cmdline', [])
        if cmdline and any('run_bot.py' in cmd for cmd in cmdline):
            print(f"FOUND: {p.info['name']} with {cmdline}")
            found = True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
if not found:
    print("NO RUNNING TRADING BOT DETECTED")
