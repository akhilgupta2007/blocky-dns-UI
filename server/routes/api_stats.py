import time
from typing import Optional
from fastapi import APIRouter, Depends, Query
from database import get_connection, get_log_entries_columns
from auth import get_current_user
from blocky_client import check_blocky_status

router = APIRouter(prefix="/api/stats", tags=["stats"], dependencies=[Depends(get_current_user)])

_STATS_CACHE = {}
_STATS_TTL_SECONDS = 4.0  # 4-second TTL coalesces concurrent dashboard requests and multiple browser tabs

def _get_cached_stat(key: str):
    if key in _STATS_CACHE:
        val, ts = _STATS_CACHE[key]
        if time.time() - ts < _STATS_TTL_SECONDS:
            return val
    return None

def _set_cached_stat(key: str, val):
    _STATS_CACHE[key] = (val, time.time())

def _resolve_range_modifier(range_param: Optional[str] = None) -> tuple[str, str, int]:
    """
    Resolves range_param into:
      (sql_modifier, bucket_format, bucket_type: 0 for hour 'MM-DD HH:00' / 'HH:00', 1 for day 'YYYY-MM-DD')
    If range_param is None, 'retention', 'max', or 'all', it resolves to the configured log_retention_days in settings.
    Supported range formats: '24h', '1d', '3d', '7d', '14d', '30d', or integer days / 'retention'.
    Guards defensively against fuzzing, extreme values, and SQL injection strings.
    """
    days = None
    hours = None

    if range_param:
        rp = str(range_param).strip().lower()
        # Truncate any overly long fuzz inputs
        if len(rp) > 32:
            rp = rp[:32]
        if rp in ("retention", "max", "all"):
            pass
        elif rp.endswith("h"):
            try:
                val = int(rp[:-1])
                # Bound hours between 1 and 87600 (10 years)
                hours = max(1, min(val, 87600))
            except (ValueError, OverflowError):
                pass
        elif rp.endswith("d"):
            try:
                val = int(rp[:-1])
                # Bound days between 1 and 3650 (10 years)
                days = max(1, min(val, 3650))
            except (ValueError, OverflowError):
                pass
        else:
            try:
                val = int(rp)
                days = max(1, min(val, 3650))
            except (ValueError, OverflowError):
                pass

    if days is None and hours is None:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key = 'log_retention_days';")
            r = c.fetchone()
            days = int(r["value"]) if r and r["value"] and r["value"].isdigit() else 7
        except Exception:
            days = 7
        finally:
            conn.close()

    if hours is not None:
        hours = max(1, min(int(hours), 87600))
        sql_modifier = f"-{hours} hours"
        bucket_format = "%H:00" if hours <= 24 else "%m-%d %H:00"
        return sql_modifier, bucket_format, 0

    if days is None or days <= 0:
        days = 1
    days = min(int(days), 3650)
    if days == 1:
        return "-24 hours", "%H:00", 0
    elif days <= 3:
        return f"-{days} days", "%m-%d %H:00", 0
    else:
        # Multi-day bucket by date
        return f"-{days} days", "%Y-%m-%d", 1

@router.get("/summary")
async def get_summary(range: Optional[str] = Query(None, description="Time range (e.g. 24h, 3d, 7d, retention)")):
    cache_key = f"summary_{range or 'retention'}"
    cached = _get_cached_stat(cache_key)
    if cached is not None:
        blocky_stat = await check_blocky_status()
        res = dict(cached)
        res["blocky_online"] = blocky_stat.get("online", True)
        res["blocking_enabled"] = blocky_stat.get("blocking_enabled", True)
        return res

    sql_modifier, _, _ = _resolve_range_modifier(range)

    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Queries in specified range
        cursor.execute(f"""
        SELECT 
            COUNT(*) as total_queries,
            SUM(CASE WHEN response_type = 'BLOCKED' THEN 1 ELSE 0 END) as blocked_queries,
            COUNT(DISTINCT client_ip) as active_clients
        FROM log_entries
        WHERE request_ts >= datetime('now', '{sql_modifier}');
        """)
        row = cursor.fetchone()
        total_q = (row["total_queries"] if row else 0) or 0
        blocked_q = (row["blocked_queries"] if row else 0) or 0
        blocked_pct = round((blocked_q / total_q * 100), 1) if total_q > 0 else 0.0
        active_devices = (row["active_clients"] if row else 0) or 0

        # Total active rules from enabled blocklists
        cursor.execute("SELECT SUM(rule_count) as rules_total FROM blocklists WHERE enabled = 1;")
        rule_row = cursor.fetchone()
        active_rules = (rule_row["rules_total"] if rule_row else 0) or 0

        # Upstream latency average
        cursor.execute("SELECT AVG(last_latency_ms) as avg_lat FROM upstreams WHERE enabled = 1 AND last_latency_ms > 0;")
        lat_row = cursor.fetchone()
        avg_latency = round(lat_row["avg_lat"], 1) if lat_row and lat_row["avg_lat"] else 12.4

        # Query distribution by response type in specified range
        cursor.execute(f"""
        SELECT 
            response_type,
            COUNT(*) as count
        FROM log_entries
        WHERE request_ts >= datetime('now', '{sql_modifier}')
        GROUP BY response_type;
        """)
        dist_rows = cursor.fetchall()
        query_distribution = {r["response_type"]: r["count"] for r in dist_rows}
    finally:
        conn.close()

    # Blocky live status
    blocky_stat = await check_blocky_status()

    result = {
        "total_queries_24h": total_q,
        "blocked_queries_24h": blocked_q,
        "blocked_percent": blocked_pct,
        "active_devices_count": active_devices,
        "active_rules_count": active_rules,
        "upstream_latency_ms": avg_latency,
        "blocky_online": blocky_stat.get("online", True),
        "blocking_enabled": blocky_stat.get("blocking_enabled", True),
        "query_distribution": query_distribution,
        "range_modifier": sql_modifier
    }
    _set_cached_stat(cache_key, result)
    return result

