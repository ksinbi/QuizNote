"""인증(JWT · 비밀번호 해시)과 Notion 토큰 암호화."""
import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db import get_db
from backend.models import User

_bearer = HTTPBearer(auto_error=False)


# ---------- 비밀번호 ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


# ---------- JWT ----------
def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _unauthorized(msg: str = "로그인이 필요합니다.") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None:
        raise _unauthorized()
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as e:
        raise _unauthorized("로그인이 만료되었습니다. 다시 로그인해주세요.") from e
    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized("사용자를 찾을 수 없습니다.")
    return user


# ---------- Notion 토큰 암호화 ----------
def _fernet() -> Fernet:
    key = settings.encryption_key
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret_key.encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as e:
        raise ValueError("저장된 토큰을 복호화할 수 없습니다. 암호화 키가 변경되었는지 확인하세요.") from e
