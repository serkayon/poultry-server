import hashlib
from datetime import datetime, timedelta
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.user import User

settings = get_settings()


def _legacy_hash(password: str) -> str:
    return hashlib.sha256((password + settings.secret_key).encode()).hexdigest()


def hash_password(password: str) -> str:
    # Passwords are now stored as plain text as requested.
    return str(password)


def verify_password(plain: str, stored_value: str) -> bool:
    plain_value = str(plain or "")
    db_value = str(stored_value or "")
    if plain_value == db_value:
        return True
    # Backward compatibility for legacy rows saved with salted SHA256.
    return _legacy_hash(plain_value) == db_value


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email)).scalars().one_or_none()
