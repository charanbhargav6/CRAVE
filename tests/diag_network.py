import socket
import requests
import sys
import os

def check_host(host, port):
    try:
        socket.create_connection((host, port), timeout=5)
        return True
    except:
        return False

print("="*50)
print("🛡️ CRAVE NETWORK DIAGNOSTICS")
print("="*50)

# 1. Check Basic Internet
print(f"Checking Basic Internet (google.com:80)... ", end="")
if check_host("google.com", 80):
    print("✅ ONLINE")
else:
    print("❌ OFFLINE")

# 2. Check DNS Resolution
print(f"Checking DNS (api.telegram.org)... ", end="")
try:
    ip = socket.gethostbyname("api.telegram.org")
    print(f"✅ RESOLVED TO {ip}")
except:
    print("❌ FAILED TO RESOLVE")

# 3. Check Telegram Endpoints
print(f"Checking Telegram (api.telegram.org:443)... ", end="")
if check_host("api.telegram.org", 443):
    print("✅ REACHABLE")
else:
    print("❌ BLOCKED")

# 4. Check Gmail Endpoints
print(f"Checking Gmail SMTP (smtp.gmail.com:465)... ", end="")
if check_host("smtp.gmail.com", 465):
    print("✅ REACHABLE")
else:
    print("❌ BLOCKED")

print(f"Checking Gmail SMTP (smtp.gmail.com:587)... ", end="")
if check_host("smtp.gmail.com", 587):
    print("✅ REACHABLE")
else:
    print("❌ BLOCKED")

print("\n" + "="*50)
print("RECOMMENDATION:")
print("-" * 50)
print("If everything above says 'BLOCKED' but Internet is 'ONLINE':")
print("1. Your ISP or Windows Firewall is blocking these services.")
print("2. SOLUTION: Turn on a VPN and try the tests again.")
print("3. Check if an Antivirus (like Bitdefender/Norton) is blocking Python.")
print("="*50)
