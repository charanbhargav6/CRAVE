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

import platform

_USE_DPAPI = False
_USE_KEYRING = False

if platform.system() == "Windows":
    try:
        import win32crypt
        _USE_DPAPI = True
    except ImportError:
        pass

if not _USE_DPAPI:
    try:
        import keyring
        _USE_KEYRING = True
    except ImportError:
        pass

if not _USE_DPAPI and not _USE_KEYRING:
    print("[Vault] WARNING: No secure key storage available.")
    print("  Windows: pip install pywin32")
    print("  Linux/macOS: pip install keyring")
    # Don't sys.exit — allow degraded operation with file-based key

# Dedicated logging for the security vault
logger = logging.getLogger("crave.security.encryption")

def _find_crave_root() -> str:
    env_root = os.environ.get("CRAVE_ROOT")
    if env_root and os.path.isdir(env_root):
        return env_root
    default = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
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
        Loads or creates the master Fernet key using the best available backend:
          1. Windows DPAPI (win32crypt) — key is locked to the current Windows user
          2. OS keyring (keyring lib)   — works on Linux/macOS/WSL
          3. Raw file fallback          — least secure, for environments without either
        """
        KEYRING_SERVICE = "crave-vault"
        KEYRING_ACCOUNT = "master-key"

        # ── Try loading an existing key ──────────────────────────────────
        if _USE_DPAPI and os.path.exists(MASTER_KEY_PATH):
            try:
                with open(MASTER_KEY_PATH, "rb") as f:
                    encrypted_key = f.read()
                _, raw_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)
                return raw_key
            except Exception as e:
                logger.critical("DPAPI decryption failed (wrong Windows user?): %s", e)
                raise PermissionError("DPAPI Decryption failed. Cannot access CRAVE Vault.")

        if _USE_KEYRING:
            stored = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
            if stored:
                logger.info("Master key loaded from OS keyring.")
                return stored.encode("utf-8")

        # Raw file fallback (unencrypted — least secure)
        raw_key_path = os.path.join(VAULT_DIR, ".master_key.raw")
        if os.path.exists(raw_key_path):
            with open(raw_key_path, "rb") as f:
                logger.warning("Master key loaded from RAW FILE (not encrypted at rest).")
                return f.read()

        # ── No existing key — generate and store ─────────────────────────
        logger.info("Generating NEW master key...")
        new_key = Fernet.generate_key()

        if _USE_DPAPI:
            encrypted_key = win32crypt.CryptProtectData(new_key, "CRAVE Master Vault Key", None, None, None, 0)
            with open(MASTER_KEY_PATH, "wb") as f:
                f.write(encrypted_key)
            try:
                os.system(f'attrib +h "{MASTER_KEY_PATH}"')
            except Exception:
                pass
            logger.info("Master key locked to current Windows user via DPAPI.")
        elif _USE_KEYRING:
            keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, new_key.decode("utf-8"))
            logger.info("Master key stored in OS keyring.")
        else:
            with open(raw_key_path, "wb") as f:
                f.write(new_key)
            os.chmod(raw_key_path, 0o600)  # Owner read/write only
            logger.warning("Master key saved as RAW FILE (chmod 600). Install keyring for better security.")
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
