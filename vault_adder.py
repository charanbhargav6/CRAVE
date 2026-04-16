"""
CRAVE SECURE VAULT ADDER
Use this script whenever you need to add a REAL API Key (like Alpaca/Binance) 
that holds actual money. 

HOW TO USE THIS SCRIPT SAFELY:
1. Open this file (vault_adder.py) in VS Code.
2. Under "my_new_keys", paste your secret keys between the quotes.
3. Open your terminal and run: `python vault_adder.py`
4. The script encrypts the keys into your DPAPI Windows Vault permanently.
5. DELETE this file or erase the keys from lines 13/14 immediately!
"""

import os
from src.security.encryption import crypto_manager

def securely_add_keys():
    # 1. Add your real keys here!
    my_new_keys = {
        "ALPACA_API_KEY": "YOUR_REAL_ALPACA_KEY_HERE",
        "ALPACA_SECRET_KEY": "YOUR_REAL_ALPACA_SECRET_HERE",
        # "BINANCE_API_KEY": "YOUR_BINANCE_KEY_HERE"
    }
    
    # 2. Decrypt the current Vault back to a plaintext .env file temporarily
    if os.path.exists("data/vault/.env.enc"):
        crypto_manager.decrypt_file("data/vault/.env.enc", ".env")
        print("[Vault] Decrypted successfully for appending.")
        
    # 3. Append your new keys to the file
    with open(".env", "a") as f:
        f.write("\n")
        for key, value in my_new_keys.items():
            if value and "YOUR_REAL" not in value: # Safety check to ignore placeholders
                f.write(f"{key}={value}\n")
                print(f"[Vault] Added {key} to the encryption block.")
                
    # 4. Re-Encrypt the Vault (This shreds the plaintext .env automatically)
    crypto_manager.encrypt_env_file()
    print("[Vault] SUCCCESS: Keys encrypted. The temporary .env file has been shredded.")
    print(">>> CRITICAL: Erase the keys from lines 13/14 in this script now! <<<")

if __name__ == "__main__":
    securely_add_keys()
