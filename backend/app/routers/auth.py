"""Authentication endpoints — password login + WebAuthn / passkey flow.

Password login is `POST /api/auth/login`. The rest of the file is the
FIDO2 surface (begin/complete handshake for register + authenticate, plus
list / rename / delete). Each route persists or consumes a short-lived
challenge state in `db.webauthn_states` so we never trust client-stored
state.

See `app/services/passkey.py` for the `fido_server` singleton and the
credential-rebuild helper.
"""

import base64
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fido2 import cbor

from app.database import db
from app.deps import get_current_user
from app.schemas.common import Token, UserLogin
from app.schemas.webauthn import (
    WebAuthnAuthenticateBegin, WebAuthnAuthenticateComplete, WebAuthnRegisterComplete,
)
from app.services.auth import _DUMMY_PASSWORD_HASH, create_access_token, verify_password
from app.services.passkey import _b64url_to_bytes, _rebuild_attested_credentials, fido_server

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=Token)
async def login(user: UserLogin):
    db_user = await db.users.find_one({"email": user.email}, {"_id": 0})
    # Always run verify_password (against the user's hash if present, or a
    # constant dummy hash if not) so the unknown-email branch takes the same
    # time as the wrong-password branch. Without this, an attacker can
    # enumerate valid emails by timing the response (~80ms vs <5ms).
    stored_hash = db_user["password_hash"] if db_user else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(user.password, stored_hash)
    if not db_user or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(data={"sub": db_user["id"]})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {"id": current_user["id"], "email": current_user["email"], "name": current_user["name"]}


# ============== WEBAUTHN / PASSKEY AUTH ==============
# Passkey-based biometric login (FaceID / TouchID / Windows Hello / hardware
# keys). Stored as an array of credentials on the user doc; verified via
# fido2 library which checks challenge, RP ID, signature, replay counter.


@router.post("/auth/passkey/register/begin")
async def register_passkey_begin(current_user: dict = Depends(get_current_user)):
    """Generate options for registering a new passkey for the current user."""
    import secrets

    from fido2.webauthn import (
        AuthenticatorAttachment, PublicKeyCredentialDescriptor,
        PublicKeyCredentialType, PublicKeyCredentialUserEntity,
        UserVerificationRequirement,
    )

    user_entity = PublicKeyCredentialUserEntity(
        # Random per registration — forces some platforms (e.g. iOS) to mint
        # a fresh credential instead of reusing an existing one.
        id=secrets.token_bytes(16),
        name=current_user["email"],
        display_name=current_user.get("name", current_user["email"]),
    )
    exclude_credentials = [
        PublicKeyCredentialDescriptor(
            type=PublicKeyCredentialType.PUBLIC_KEY,
            id=base64.b64decode(pk["id"]),
        )
        for pk in current_user.get("passkeys", [])
    ] or None

    options, state = fido_server.register_begin(
        user=user_entity,
        credentials=exclude_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
        authenticator_attachment=AuthenticatorAttachment.PLATFORM,
    )

    await db.webauthn_states.update_one(
        {"user_id": current_user["id"], "type": "registration"},
        {"$set": {
            "state": base64.b64encode(cbor.encode(state)).decode(),
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        }},
        upsert=True,
    )

    pk = options["publicKey"]
    return {
        "publicKey": {
            "challenge": pk["challenge"],
            "rp": pk["rp"],
            "user": pk["user"],
            "pubKeyCredParams": [{"type": "public-key", "alg": p["alg"]} for p in pk.get("pubKeyCredParams", [])],
            "timeout": 60000,
            "excludeCredentials": [
                {"type": "public-key", "id": c["id"]}
                for c in (pk.get("excludeCredentials") or [])
            ],
            "authenticatorSelection": {
                k: (v.value if hasattr(v, "value") else v)
                for k, v in (pk.get("authenticatorSelection") or {}).items()
            },
            "attestation": "none",
        }
    }


