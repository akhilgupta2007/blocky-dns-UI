import threading
import time
from database import get_connection

def prune_old_logs(days: int = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    if days is None:
        cursor.execute("SELECT value FROM settings WHERE key = 'log_retention_days';")
        row = cursor.fetchone()
        days = int(row["value"]) if row else 7

    cursor.execute("""
    DELETE FROM log_entries 
    WHERE request_ts < datetime('now', '-' || ? || ' days');
    """, (days,))
    deleted_count = cursor.rowcount

    conn.commit()
    conn.close()
    print(f"[Retention] Pruned {deleted_count} log entries older than {days} days")
    return deleted_count

def start_retention_scheduler():
    def background_loop():
        while True:
            try:
                prune_old_logs()
            except Exception as e:
                print(f"[Retention Error]: {e}")
            # Run every 6 hours
            time.sleep(6 * 3600)

    thread = threading.Thread(target=background_loop, daemon=True)
    thread.start()
