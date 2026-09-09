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


# ---- Short-secret encryption (config values, not backup payloads) ----
#
# Credentials stored in db.settings — currently the AWS secret access key —
# sat there in plaintext. Every backup archive includes the `settings`
# collection, so each backup carried the credentials that created it, next
# to the users collection. Anyone who reached the database got working AWS
# keys and the bucket name.
#
# These use the MEK directly rather than the envelope scheme above: a short
# config value is rewritten as a whole on every change, so a per-payload DEK
# buys nothing. Values are tagged so an untagged (pre-existing, plaintext)
# value is recognisable and can be passed through unchanged — live databases
# are full of them and configured backups must keep working across the
# upgrade.
_SECRET_PREFIX = "enc.v1:"


def is_encrypted_secret(value: str) -> bool:
    """Whether `value` was written by encrypt_secret."""
    return isinstance(value, str) and value.startswith(_SECRET_PREFIX)


def encrypt_secret(plaintext: str, mek: str) -> str:
    """Encrypt a short config secret to a tagged, self-describing string."""
    if not plaintext:
        return plaintext
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(bytes.fromhex(mek))
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return _SECRET_PREFIX + base64.b64encode(nonce + ciphertext).decode()


def decrypt_secret(value: str, mek: str) -> str:
    """Inverse of encrypt_secret.

    An untagged value is returned unchanged — that is a secret written
    before encryption at rest existed, not a corrupt one.
    """
    if not value:
        return value
    if not is_encrypted_secret(value):
        return value
    raw = base64.b64decode(value[len(_SECRET_PREFIX):])
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(bytes.fromhex(mek))
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
