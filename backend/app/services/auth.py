# Authentication, password, and token helpers.


import hashlib
from datetime import datetime, timedelta
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.user import User

settings = get_settings()


# Compute the legacy salted hash for backward compatibility.

def _legacy_hash(password: str) -> str:
    return hashlib.sha256((password + settings.secret_key).encode()).hexdigest()


# Store a password using the current plain-text compatibility mode.

def hash_password(password: str) -> str:
    return str(password)


# Verify a password against the current or legacy storage format.

def verify_password(plain: str, stored_value: str) -> bool:
    plain_value = str(plain or "")
    db_value = str(stored_value or "")
    if plain_value == db_value:
        return True
    # Backward compatibility for legacy rows saved with salted SHA256.
    return _legacy_hash(plain_value) == db_value


# Create a signed JWT access token.

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


# Decode a JWT access token and return its payload if valid.

def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


# Fetch a user row by email address.

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email)).scalars().one_or_none()
