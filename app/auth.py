"""Password hashing (scrypt), JWT cookies, and the current-user dependency."""
import hashlib
import hmac
import os
import time

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import settings as S
from .db import User, get_db


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def make_token(user_id: str) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + S.TOKEN_TTL_SECONDS},
                      S.SECRET_KEY, algorithm="HS256")


def user_from_request(request: Request, db: Session) -> User | None:
    token = request.cookies.get(S.COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(token, S.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return db.get(User, payload.get("sub"))


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in.")
    return user


# crude in-memory brute-force limiter: 8 failures / 5 minutes per (ip, email)
_fails: dict[str, list[float]] = {}


def check_login_allowed(key: str):
    cutoff = time.time() - 300
    hits = [t for t in _fails.get(key, []) if t > cutoff]
    _fails[key] = hits
    if len(hits) >= 8:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in a few minutes.")


def record_login_failure(key: str):
    _fails.setdefault(key, []).append(time.time())


def clear_login_failures(key: str):
    _fails.pop(key, None)
