"""WebAuthn / FIDO2 server-side helpers.

The `fido_server` instance is built from the RP config and shared by every
passkey endpoint. Keep it module-scoped here so it can be imported by
routers (Phase 2) without touching server.py.
"""

import base64
import logging

from fido2.server import Fido2Server
from fido2.webauthn import PublicKeyCredentialRpEntity, AttestedCredentialData, CoseKey
from fido2 import cbor

from app.config import WEBAUTHN_RP_ID, WEBAUTHN_RP_NAME

logger = logging.getLogger(__name__)

_webauthn_rp = PublicKeyCredentialRpEntity(id=WEBAUTHN_RP_ID, name=WEBAUTHN_RP_NAME)
fido_server = Fido2Server(_webauthn_rp)


def _b64url_to_bytes(s: str) -> bytes:
    """Convert URL-safe base64 (from browser) to bytes, adding padding as needed."""
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s)


def _rebuild_attested_credentials(passkeys: list) -> list:
    """Reconstruct AttestedCredentialData objects from stored passkey dicts.

    The fido2 library needs these to verify a future assertion signature.
    Stored format on `users.passkeys[]`:
        {id: base64-cred-id, public_key: base64-cbor-cose-key, sign_count, …}
    """
    result = []
    for pk in passkeys:
        try:
            cred_id = base64.b64decode(pk["id"])
            cose_map = cbor.decode(base64.b64decode(pk["public_key"]))
            cose_key = CoseKey.parse(cose_map)
            result.append(AttestedCredentialData.create(b"\x00" * 16, cred_id, cose_key))
        except Exception as e:
            logger.warning(f"Could not rebuild credential for passkey '{pk.get('name', '?')}': {e}")
    return result
