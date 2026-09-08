import logging
import threading
from database import get_connection

logger = logging.getLogger("blocky")

_cache_lock = threading.Lock()
_routing_cache: list[dict] = []
_initialized: bool = False

def reload_routing_cache() -> list[dict]:
    """Reloads active domain routing rules from SQLite into in-memory cache."""
    global _routing_cache, _initialized
    rules = []
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT domain_pattern, resolver, tag, enabled FROM domain_routing;")
        for r in cursor.fetchall():
            # Robust enabled check across integer, string, boolean, or NULL in SQLite
            is_enabled = r["enabled"] in (1, "1", True, "true", "True") or r["enabled"] is None
            if not is_enabled:
                continue
            pat = (r["domain_pattern"] or "").strip().lower()
            clean_pat = pat[2:] if pat.startswith("*.") else (pat[1:] if pat.startswith(".") else pat)
            clean_pat = clean_pat.rstrip(".")
            if clean_pat:
                rules.append({
                    "pattern": clean_pat,
                    "resolver": r["resolver"] or "",
                    "tag": r["tag"] or ""
                })
        conn.close()
        with _cache_lock:
            _routing_cache = rules
            _initialized = True
        logger.info(f"[RoutingCache] Loaded {len(rules)} routing rules into memory")
    except Exception as e:
        logger.warning(f"[RoutingCache] Failed to reload routing rules: {e}")
    return _routing_cache

def get_cached_routing_rules() -> list[dict]:
    """Returns in-memory cached domain routing rules. Auto-initializes if needed."""
    global _initialized
    if not _initialized:
        return reload_routing_cache()
    with _cache_lock:
        return list(_routing_cache)
