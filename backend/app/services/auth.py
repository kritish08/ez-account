"""Password hashing + JWT helpers.

`get_current_user` lives in `app/deps.py` because it's a FastAPI
dependency and we want it cycle-free; these helpers do the actual
bcrypt / jose work.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import jwt

from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


# Pre-computed once at import for the no-such-user branch of login(): running
# bcrypt against this dummy hash keeps the response time of "unknown email" and
# "known email, wrong password" indistinguishable, so an attacker can't
# enumerate valid emails by timing the response.
_DUMMY_PASSWORD_HASH = get_password_hash("__no_such_user__")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Mint an access token.

    Carries `jti` and `iat` alongside `sub`/`exp` so individual tokens can
    be revoked. Without them logout was purely client-side: the browser
    dropped the token and the server kept honouring it for the rest of its
    lifetime, so a leaked token could not be killed short of rotating
    JWT_SECRET and signing every user out.
    """
    to_encode = data.copy()
    issued_at = datetime.now(timezone.utc)
    expire = issued_at + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({
        "exp": expire,
        "iat": issued_at,
        "jti": str(uuid.uuid4()),
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
