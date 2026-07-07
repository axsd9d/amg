#!/usr/bin/env python3
"""
make_secrets.py — build an ENCRYPTED credential vault (optional).

Run this LOCALLY only. It prints two values:
  * SECRETS_KEY  — the master key
  * SECRETS_ENC  — the encrypted blob of all your supplier passwords

Paste both into Render as SECRET environment variables. credentials.py will
decrypt them at runtime. This way you keep ALL passwords in one encrypted
string instead of many separate env vars — and nothing plaintext ever touches
Git or the Render UI logs.

Usage:
    pip install cryptography
    python make_secrets.py
Then edit the CREDS dict below with your real logins first.
"""

import json
from cryptography.fernet import Fernet

# 1) Put your REAL supplier logins here (this file is git-ignored; never commit).
CREDS = {
    "ALLPOINTS_USER": "customerservice@a-mg.com",
    "ALLPOINTS_PASS": "REPLACE_ME",
    "AMAZON_USER":    "customerservice@a-mg.com",
    "AMAZON_PASS":    "REPLACE_ME",
    "FERGUSON_USER":  "danielv@a-mg.com",
    "FERGUSON_PASS":  "REPLACE_ME",
    "GRAINGER_USER":  "customerservice@a-mg.com",
    "GRAINGER_PASS":  "REPLACE_ME",
    "JOHNSTONE_USER": "customerservice@a-mg.com",
    "JOHNSTONE_PASS": "REPLACE_ME",
    "PARTSTOWN_USER": "customerservice@a-mg.com",
    "PARTSTOWN_PASS": "REPLACE_ME",
}

if __name__ == "__main__":
    key = Fernet.generate_key()
    token = Fernet(key).encrypt(json.dumps(CREDS).encode())
    print("\n=== Copy these into Render as SECRET env vars ===\n")
    print("SECRETS_KEY =", key.decode())
    print()
    print("SECRETS_ENC =", token.decode())
    print("\n(Do NOT commit this output or this file with real passwords.)\n")
