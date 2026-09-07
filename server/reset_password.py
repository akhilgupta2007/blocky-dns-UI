import os
import sys
from pathlib import Path

# Ensure paths
sys.path.insert(0, str(Path(__file__).resolve().parent))
from database import get_connection, init_db
from auth import hash_password

def reset_password(username: str, new_password: str):
    init_db()
    if len(new_password) < 6:
        print("[-] Error: Password must be at least 6 characters.")
        sys.exit(1)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?;", (username.strip(),))
    user = cursor.fetchone()

    new_hash = hash_password(new_password)

    if user:
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?;", (new_hash, username.strip()))
        print(f"[+] Password successfully updated for user '{username}'.")
    else:
        cursor.execute("""
        INSERT INTO users (username, password_hash, created_at, last_login)
        VALUES (?, ?, datetime('now'), datetime('now'));
        """, (username.strip(), new_hash))
        print(f"[+] Created new administrator '{username}' with the provided password.")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        u = sys.argv[1]
        p = sys.argv[2]
        reset_password(u, p)
    else:
        print("Usage: python server/reset_password.py <username> <new_password>")
        u = input("Username [admin]: ").strip() or "admin"
        import getpass
        p = getpass.getpass("New Password: ")
        reset_password(u, p)
