"""FastAPI dependencies used by routes.

`get_current_user` is the canonical "this request must be authenticated"
gate. Returning the user dict means handlers can write
`current_user["id"]` / `["email"]` directly.

`require_admin` is the "and allowed to do irreversible things" gate. It
guards the two endpoints that can destroy the whole dataset — factory
reset and backup restore.

Scope note: this app is deliberately single-tenant (see
routers/business.py — one business document). Business records carry no
owner field and queries are not tenant-scoped, so roles are NOT a
substitute for tenant isolation. If a second business is ever onboarded
onto one deployment, every record merges; that needs a `business_id` on
every document and a shared dependency injecting it into every query,
not a role check.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from app.config import SECRET_KEY, ALGORITHM
from app.database import db

# Single shared security scheme.
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if user is None:
        raise credentials_exception

    # ---- Revocation ----
    # Two levers, both checked here so every authenticated route gets them
    # rather than just the one that remembered to ask.
    #
    # 1. Per-token: /auth/logout adds this token's jti to a denylist, so
    #    signing out of one device leaves the others alone.
    jti = payload.get("jti")
    if jti and await db.revoked_tokens.find_one({"jti": jti}, {"_id": 1}):
        raise credentials_exception

    # 2. Per-user: /auth/logout-all increments the account's token version,
    #    which invalidates every token carrying an older one. This is the
    #    incident-response lever for a lost device, and it costs nothing
    #    extra because the user document is already loaded.
    #
    #    A version counter rather than an "issued before" timestamp on
    #    purpose: `iat` has one-second resolution, so a timestamp comparison
    #    either lets through tokens minted in the same second as the revoke
    #    or rejects the fresh login that immediately follows it. A counter
    #    has no such window. Tokens and users predating this both read as
    #    version 0, so existing sessions keep working.
    if payload.get("tv", 0) != user.get("token_version", 0):
        raise credentials_exception

    # Handlers that revoke need the presenting token's own claims.
    user["_token_claims"] = {"jti": jti, "iat": payload.get("iat"), "exp": payload.get("exp")}
    return user


# Roles that may perform irreversible, dataset-wide operations.
ADMIN_ROLES = {"admin", "owner"}


def is_admin(user: dict) -> bool:
    """Whether a user may perform destructive operations.

    A user with NO `role` field counts as an admin. Nothing in the app
    ever wrote a role — only the provisioning scripts did — so live
    databases are full of role-less users, and treating them as
    non-admin would lock owners out of their own backups on upgrade.
    An explicitly-set non-admin role is honoured, so the gate becomes
    real the moment staff accounts exist.
    """
    role = user.get("role")
    if role is None:
        return True
    return str(role).strip().lower() in ADMIN_ROLES


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Authenticated AND permitted to destroy data."""
    if not is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires an administrator account.",
        )
    return current_user
