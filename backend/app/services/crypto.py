"""Envelope encryption for backup payloads (AES-256-GCM).

Mirror in the `backup/` sidecar (`backup.py::decrypt_envelope`) so the
external restore tool can read what the server wrote.
"""

import base64
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt_data(data: bytes, mek: str) -> dict:
    """Encrypt data using envelope encryption (AES-256-GCM).

    A fresh DEK (Data Encryption Key) is generated for every payload and
    then wrapped with the long-lived MEK (Master Encryption Key) from
    config. This means a single MEK can decrypt many backups, but no DEK
    can be reused if a backup is compromised.
    """
    dek = secrets.token_bytes(32)        # 256-bit DEK
    nonce = secrets.token_bytes(12)      # 96-bit nonce for AES-GCM
    aesgcm = AESGCM(dek)
    encrypted_data = aesgcm.encrypt(nonce, data, None)

    mek_bytes = bytes.fromhex(mek)
    mek_nonce = secrets.token_bytes(12)
    mek_aesgcm = AESGCM(mek_bytes)
    encrypted_dek = mek_aesgcm.encrypt(mek_nonce, dek, None)

    return {
        "encrypted_data": base64.b64encode(encrypted_data).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "encrypted_dek": base64.b64encode(encrypted_dek).decode(),
        "mek_nonce": base64.b64encode(mek_nonce).decode(),
    }


def decrypt_data(encrypted_package: dict, mek: str) -> bytes:
    """Inverse of encrypt_data."""
    encrypted_data = base64.b64decode(encrypted_package["encrypted_data"])
    nonce = base64.b64decode(encrypted_package["nonce"])
    encrypted_dek = base64.b64decode(encrypted_package["encrypted_dek"])
    mek_nonce = base64.b64decode(encrypted_package["mek_nonce"])

    mek_bytes = bytes.fromhex(mek)
    mek_aesgcm = AESGCM(mek_bytes)
    dek = mek_aesgcm.decrypt(mek_nonce, encrypted_dek, None)

    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(nonce, encrypted_data, None)
