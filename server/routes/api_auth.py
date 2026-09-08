from fastapi import APIRouter, HTTPException, Response, Request, Depends
from pydantic import BaseModel
from database import get_connection
from auth import (
    hash_password, verify_password, create_access_token,
    is_setup_completed, get_current_user
)
from blocky_client import sync_config_from_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

class SetupRequest(BaseModel):
    username: str
    password: str
    integration_mode: str = "all-in-one"
    blocky_api_url: str = "http://localhost:4000"

class LoginRequest(BaseModel):
    username: str
    password: str

@router.get("/status")
def auth_status(request: Request):
    setup_done = is_setup_completed()
    user = None
    try:
        token = request.cookies.get("blockydns_token")
        if token:
            from auth import decode_access_token
            username = decode_access_token(token)
            if username:
                conn = get_connection()
                c = conn.cursor()
                c.execute("SELECT id FROM users WHERE username = ?;", (username,))
                if c.fetchone():
                    user = username
                conn.close()
    except Exception:
        pass

    return {
        "setup_completed": setup_done,
        "authenticated": (user is not None) and setup_done,
        "user": user
    }

@router.post("/setup")
def initial_setup(req: SetupRequest, request: Request, response: Response):
    if is_setup_completed():
        raise HTTPException(status_code=400, detail="Setup has already been completed")

    if not req.username or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    conn = get_connection()
    cursor = conn.cursor()
    pw_hash = hash_password(req.password)

    cursor.execute("""
    INSERT INTO users (username, password_hash, created_at, last_login)
    VALUES (?, ?, datetime('now'), datetime('now'));
    """, (req.username.strip(), pw_hash))

    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('integration_mode', ?);", (req.integration_mode,))
    if req.integration_mode == "existing" and req.blocky_api_url:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blocky_api_url', ?);", (req.blocky_api_url.strip(),))

    conn.commit()
    conn.close()

    # Generate initial Blocky config
    try:
        sync_config_from_db()
    except Exception as e:
        print(f"[Setup] Warning syncing initial config: {e}")

    token = create_access_token(req.username.strip(), request)
    response.set_cookie(
        key="blockydns_token",
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=72 * 3600
    )
    return {"success": True, "token": token, "user": req.username.strip()}

@router.post("/login")
def login(req: LoginRequest, request: Request, response: Response):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash FROM users WHERE username = ?;", (req.username.strip(),))
    user = cursor.fetchone()

    if not user or not verify_password(req.password, user["password_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    cursor.execute("UPDATE users SET last_login = datetime('now') WHERE id = ?;", (user["id"],))
    conn.commit()
    conn.close()

    token = create_access_token(user["username"], request)
    response.set_cookie(
        key="blockydns_token",
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=72 * 3600
    )
    return {"success": True, "token": token, "user": user["username"]}

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="blockydns_token", path="/", httponly=True, samesite="lax")
    return {"success": True}

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

@router.post("/change-password")
def change_password(req: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = ?;", (current_user["username"],))
    user = cursor.fetchone()

    if not user or not verify_password(req.current_password, user["password_hash"]):
        conn.close()
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    new_hash = hash_password(req.new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?;", (new_hash, current_user["username"]))
    conn.commit()
    conn.close()

    return {"success": True, "message": "Password updated successfully"}

