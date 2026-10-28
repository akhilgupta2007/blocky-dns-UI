import os
import datetime
import bcrypt
import jwt
import secrets
import uuid
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_connection

KNOWN_DEFAULT_SECRETS = {
    "change_me_to_a_random_secure_secret_string",
    "super_secret_blockydns_jwt_key_homelab_secure_12345",
    "super_secret_blockydns_jwt_key_change_me",
}

def _get_jwt_secret() -> str:
    env_secret = os.getenv("JWT_SECRET")
    if env_secret and len(env_secret.strip()) >= 32 and env_secret.strip() not in KNOWN_DEFAULT_SECRETS:
        return env_secret.strip()
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'jwt_secret';")
            row = cursor.fetchone()
            if row and row["value"] and len(row["value"].strip()) >= 32 and row["value"].strip() not in KNOWN_DEFAULT_SECRETS:
                return row["value"].strip()
            generated = secrets.token_hex(32)
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('jwt_secret', ?);", (generated,))
            conn.commit()
            return generated
        finally:
            conn.close()
    except Exception:
        return secrets.token_hex(32)

JWT_SECRET = _get_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 72

security = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

import hashlib

def get_ua_fingerprint(request: Request) -> str:
    ua = request.headers.get("user-agent", "unknown")
    return hashlib.sha256(ua.encode("utf-8")).hexdigest()[:16]

def create_access_token(username: str, request: Request = None) -> str:
    payload = {
        "sub": username,
        "jti": uuid.uuid4().hex,
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str, request: Request = None):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

def is_setup_completed() -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM users;")
        row = cursor.fetchone()
        return (row["cnt"] if row else 0) > 0
    finally:
        conn.close()

def revoke_token(token: str):
    if not token:
        return
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO revoked_tokens (token_hash, revoked_at) VALUES (?, datetime('now'));", (token_hash,))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass

def is_token_revoked(token: str) -> bool:
    if not token:
        return True
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT token_hash FROM revoked_tokens WHERE token_hash = ?;", (token_hash,))
            row = cursor.fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return False

async def get_current_user(request: Request, auth: HTTPAuthorizationCredentials = Security(security)):
    # 1. Try Authorization header
    token = None
    if auth and auth.credentials:
        token = auth.credentials
    # 2. Try cookie
    if not token:
        token = request.cookies.get("blockydns_token")

    if not token:
        raise HTTPException(status_code=401, detail="Authentication credentials required")

    if is_token_revoked(token):
        raise HTTPException(status_code=401, detail="Session has been revoked or logged out")

    username = decode_access_token(token, request)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM users WHERE username = ?;", (username,))
        user = cursor.fetchone()
    finally:
        conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return dict(user)
