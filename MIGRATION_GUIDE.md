# Moving CRAVE to a New PC (DPAPI Security Guide)

CRAVE's Secure Vault (Phase 5b) is protected by **Windows DPAPI**. 
This is military-grade local encryption. It means your `.master_key.dpapi` is mathematically tied to your unique Windows User Account. 

If someone steals your laptop's hard drive and plugs it into another PC, they cannot decrypt your API keys, because they cannot login using your Windows credentials. 

However, this means **you** cannot just copy the `D:\CRAVE` folder to a new laptop and expect it to automatically run. Windows on the new laptop will reject the vault.

Here is the exact step-by-step process to move CRAVE to a completely new laptop, while maintaining 100% of his autonomous, silent-boot behavior.

---

### Step 1: On the OLD Laptop (The Export)
Before you sell, format, or retire your old laptop, you must decrypt the vault back into plain-text files so you can carry them over.

1. Open PowerShell / CMD.
2. Navigate to your CRAVE folder:
   ```cmd
   cd D:\CRAVE
   .venv\Scripts\activate
   ```
3. Run the following Python commands to spit your encrypted keys back out as plain-text:
   ```cmd
   python -c "from src.security.encryption import crypto_manager; crypto_manager.decrypt_file('data/vault/.env.enc', '.env')"
   python -c "from src.security.encryption import crypto_manager; crypto_manager.decrypt_file('data/vault/credentials.json.enc', 'data/credentials.json')"
   ```
4. Look in your `D:\CRAVE` root folder. You will see your raw `.env` file containing your Telegram, Alpaca, and Groq keys, and `credentials.json` containing your L2/L4 hashes.

### Step 2: The Migration
1. Copy the entire `D:\CRAVE` folder to a USB drive or cloud drive.
   > **Note:** DO NOT copy the `D:\CRAVE\data\vault\` folder. It is totally useless on the new PC.
2. Paste the folder into `D:\CRAVE` on your **NEW Laptop**.

### Step 3: On the NEW Laptop (The Re-Lock)
Now that CRAVE is on the new laptop, we need him to eat the raw files you exported and generate a brand-new DPAPI master key permanently tied to your *new* laptop.

1. Open CMD as Administrator on the new laptop.
2. Ensure you have installed the required python package:
   ```cmd
   cd D:\CRAVE
   .venv\Scripts\activate
   pip install pywin32
   ```
3. Run CRAVE:
   ```cmd
   python main.py
   ```

### What Happens Automatically
When you run `main.py` on the new laptop, the `encryption.py` module will wake up and realize its DPAPI signature doesn't match the new OS.
- It will instantly generate a **NEW** Master Key.
- It will lock that key using your new laptop's Windows credentials.
- It will find your raw `.env` and `credentials.json` files.
- It will encrypt them into `data/vault/`.
- **It will permanently shred and delete the plain-text `.env` file from the disk.**

Your vault is now 100% locked and secured to the new PC.

---

### FAQ

**"Wait, does CRAVE ever ask me to type a Vault Password?"**
**NO.** He will never ask you for a password because Windows DPAPI is quietly doing the math in the background using your Active Windows login session. At 8:00 AM, when Windows Task Scheduler runs the script, the vault cracks itself open automatically and silently. 

**"What if my old laptop's motherboard fries and I completely lose the OS, and I never did Step 1?"**
Because you didn't do Step 1, the vault cannot be decrypted. You will simply have to log into Groq, Gemini, and Telegram on your phone/browser, generate completely new API keys, paste them into a new `.env` file, setup your 6-digit PINs again, and run `main.py` on your new laptop. You only lose the *keys*, not your CRAVE code!