@router.post("/auth/passkey/register/complete")
async def register_passkey_complete(data: WebAuthnRegisterComplete, current_user: dict = Depends(get_current_user)):
    """Verify the attestation produced by the browser and save the passkey."""
    state_doc = await db.webauthn_states.find_one({"user_id": current_user["id"], "type": "registration"})
    if not state_doc or state_doc["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Registration session expired or not found")

    state = cbor.decode(base64.b64decode(state_doc["state"]))

    try:
        from fido2.webauthn import (
            AttestationObject, AuthenticatorAttestationResponse,
            CollectedClientData, RegistrationResponse,
        )
        reg = data.registration_data
        resp = reg.get("response", {})
        registration_response = RegistrationResponse(
            raw_id=_b64url_to_bytes(reg["id"]),
            response=AuthenticatorAttestationResponse(
                client_data=CollectedClientData(_b64url_to_bytes(resp["clientDataJSON"])),
                attestation_object=AttestationObject(_b64url_to_bytes(resp["attestationObject"])),
            ),
        )
        auth_data = fido_server.register_complete(state, registration_response)

        credential_id_b64 = base64.b64encode(auth_data.credential_data.credential_id).decode()
        if any(pk["id"] == credential_id_b64 for pk in current_user.get("passkeys", [])):
            logger.warning(f"Duplicate passkey registration blocked for user {current_user['id']}")
            raise HTTPException(status_code=400, detail="This passkey is already registered to your account.")

        credential = {
            "id": credential_id_b64,
            "public_key": base64.b64encode(cbor.encode(auth_data.credential_data.public_key)).decode(),
            "sign_count": auth_data.counter,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "name": "Passkey " + datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        await db.users.update_one({"id": current_user["id"]}, {"$push": {"passkeys": credential}})
        await db.webauthn_states.delete_one({"_id": state_doc["_id"]})
        return {"message": "Passkey registered successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WebAuthn registration failed: {e}", exc_info=True)
        # Don't leak the raw library exception to the client.
        raise HTTPException(status_code=400, detail="Passkey registration failed")


@router.post("/auth/passkey/authenticate/begin")
async def authenticate_passkey_begin(data: WebAuthnAuthenticateBegin):
    """Generate an assertion challenge for the user. Public (no auth needed)."""
    user = await db.users.find_one({"email": data.email})
    if not user or not user.get("passkeys"):
        raise HTTPException(status_code=404, detail="No passkeys registered for this account")

    from fido2.webauthn import (
        PublicKeyCredentialDescriptor, PublicKeyCredentialType, UserVerificationRequirement,
    )
    allow_credentials = [
        PublicKeyCredentialDescriptor(
            type=PublicKeyCredentialType.PUBLIC_KEY,
            id=base64.b64decode(pk["id"]),
        )
        for pk in user["passkeys"]
    ]
    options, state = fido_server.authenticate_begin(
        credentials=allow_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    await db.webauthn_states.update_one(
        {"email": data.email, "type": "authentication"},
        {"$set": {
            "state": base64.b64encode(cbor.encode(state)).decode(),
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        }},
        upsert=True,
    )

    pk = options["publicKey"]
    return {
        "publicKey": {
            "challenge": pk["challenge"],
            "rpId": pk.get("rpId"),
            "allowCredentials": [
                {"type": "public-key", "id": c["id"]}
                for c in (pk.get("allowCredentials") or [])
            ],
            "userVerification": pk["userVerification"].value if hasattr(pk.get("userVerification"), "value") else pk.get("userVerification", "required"),
            "timeout": 60000,
        }
    }


@router.post("/auth/passkey/authenticate/complete")
async def authenticate_passkey_complete(data: WebAuthnAuthenticateComplete):
    """Verify the browser-signed assertion and issue a JWT."""
    user = await db.users.find_one({"email": data.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    state_doc = await db.webauthn_states.find_one({"email": data.email, "type": "authentication"})
    if not state_doc or state_doc["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Authentication session expired")
    state = cbor.decode(base64.b64decode(state_doc["state"]))

    credentials = _rebuild_attested_credentials(user.get("passkeys", []))
    if not credentials:
        raise HTTPException(status_code=400, detail="No valid credentials found for this user")

    try:
        from fido2.webauthn import (
            AuthenticationResponse, AuthenticatorAssertionResponse,
            AuthenticatorData, CollectedClientData,
        )
        cred = data.credential_data
        resp = cred.get("response", {})

        # Explicit DB-level check before signature verification: presented
        # credential id must be one of this user's registered passkeys.
        presented_id_bytes = _b64url_to_bytes(cred["id"])
        presented_id_b64 = base64.b64encode(presented_id_bytes).decode()
        if not any(pk["id"] == presented_id_b64 for pk in user.get("passkeys", [])):
            logger.warning(f"Unregistered passkey login attempt for {data.email}: {presented_id_b64[:20]}...")
            raise HTTPException(status_code=401, detail="This passkey is not registered to your account.")

        auth_data_bytes = _b64url_to_bytes(resp["authenticatorData"])
        authentication_response = AuthenticationResponse(
            raw_id=presented_id_bytes,
            response=AuthenticatorAssertionResponse(
                client_data=CollectedClientData(_b64url_to_bytes(resp["clientDataJSON"])),
                authenticator_data=AuthenticatorData(auth_data_bytes),
                signature=_b64url_to_bytes(resp["signature"]),
                user_handle=_b64url_to_bytes(resp["userHandle"]) if resp.get("userHandle") else None,
            ),
        )

        # fido2 verifies challenge, RP ID, UV flag, signature, and replay (sign count)
        matched = fido_server.authenticate_complete(state, credentials, authentication_response)

        matched_id_b64 = base64.b64encode(matched.credential_id).decode()
        new_sign_count = AuthenticatorData(auth_data_bytes).counter
        await db.users.update_one(
            {"id": user["id"], "passkeys.id": matched_id_b64},
            {"$set": {"passkeys.$.sign_count": new_sign_count}},
        )
        await db.webauthn_states.delete_one({"_id": state_doc["_id"]})
        logger.info(f"Passkey login successful for user {user['id']} (credential: {matched_id_b64[:20]}...)")
        access_token = create_access_token(data={"sub": user["id"]})
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WebAuthn authentication failed: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Passkey verification failed")


@router.get("/auth/passkeys")
async def list_passkeys(current_user: dict = Depends(get_current_user)):
    """List passkeys for the current user. Excludes the cryptographic public_key
    field from the response to keep it small; UI only needs id/name/created_at."""
    pks = current_user.get("passkeys", [])
    return [
        {k: pk[k] for k in pk if k != "public_key"}
        for pk in pks
    ]


@router.delete("/auth/passkeys/{credential_id:path}")
async def delete_passkey(credential_id: str, current_user: dict = Depends(get_current_user)):
    """Remove a registered passkey from the current user's account."""
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$pull": {"passkeys": {"id": credential_id}}},
    )
    return {"message": "Passkey removed successfully"}


@router.patch("/auth/passkeys/{credential_id:path}")
async def rename_passkey(
    credential_id: str,
    data: dict,
    current_user: dict = Depends(get_current_user),
):
    """Rename a passkey so the user can identify which device it lives on."""
    new_name = (data or {}).get("name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Name is required")
    await db.users.update_one(
        {"id": current_user["id"], "passkeys.id": credential_id},
        {"$set": {"passkeys.$.name": new_name}},
    )
    return {"message": "Passkey renamed successfully"}
