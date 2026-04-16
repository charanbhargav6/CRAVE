"""
CRAVE Phase 12 — Encrypted Contact Vault
Save to: D:\\CRAVE\\src\\security\\contact_vault.py

AES-Fernet encryption for the contacts database.
Even if someone opens the file in File Manager, they see ciphertext only.
"""

import os
import json
import logging
from pathlib import Path
from cryptography.fernet import Fernet

logger = logging.getLogger("crave.security.contact_vault")

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
VAULT_PATH = os.path.join(CRAVE_ROOT, "data", "contacts.enc")
KEY_PATH = os.path.join(CRAVE_ROOT, "config", ".contacts_key")


def _get_or_create_key() -> bytes:
    """Load or generate the Fernet encryption key."""
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
        with open(KEY_PATH, "wb") as f:
            f.write(key)
        # Hide the key file from casual browsing
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(KEY_PATH, 0x02)  # FILE_ATTRIBUTE_HIDDEN
        except:
            pass
        logger.info("Generated new contacts encryption key.")
        return key


def _get_fernet() -> Fernet:
    return Fernet(_get_or_create_key())


class ContactVault:
    """AES-encrypted contact storage. File is unreadable in File Manager."""

    def __init__(self):
        self.fernet = _get_fernet()
        self._contacts = self._load()

    def _load(self) -> list[dict]:
        """Decrypt and load contacts from disk."""
        if not os.path.exists(VAULT_PATH):
            return []
        try:
            with open(VAULT_PATH, "rb") as f:
                encrypted = f.read()
            decrypted = self.fernet.decrypt(encrypted)
            data = json.loads(decrypted.decode("utf-8"))
            return data.get("contacts", [])
        except Exception as e:
            logger.error(f"Failed to decrypt contacts: {e}")
            return []

    def _save(self):
        """Encrypt and persist contacts to disk."""
        os.makedirs(os.path.dirname(VAULT_PATH), exist_ok=True)
        data = json.dumps({"contacts": self._contacts}, indent=2).encode("utf-8")
        encrypted = self.fernet.encrypt(data)
        with open(VAULT_PATH, "wb") as f:
            f.write(encrypted)
        # Mark as hidden + system file on Windows
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(VAULT_PATH, 0x02 | 0x04)
        except:
            pass

    def add_contact(self, name: str, phone: str, platform: str = "whatsapp") -> str:
        """Add a new contact to the encrypted vault."""
        # Check for duplicates
        for c in self._contacts:
            if c["name"].lower() == name.lower():
                c["phone"] = phone
                c["platform"] = platform
                self._save()
                return f"Updated contact: {name}"

        self._contacts.append({
            "name": name,
            "phone": phone,
            "platform": platform,
        })
        self._save()
        return f"Contact added: {name} ({phone})"

    def remove_contact(self, name: str) -> str:
        """Remove a contact by name."""
        before = len(self._contacts)
        self._contacts = [c for c in self._contacts if c["name"].lower() != name.lower()]
        if len(self._contacts) < before:
            self._save()
            return f"Removed contact: {name}"
        return f"Contact not found: {name}"

    def resolve(self, name: str) -> dict | None:
        """Fuzzy match a contact name. Returns the best match or None."""
        name_lower = name.lower().strip()
        
        # Exact match first
        for c in self._contacts:
            if c["name"].lower() == name_lower:
                return c

        # Partial/fuzzy match
        for c in self._contacts:
            if name_lower in c["name"].lower() or c["name"].lower() in name_lower:
                return c

        return None

    def list_contacts(self) -> list[dict]:
        """Return all contacts (decrypted in memory only)."""
        return self._contacts.copy()

    def count(self) -> int:
        return len(self._contacts)
