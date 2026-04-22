"""
CRAVE Phase E — PentAGI Installer
Native Python script to download and configure PentAGI's local Docker environment.
"""

import os
import sys
import subprocess
import urllib.request
import zipfile

def install_pentagi():
    print("=== CRAVE Autonomous Security: PentAGI Setup ===")
    
    install_dir = os.path.join(os.path.dirname(__file__), "pentagi")
    os.makedirs(install_dir, exist_ok=True)
    
    print(f"[1/4] Preparing PentAGI directory at {install_dir}")
    
    # Download latest installer (assuming windows/amd64 based on OS)
    zip_path = os.path.join(install_dir, "installer.zip")
    url = "https://pentagi.com/downloads/windows/amd64/installer-latest.zip"
    
    print(f"[2/4] Downloading PentAGI installer from {url} ...")
    try:
        # User-agent spoofing if needed
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(zip_path, 'wb') as out_file:
            out_file.write(response.read())
            
        print("[3/4] Extracting components...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(install_dir)
            
        # Clean up
        os.remove(zip_path)
        
        print("[4/4] Configuring .env for Local Ollama bridging...")
        env_path = os.path.join(install_dir, ".env")
        with open(env_path, "w") as f:
            f.write("OLLAMA_SERVER_URL=http://host.docker.internal:11434\n")
            f.write("PENTAGI_MODE=local\n")
            
        print("\n[SUCCESS] PentAGI Installation Complete.")
        print("To start PentAGI, open Docker Desktop and run the extracted installer script.")
        print("Once running on port 8000, CRAVE's ThreatDetector will automatically bridge to it.")
        
    except Exception as e:
        print(f"\n[ERROR] Installation failed. Please install manually or check network. Error: {e}")

if __name__ == "__main__":
    install_pentagi()
