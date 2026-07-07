"""
credentials.py
──────────────
Securely resolves supplier login credentials at RUNTIME.

Passwords are NEVER stored in this repository. Instead each supplier in
suppliers.json declares two env-var names:

    "login_email_env":   "FERGUSON_USER"
    "login_password_env": "FERGUSON_PASS"

At runtime we read the actual values from environment variables, which on
Render are supplied via the dashboard as "Secret" environment variables
(encrypted at rest). Nothing sensitive is ever committed to Git.

Optional extra layer: if you set a master key `SECRETS_KEY` and store an
encrypted secrets blob in `SECRETS_ENC` (Fernet/AES-128), this module will
decrypt it and merge those values in. This lets you keep ALL passwords in a
single encrypted string if you prefer.
"""

import os
import json
import logging

logger = logging.getLogger("partfinder.credentials")

# ── Optional encrypted-blob support (single-string vault) ──────────────────
_decrypted_vault: dict = {}


def _load_encrypted_vault() -> None:
    """If SECRETS_KEY + SECRETS_ENC are present, decrypt them into a dict.

    Create the encrypted blob locally like this:

        from cryptography.fernet import Fernet
        key = Fernet.generate_key()                 # -> SECRETS_KEY
        data = {"FERGUSON_USER": "danielv@a-mg.com",
                "FERGUSON_PASS": "•••••••••"}
        token = Fernet(key).encrypt(json.dumps(data).encode())  # -> SECRETS_ENC

    Then paste `key` into Render env var SECRETS_KEY and `token` into SECRETS_ENC.
    """
    global _decrypted_vault
    key = os.environ.get("SECRETS_KEY")
    enc = os.environ.get("SECRETS_ENC")
    if not key or not enc:
        return
    try:
        from cryptography.fernet import Fernet
        raw = Fernet(key.encode()).decrypt(enc.encode())
        _decrypted_vault = json.loads(raw.decode())
        logger.info("Loaded %d credentials from encrypted vault.", len(_decrypted_vault))
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to decrypt SECRETS_ENC: %s", e)


_load_encrypted_vault()


def _resolve(env_name: str) -> str:
    """Look up a value: plain env var first, then encrypted vault."""
    if not env_name:
        return ""
    val = os.environ.get(env_name)
    if val:
        return val
    return _decrypted_vault.get(env_name, "")


def get_credentials(supplier: dict) -> dict:
    """Return {'login_email': ..., 'login_password': ...} for a supplier.

    Empty strings mean 'no credentials configured' -> the scraper will skip
    login and simply build a deep-link instead.
    """
    email = _resolve(supplier.get("login_email_env", ""))
    password = _resolve(supplier.get("login_password_env", ""))
    return {"login_email": email, "login_password": password}


def has_credentials(supplier: dict) -> bool:
    creds = get_credentials(supplier)
    return bool(creds["login_email"] and creds["login_password"])
