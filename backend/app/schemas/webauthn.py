"""WebAuthn / Passkey schemas."""

from pydantic import BaseModel


class WebAuthnRegisterComplete(BaseModel):
    registration_data: dict


class WebAuthnAuthenticateBegin(BaseModel):
    email: str


class WebAuthnAuthenticateComplete(BaseModel):
    email: str
    credential_data: dict
