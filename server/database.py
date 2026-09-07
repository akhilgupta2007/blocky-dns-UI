import os
import sqlite3
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
try:
    os.chmod(str(DATA_DIR), 0o777)
except Exception:
    pass
DB_PATH = DATA_DIR / "blockydns.db"

def get_connection():
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=20.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode and performance pragmas for low-resource hardware like Pi 2
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = 2000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
    except sqlite3.DatabaseError as e:
        if "malformed" in str(e).lower():
            print(f"[DB ALERT] Malformed SQLite database detected ({e}). Automatically recovering clean database...")
            import time
            ts = int(time.time())
            for ext in ["", "-wal", "-shm"]:
                p = Path(str(DB_PATH) + ext)
                if p.exists():
                    try:
                        p.rename(DATA_DIR / f"blockydns_corrupt_{ts}.db{ext}")
                    except Exception:
                        try:
                            p.unlink()
                        except Exception:
                            pass
            conn = sqlite3.connect(str(DB_PATH), timeout=20.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA cache_size = 2000;")
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn
        raise

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Users table (Admin auth)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_login TEXT
    );
    """)

    # 2. Devices table (Reverse PTR + friendly names)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS devices (
        client_ip TEXT PRIMARY KEY,
        hostname TEXT,
        friendly_name TEXT,
        icon TEXT DEFAULT 'device',
        group_name TEXT DEFAULT 'default',
        first_seen TEXT,
        last_seen TEXT,
        total_queries INTEGER DEFAULT 0,
        blocked_queries INTEGER DEFAULT 0
    );
    """)

    # 3. Blocklists table (Adlists / Subscriptions)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS blocklists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        url TEXT UNIQUE NOT NULL,
        category TEXT DEFAULT 'Adware & Tracking',
        enabled INTEGER DEFAULT 1,
        rule_count INTEGER DEFAULT 0,
        last_updated TEXT
    );
    """)

    # 4. Custom Rules table (Whitelist / Blacklist)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS custom_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_type TEXT NOT NULL, -- 'whitelist' or 'blacklist'
        domain TEXT NOT NULL,
        is_wildcard INTEGER DEFAULT 0,
        is_regex INTEGER DEFAULT 0,
        enabled INTEGER DEFAULT 1,
        comment TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # 5. Local DNS table (LAN overrides & wildcards)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS local_dns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT UNIQUE NOT NULL,
        ip_address TEXT NOT NULL,
        record_type TEXT DEFAULT 'A',
        is_wildcard INTEGER DEFAULT 0,
        enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """)

    # 6. Domain Routing table (Geo-Bypass & Conditional DNS)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS domain_routing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain_pattern TEXT UNIQUE NOT NULL,
        resolver TEXT NOT NULL,
        tag TEXT DEFAULT 'Geo-Bypass',
        enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """)

    # 7. Upstreams table (DoH / DoT / Custom)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS upstreams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        endpoint TEXT UNIQUE NOT NULL,
        protocol TEXT NOT NULL, -- 'doh', 'dot', 'udp'
        enabled INTEGER DEFAULT 1,
        is_custom INTEGER DEFAULT 0,
        last_latency_ms REAL DEFAULT 0.0
    );
    """)

    # 8. Query Log entries (Full Blocky GORM schema compatibility)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS log_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_ts TIMESTAMP NOT NULL,
        client_ip TEXT,
        client_name TEXT,
        duration_ms INTEGER DEFAULT 0,
        reason TEXT,
        response_type TEXT,
        question_name TEXT,
        question_type TEXT,
        answer TEXT,
        response_code TEXT,
        effective_tldp TEXT,
        hostname TEXT,
        question TEXT
    );
    """)

    # Check and migrate existing log_entries if created under old schema
    try:
        cursor.execute("PRAGMA table_info(log_entries);")
        existing_cols = {c["name"]: dict(c) for c in cursor.fetchall()}
        
        for col_name, col_type in [
            ("question_name", "TEXT"),
            ("question_type", "TEXT"),
            ("response_code", "TEXT"),
            ("effective_tldp", "TEXT"),
            ("hostname", "TEXT"),
            ("question", "TEXT")
        ]:
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE log_entries ADD COLUMN {col_name} {col_type} DEFAULT '';")
                except Exception:
                    pass
    except Exception as err:
        print(f"[DB] Migration note: {err}")

    # Indexes for fast search
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_ts ON log_entries(request_ts);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_ip ON log_entries(client_ip);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_type ON log_entries(response_type);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_qname ON log_entries(question_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_question ON log_entries(question);")

    # 9. Key-Value Settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # 10. Blocked Services table (1-Click App/Platform blocking catalog)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS blocked_services (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        icon TEXT NOT NULL,
        domains_json TEXT NOT NULL,
        enabled INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL
    );
    """)

    conn.commit()
    conn.close()


    # Ensure files and directories are writable across containers (e.g. Blocky unprivileged UID 100)
    try:
        os.chmod(str(DB_PATH), 0o666)
        for ext in ["-wal", "-shm"]:
            p = Path(str(DB_PATH) + ext)
            if p.exists():
                os.chmod(str(p), 0o666)
        os.chmod(str(DATA_DIR), 0o777)
    except Exception:
        pass

    print(f"[DB] SQLite database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_db()