@router.get("/timeline")
def get_timeline(range: Optional[str] = Query(None, description="Time range (e.g. 24h, 3d, 7d, retention)")):
    cache_key = f"timeline_{range or 'retention'}"
    cached = _get_cached_stat(cache_key)
    if cached is not None:
        return cached

    sql_modifier, bucket_format, _ = _resolve_range_modifier(range)

    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(f"""
        SELECT 
            strftime('{bucket_format}', request_ts) as hour_bucket,
            COUNT(*) as total,
            SUM(CASE WHEN response_type = 'BLOCKED' THEN 1 ELSE 0 END) as blocked
        FROM log_entries
        WHERE request_ts >= datetime('now', '{sql_modifier}')
        GROUP BY hour_bucket
        ORDER BY hour_bucket ASC;
        """)
        rows = cursor.fetchall()
    finally:
        conn.close()

    timeline_data = [
        {"hour": r["hour_bucket"], "total": r["total"], "blocked": r["blocked"]}
        for r in rows
    ]
    _set_cached_stat(cache_key, timeline_data)
    return timeline_data

@router.get("/top-domains")
def get_top_domains(
    range: Optional[str] = Query(None, description="Time range (e.g. 24h, 3d, 7d, retention)"),
    limit: int = Query(10, ge=1, le=100)
):
    cache_key = f"top_domains_{range or 'retention'}_{limit}"
    cached = _get_cached_stat(cache_key)
    if cached is not None:
        return cached

    cols = get_log_entries_columns()
    if not cols:
        return {"top_allowed": [], "top_blocked": []}

    q_col = "question_name" if "question_name" in cols else ("question" if "question" in cols else "''")
    if "question_name" in cols and "question" in cols:
        q_expr = "COALESCE(NULLIF(question_name, ''), NULLIF(question, ''), '')"
    else:
        q_expr = f"COALESCE({q_col}, '')"

    sql_modifier, _, _ = _resolve_range_modifier(range)

    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Top allowed
        cursor.execute(f"""
        SELECT {q_expr} as domain, COUNT(*) as count
        FROM log_entries
        WHERE response_type != 'BLOCKED' AND request_ts >= datetime('now', '{sql_modifier}')
        GROUP BY domain
        ORDER BY count DESC
        LIMIT {int(limit)};
        """)
        allowed = [dict(r) for r in cursor.fetchall() if r["domain"]]

        # Top blocked
        cursor.execute(f"""
        SELECT {q_expr} as domain, COUNT(*) as count
        FROM log_entries
        WHERE response_type = 'BLOCKED' AND request_ts >= datetime('now', '{sql_modifier}')
        GROUP BY domain
        ORDER BY count DESC
        LIMIT {int(limit)};
        """)
        blocked = [dict(r) for r in cursor.fetchall() if r["domain"]]
    finally:
        conn.close()

    result = {"top_allowed": allowed, "top_blocked": blocked}
    _set_cached_stat(cache_key, result)
    return result

@router.get("/top-devices")
def get_top_devices(range: Optional[str] = Query(None, description="Time range (e.g. 24h, 3d, 7d, retention)")):
    cache_key = f"top_devices_{range or 'retention'}"
    cached = _get_cached_stat(cache_key)
    if cached is not None:
        return cached

    sql_modifier, _, _ = _resolve_range_modifier(range)

    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(f"""
        SELECT 
            l.client_ip,
            COALESCE(d.friendly_name, d.hostname, l.client_ip) as name,
            COALESCE(d.hostname, '') as hostname,
            COALESCE(d.friendly_name, '') as friendly_name,
            COALESCE(d.icon, 'device') as icon,
            COUNT(*) as total_queries,
            SUM(CASE WHEN l.response_type = 'BLOCKED' THEN 1 ELSE 0 END) as blocked_queries
        FROM log_entries l
        LEFT JOIN devices d ON l.client_ip = d.client_ip
        WHERE l.request_ts >= datetime('now', '{sql_modifier}')
        GROUP BY l.client_ip
        ORDER BY total_queries DESC;
        """)
        rows = cursor.fetchall()
    finally:
        conn.close()

    devices = []
    for r in rows:
        tot = r["total_queries"]
        blk = r["blocked_queries"]
        pct = round((blk / tot * 100), 1) if tot > 0 else 0.0
        devices.append({
            "client_ip": r["client_ip"],
            "name": r["name"],
            "hostname": r["hostname"],
            "friendly_name": r["friendly_name"],
            "icon": r["icon"],
            "total_queries": tot,
            "blocked_queries": blk,
            "blocked_percent": pct
        })

    _set_cached_stat(cache_key, devices)
    return devices


