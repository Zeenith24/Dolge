"""Password hashing (scrypt), JWT cookies, and the current-user dependency."""
import datetime as dt
import hashlib
import hmac
import os
import secrets
import time

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import settings as S
from .db import EmailToken, User, get_db, now


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


def make_token(user: User) -> str:
    t = int(time.time())
    return jwt.encode({"sub": user.id, "sv": user.session_version or 0, "iat": t,
                       "exp": t + S.TOKEN_TTL_SECONDS}, S.SECRET_KEY, algorithm="HS256")


def user_from_request(request: Request, db: Session) -> User | None:
    token = request.cookies.get(S.COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(token, S.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    user = db.get(User, payload.get("sub"))
    # a password reset bumps session_version, which logs out every older cookie
    if not user or payload.get("sv", 0) != (user.session_version or 0):
        return None
    return user


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


# --------------------------------------------------------------------------- generic rate limit
_hits: dict[str, list[float]] = {}


def rate_limit(key: str, limit: int, window_seconds: int, message: str = "Too many requests. Please wait a bit."):
    """Allow `limit` calls per `window_seconds` for `key` (in-memory, per server process)."""
    cutoff = time.time() - window_seconds
    hits = [t for t in _hits.get(key, []) if t > cutoff]
    if len(hits) >= limit:
        _hits[key] = hits
        raise HTTPException(status_code=429, detail=message)
    hits.append(time.time())
    _hits[key] = hits
    if len(_hits) > 5000:                       # keep memory bounded
        for k in [k for k, v in _hits.items() if not v or v[-1] < cutoff][:2500]:
            _hits.pop(k, None)


# --------------------------------------------------------------------------- one-time email tokens
def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_email_token(db: Session, user: User, kind: str, ttl: dt.timedelta) -> str:
    """Invalidate older unused tokens of this kind, store a new hashed one, return the raw token."""
    for old in db.query(EmailToken).filter(EmailToken.user_id == user.id, EmailToken.kind == kind,
                                           EmailToken.used_at.is_(None)):
        old.used_at = now()
    raw = secrets.token_urlsafe(32)
    db.add(EmailToken(user_id=user.id, kind=kind, token_hash=_hash(raw), expires_at=now() + ttl))
    db.commit()
    return raw


def consume_email_token(db: Session, raw: str, kind: str) -> User:
    """Mark a token used and return its user, or raise 400 if it is unknown, used or expired."""
    tok = db.query(EmailToken).filter(EmailToken.token_hash == _hash(raw or ""), EmailToken.kind == kind).first()
    bad = HTTPException(status_code=400, detail="This link is invalid or has expired. Request a new one.")
    if not tok or tok.used_at is not None:
        raise bad
    expires = tok.expires_at if tok.expires_at.tzinfo else tok.expires_at.replace(tzinfo=dt.timezone.utc)
    if expires < now():
        raise bad
    user = db.get(User, tok.user_id)
    if not user:
        raise bad
    tok.used_at = now()
    db.commit()
    return user
