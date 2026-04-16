"""
CRAVE Phase 5b - Secure Vault
Uses Windows DPAPI to lock the master encryption key to the current Windows user.
"""

import os
import sys
import io
import logging
import subprocess
from pathlib import Path

# Fix for ModuleNotFoundError: No module named 'src'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from cryptography.fernet import Fernet
from dotenv import dotenv_values

try:
    import win32crypt
except ImportError:
    print("[Vault] ERROR: pywin32 not installed! Run `pip install pywin32`")
    sys.exit(1)

# Dedicated logging for the security vault
logger = logging.getLogger("crave.security.encryption")

def _find_crave_root() -> str:
    env_root = os.environ.get("CRAVE_ROOT")
    if env_root and os.path.isdir(env_root):
        return env_root
    default = "D:\\CRAVE"
    if os.path.isdir(default):
        return default
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config" / "hardware.json").exists():
            return str(parent)
    return default

CRAVE_ROOT = _find_crave_root()
VAULT_DIR = os.path.join(CRAVE_ROOT, "data", "vault")
# The actual Fernet keys used for file encryption, but encrypted by Windows DPAPI
MASTER_KEY_PATH = os.path.join(VAULT_DIR, ".master_key.dpapi")

ENV_PATH = os.path.join(CRAVE_ROOT, ".env")
ENV_ENC_PATH = os.path.join(VAULT_DIR, ".env.enc")
CREDS_PATH = os.path.join(CRAVE_ROOT, "data", "credentials.json")
CREDS_ENC_PATH = os.path.join(VAULT_DIR, "credentials.json.enc")

class CRAVEEncryption:
    def __init__(self):
        self._ensure_vault_exists()
        self.key = self._get_or_create_key()
        self.fernet = Fernet(self.key)

    def _ensure_vault_exists(self):
        """Creates the vault directory and applies rigid NTFS ACLs."""
        if not os.path.exists(VAULT_DIR):
            os.makedirs(VAULT_DIR, exist_ok=True)
            logger.info("Vault directory created.")
            
            # Apply NTFS ACL lockdown using icacls
            # /inheritance:r removes all inherited permissions (like Users group having read access)
            # /grant:r "%USERNAME%":(OI)(CI)F grants full control to current logged in Windows user
            # /grant:r "SYSTEM":(OI)(CI)F grants full control to SYSTEM
            try:
                username = os.environ.get("USERNAME", "")
                if username:
                    # Double-quotes around VAULT_DIR in case of spaces
                    cmd = f'icacls "{VAULT_DIR}" /inheritance:r /grant:r "{username}":(OI)(CI)F /grant:r "SYSTEM":(OI)(CI)F'
                    subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    logger.info("NTFS ACL lockdown applied exclusively to %s and SYSTEM.", username)
            except Exception as e:
                logger.error("Failed to apply NTFS ACL to vault: %s", e)

    def _get_or_create_key(self) -> bytes:
        """
        Loads the master key from disk and decrypts it via Windows DPAPI.
        If it doesn't exist, generates a new Fernet key and encrypts it via DPAPI.
        """
        if os.path.exists(MASTER_KEY_PATH):
            try:
                with open(MASTER_KEY_PATH, "rb") as f:
                    encrypted_key = f.read()
                # Unprotect DPAPI
                # Returns (description, raw_bytes)
                _, raw_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)
                return raw_key
            except Exception as e:
                logger.critical("FATAL: Failed to decrypt master key. Are you logged in as the correct Windows user? Error: %s", e)
                raise PermissionError("DPAPI Decryption failed. Cannot access CRAVE Vault.")

        # Create a new raw Fernet key
        logger.info("Generating NEW master key...")
        new_key = Fernet.generate_key()
        
        # Encrypt the new key using Windows DPAPI
        description = "CRAVE Master Vault Key"
        encrypted_key = win32crypt.CryptProtectData(new_key, description, None, None, None, 0)
        
        # Save the DPAPI encrypted blob to disk
        with open(MASTER_KEY_PATH, "wb") as f:
            f.write(encrypted_key)
            
        # Hide the file so it doesn't clutter
        try:
            os.system(f'attrib +h "{MASTER_KEY_PATH}"')
        except:
            pass
            
        logger.info("Master key generated and locked to current Windows User via DPAPI.")
        return new_key

    def encrypt_file(self, source: str, dest: str) -> bool:
        """Encrypts a generic file on disk using the master key."""
        if not os.path.exists(source):
            return False
        with open(source, "rb") as f:
            data = f.read()
        enc_data = self.fernet.encrypt(data)
        with open(dest, "wb") as f:
            f.write(enc_data)
        return True

    def decrypt_file(self, source: str, dest: str) -> bool:
        """Decrypts a generic file back to disk."""
        if not os.path.exists(source):
            return False
        with open(source, "rb") as f:
            enc_data = f.read()
        try:
            data = self.fernet.decrypt(enc_data)
            with open(dest, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            logger.error(f"Failed to decrypt {source}: {e}")
            return False

    def encrypt_env_file(self) -> bool:
        """Reads plain .env, creates .env.enc inside the Vault, and securely deletes .env"""
        if not os.path.exists(ENV_PATH):
            logger.warning("No .env found to encrypt. (Already encrypted?)")
            return False
            
        success = self.encrypt_file(ENV_PATH, ENV_ENC_PATH)
        if success:
            # Secure delete plain text .env: overwrite with random bytes then remove
            try:
                size = os.path.getsize(ENV_PATH)
                with open(ENV_PATH, "wb") as f:
                    f.write(os.urandom(size))
                os.remove(ENV_PATH)
                logger.info("Successfully encrypted .env into vault and securely deleted original.")
                return True
            except Exception as e:
                logger.error(f"Failed to securely delete plaintext .env: {e}")
                return False
        return False

    def decrypt_env_to_memory(self) -> bool:
        """
        Reads Vault/.env.enc, decrypts it, and loads directly into os.environ.
        NO plaintext file is written to disk.
        """
        if not os.path.exists(ENV_ENC_PATH):
            logger.warning("No .env.enc found in Vault to load into memory!")
            return False
            
        with open(ENV_ENC_PATH, "rb") as f:
            enc_data = f.read()
            
        try:
            data = self.fernet.decrypt(enc_data).decode("utf-8")
            # Parse as dotenv dynamically
            stream = io.StringIO(data)
            parsed_env = dotenv_values(stream=stream)
            
            # Inject securely into os.environ
            keys_loaded = 0
            for k, v in parsed_env.items():
                if v is not None:
                    os.environ[k] = v
                    keys_loaded += 1
                    
            logger.info("Autonomously injected %d API keys from DPAPI Vault directly into memory.", keys_loaded)
            return True
        except Exception as e:
            logger.error(f"Failed to decrypt .env.enc into memory: {e}")
            return False

    def is_env_encrypted(self) -> bool:
        """Checks if the .env file has been migrated into the vault."""
        return os.path.exists(ENV_ENC_PATH) and not os.path.exists(ENV_PATH)

# ── Lazy singleton (prevents vault access on import) ─────────────────────────
_crypto_instance = None

def _get_crypto_manager() -> CRAVEEncryption:
    """Lazy-load crypto manager only when first accessed."""
    global _crypto_instance
    if _crypto_instance is None:
        _crypto_instance = CRAVEEncryption()
    return _crypto_instance

class _CryptoProxy:
    """Proxy that behaves like CRAVEEncryption but lazy-loads on first use."""
    def __getattr__(self, name):
        return getattr(_get_crypto_manager(), name)

crypto_manager = _CryptoProxy()
