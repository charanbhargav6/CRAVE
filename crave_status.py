import os
import psutil
import webbrowser
import sqlite3
import pandas as pd
from pathlib import Path
import time

def is_bot_running():
    for p in psutil.process_iter(['name', 'cmdline']):
        try:
            if 'python' in p.info['name'].lower() or 'py' in p.info['name'].lower():
                cmdline = p.info.get('cmdline', [])
                if cmdline and any('run_bot.py' in cmd for cmd in cmdline):
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

def main():
    print("="*50)
    print(" CRAVE SYSTEM STATUS ".center(50))
    print("="*50)

    if is_bot_running():
        print("[+] CRAVE is ONLINE and running in the background.")
        print("[+] Opening the Live Dashboard...")
        # Give a small delay in case it was just started
        time.sleep(1)
        webbrowser.open("http://localhost:3000")
    else:
        print("[-] CRAVE is OFFLINE.")
        print("[-] Generating offline spreadsheet report from database...")
        
        db_path = Path(r"D:\CRAVE\data\trades.db")
        csv_path = Path(r"D:\CRAVE\data\offline_trades_report.csv")
        
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            try:
                # Get the last 200 trades
                df = pd.read_sql_query("SELECT * FROM trades ORDER BY id DESC LIMIT 200", conn)
                df.to_csv(csv_path, index=False)
                print(f"[+] Exported trades to {csv_path.name}")
                print("[+] Opening spreadsheet...")
                os.startfile(csv_path)
            except Exception as e:
                print(f"[!] Could not read trades: {e}")
            finally:
                conn.close()
        else:
            print("[!] No database found at D:\\CRAVE\\data\\trades.db. No offline data available.")
            
    print("\nPress any key to exit...")
    os.system("pause >nul")

if __name__ == "__main__":
    main()
