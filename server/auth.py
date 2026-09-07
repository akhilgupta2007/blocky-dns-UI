import os
import datetime
import bcrypt
import jwt
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_connection

JWT_SECRET = os.getenv("JWT_SECRET", "super_secret_blockydns_jwt_key_homelab_secure_12345")
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
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=JWT_EXPIRATION_HOURS),
        "ua": get_ua_fingerprint(request) if request else None
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str, request: Request = None):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # Verify User-Agent fingerprint if present
        if request and payload.get("ua"):
            current_ua = get_ua_fingerprint(request)
            if payload["ua"] != current_ua:
                print(f"[AUTH] User-Agent mismatch detected! Session rejected.")
                return None
        return payload.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

def is_setup_completed() -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM users;")
    row = cursor.fetchone()
    conn.close()
    return (row["cnt"] if row else 0) > 0

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

    username = decode_access_token(token, request)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE username = ?;", (username,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return dict(user)
