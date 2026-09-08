from fastapi import APIRouter, Depends
from database import get_connection
from auth import get_current_user
from blocky_client import check_blocky_status

router = APIRouter(prefix="/api/stats", tags=["stats"], dependencies=[Depends(get_current_user)])

@router.get("/summary")
async def get_summary():
    conn = get_connection()
    cursor = conn.cursor()

    # Queries in last 24 hours
    cursor.execute("""
    SELECT 
        COUNT(*) as total_queries,
        SUM(CASE WHEN response_type = 'BLOCKED' THEN 1 ELSE 0 END) as blocked_queries,
        COUNT(DISTINCT client_ip) as active_clients
    FROM log_entries
    WHERE request_ts >= datetime('now', '-24 hours');
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

    # Query distribution by response type (RESOLVED, BLOCKED, CACHED, etc.) in last 24h
    cursor.execute("""
    SELECT 
        response_type,
        COUNT(*) as count
    FROM log_entries
    WHERE request_ts >= datetime('now', '-24 hours')
    GROUP BY response_type;
    """)
    dist_rows = cursor.fetchall()
    query_distribution = {r["response_type"]: r["count"] for r in dist_rows}

    conn.close()

    # Blocky live status
    blocky_stat = await check_blocky_status()

    return {
        "total_queries_24h": total_q,
        "blocked_queries_24h": blocked_q,
        "blocked_percent": blocked_pct,
        "active_devices_count": active_devices,
        "active_rules_count": active_rules,
        "upstream_latency_ms": avg_latency,
        "blocky_online": blocky_stat.get("online", True),
        "blocking_enabled": blocky_stat.get("blocking_enabled", True),
        "query_distribution": query_distribution
    }

@router.get("/timeline")
def get_timeline():
    """Generates 24 hourly buckets of total vs blocked queries."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        strftime('%H:00', request_ts) as hour_bucket,
        COUNT(*) as total,
        SUM(CASE WHEN response_type = 'BLOCKED' THEN 1 ELSE 0 END) as blocked
    FROM log_entries
    WHERE request_ts >= datetime('now', '-24 hours')
    GROUP BY hour_bucket
    ORDER BY hour_bucket ASC;
    """)
    rows = cursor.fetchall()
    conn.close()

    timeline_data = [
        {"hour": r["hour_bucket"], "total": r["total"], "blocked": r["blocked"]}
        for r in rows
    ]
    return timeline_data

@router.get("/top-domains")
def get_top_domains():
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(log_entries);")
        cols = {c["name"] for c in cursor.fetchall()}
    except Exception:
        cols = set()

    if not cols:
        conn.close()
        return {"top_allowed": [], "top_blocked": []}

    q_col = "question_name" if "question_name" in cols else ("question" if "question" in cols else "''")
    if "question_name" in cols and "question" in cols:
        q_expr = "COALESCE(NULLIF(question_name, ''), NULLIF(question, ''), '')"
    else:
        q_expr = f"COALESCE({q_col}, '')"

    # Top 10 allowed
    cursor.execute(f"""
    SELECT {q_expr} as domain, COUNT(*) as count
    FROM log_entries
    WHERE response_type != 'BLOCKED' AND request_ts >= datetime('now', '-24 hours')
    GROUP BY domain
    ORDER BY count DESC
    LIMIT 10;
    """)
    allowed = [dict(r) for r in cursor.fetchall() if r["domain"]]

    # Top 10 blocked
    cursor.execute(f"""
    SELECT {q_expr} as domain, COUNT(*) as count
    FROM log_entries
    WHERE response_type = 'BLOCKED' AND request_ts >= datetime('now', '-24 hours')
    GROUP BY domain
    ORDER BY count DESC
    LIMIT 10;
    """)
    blocked = [dict(r) for r in cursor.fetchall() if r["domain"]]

    conn.close()
    return {"top_allowed": allowed, "top_blocked": blocked}

@router.get("/top-devices")
def get_top_devices():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        l.client_ip,
        COALESCE(d.friendly_name, d.hostname, l.client_ip) as name,
        COALESCE(d.icon, 'device') as icon,
        COUNT(*) as total_queries,
        SUM(CASE WHEN l.response_type = 'BLOCKED' THEN 1 ELSE 0 END) as blocked_queries
    FROM log_entries l
    LEFT JOIN devices d ON l.client_ip = d.client_ip
    WHERE l.request_ts >= datetime('now', '-24 hours')
    GROUP BY l.client_ip
    ORDER BY total_queries DESC
    LIMIT 8;
    """)
    rows = cursor.fetchall()
    conn.close()

    devices = []
    for r in rows:
        tot = r["total_queries"]
        blk = r["blocked_queries"]
        pct = round((blk / tot * 100), 1) if tot > 0 else 0.0
        devices.append({
            "client_ip": r["client_ip"],
            "name": r["name"],
            "icon": r["icon"],
            "total_queries": tot,
            "blocked_queries": blk,
            "blocked_percent": pct
        })
    return devices
