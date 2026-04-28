import psutil
found = False
trading_keywords = ['run_bot.py', 'trading_loop.py', 'paper_trading.py']
for p in psutil.process_iter(['name', 'cmdline']):
    try:
        cmdline = p.info.get('cmdline', [])
        if cmdline:
            for kw in trading_keywords:
                if any(kw in cmd for cmd in cmdline):
                    print(f"FOUND: {p.info['name']} with {cmdline}")
                    found = True
                    break
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
if not found:
    print("NO RUNNING TRADING PROCESSES DETECTED")
