import json
import asyncio
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from database import get_connection
from auth import get_current_user
from retention import prune_old_logs
from routing_cache import get_cached_routing_rules

router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(get_current_user)])

def enrich_log_rows(rows: list, cursor=None) -> list:
    """Enriches log rows using in-memory routing cache. Zero SQLite queries!"""
    has_conditional = any(
        (r.get("response_type") or "").strip().upper() == "CONDITIONAL" for r in rows
    )
    if not has_conditional:
        return rows

    routing_rules = get_cached_routing_rules()
    if not routing_rules:
        return rows

    for r in rows:
        if (r.get("response_type") or "").strip().upper() == "CONDITIONAL":
            q = (r.get("question") or "").strip().lower().rstrip(".")
            raw_reason = (r.get("reason") or "").strip()
            if raw_reason == "CONDITIONAL" or "(" not in raw_reason:
                matched_rule = None
                for rule in routing_rules:
                    pat = rule["pattern"]
                    if q == pat or q.endswith("." + pat):
                        matched_rule = rule
                        break
                if matched_rule:
                    tag_part = f" [{matched_rule['tag']}]" if matched_rule["tag"] else ""
                    r["reason"] = f"CONDITIONAL ({matched_rule['resolver']}{tag_part})"
    return rows

@router.get("")
def get_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    search: str = Query(None),
    client_ip: str = Query(None),
    response_type: str = Query(None),
    status: str = Query(None),
    include_ptr: bool = Query(False),
    from_ts: str = Query(None),
    to_ts: str = Query(None)
):
    offset = (page - 1) * limit
    conn = get_connection()
    cursor = conn.cursor()

    # Detect available columns in log_entries
    try:
        cursor.execute("PRAGMA table_info(log_entries);")
        columns = {row["name"] for row in cursor.fetchall()}
    except Exception:
        columns = set()

    if not columns:
        conn.close()
        return {
            "page": page,
            "limit": limit,
            "total_records": 0,
            "total_pages": 1,
            "records": []
        }

    # Primary key fallback: use 'id' if exists, else SQLite built-in 'rowid'
    id_expr = "l.id" if "id" in columns else "l.rowid"

    # Domain question column: Blocky standard is 'question' or 'question_name'
    q_col = "l.question_name" if "question_name" in columns else ("l.question" if "question" in columns else "''")
    q_expr = "COALESCE(NULLIF(l.question_name, ''), NULLIF(l.question, ''), '')" if ("question_name" in columns and "question" in columns) else f"COALESCE({q_col}, '')"

    # Build dynamic conditions & params
    conditions = []
    params = []

    # Filter out internal PTR & SUDN queries unless explicitly requested
    if not include_ptr:
        conditions.append(f"({q_expr} NOT LIKE '%.in-addr.arpa%' AND {q_expr} NOT LIKE '%.ip6.arpa%' AND l.response_type != 'SPECIAL' AND COALESCE(l.reason, '') NOT LIKE '%Special%')")

    if search:
        s = f"%{search.strip()}%"
        conditions.append(f"({q_expr} LIKE ? OR l.client_ip LIKE ? OR d.friendly_name LIKE ? OR d.hostname LIKE ? OR l.answer LIKE ?)")
        params.extend([s, s, s, s, s])

    if client_ip:
        conditions.append("l.client_ip = ?")
        params.append(client_ip.strip())

    # Support filtering by status or response_type (e.g. BLOCKED, RESOLVED, CACHED, CONDITIONAL)
    stat = (status or response_type or "").strip().upper()
    if stat and stat != "ALL":
        if stat == "BLOCKED":
            conditions.append("(l.response_type = 'BLOCKED' OR l.response_type = 'REBIND')")
        else:
            conditions.append("l.response_type = ?")
            params.append(stat)

    if from_ts:
        clean_from = from_ts.replace("T", " ").replace("Z", "").split(".")[0]
        conditions.append("l.request_ts >= ?")
        params.append(clean_from)

    if to_ts:
        clean_to = to_ts.replace("T", " ").replace("Z", "").split(".")[0]
        conditions.append("l.request_ts <= ?")
        params.append(clean_to)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Count total matching rows
    count_query = f"""
    SELECT COUNT(*) as total
    FROM log_entries l
    LEFT JOIN devices d ON l.client_ip = d.client_ip
    {where_clause};
    """
    cursor.execute(count_query, params)
    row = cursor.fetchone()
    total_count = row["total"] if row else 0

    # Select paginated rows
    query = f"""
    SELECT 
        {id_expr} as id,
        l.request_ts,
        l.client_ip,
        COALESCE(d.friendly_name, d.hostname, l.client_ip) as client_name,
        COALESCE(d.icon, 'device') as client_icon,
        {q_expr} as question,
        COALESCE(l.question_type, 'A') as question_type,
        l.response_type,
        l.duration_ms,
        l.reason,
        l.answer
    FROM log_entries l
    LEFT JOIN devices d ON l.client_ip = d.client_ip
    {where_clause}
    ORDER BY l.request_ts DESC
    LIMIT ? OFFSET ?;
    """
    params.extend([limit, offset])
    cursor.execute(query, params)
    raw_rows = [dict(r) for r in cursor.fetchall()]
    rows = enrich_log_rows(raw_rows, cursor)

    conn.close()

    return {
        "page": page,
        "limit": limit,
        "total_records": total_count,
        "total_pages": (total_count + limit - 1) // limit if limit > 0 and total_count > 0 else 1,
        "records": rows
    }

@router.post("/prune")
def prune_logs_now():
    pruned = prune_old_logs()
    return {"success": True, "pruned_count": pruned}

@router.get("/stream")
async def stream_query_logs(request: Request, last_id: int = Query(0, ge=0), include_ptr: bool = Query(False)):
    """Server-Sent Events (SSE) live streaming endpoint for real-time DNS queries."""
    async def event_generator():
        current_id = last_id
        if current_id == 0:
            try:
                conn = get_connection()
                c = conn.cursor()
                c.execute("PRAGMA table_info(log_entries);")
                c_cols = {r["name"] for r in c.fetchall()}
                id_col = "id" if "id" in c_cols else "rowid"
                c.execute(f"SELECT MAX({id_col}) as max_id FROM log_entries;")
                row = c.fetchone()
                current_id = row["max_id"] or 0
                conn.close()
            except Exception:
                current_id = 0

        # Send initial connected event
        yield f"event: ping\ndata: {json.dumps({'status': 'connected', 'tracking_id': current_id})}\n\n"

        while True:
            if await request.is_disconnected():
                break

            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(log_entries);")
                stream_cols = {r["name"] for r in cursor.fetchall()}
                s_id = "l.id" if "id" in stream_cols else "l.rowid"
                s_q_col = "l.question_name" if "question_name" in stream_cols else ("l.question" if "question" in stream_cols else "''")
                s_q_expr = "COALESCE(NULLIF(l.question_name, ''), NULLIF(l.question, ''), '')" if ("question_name" in stream_cols and "question" in stream_cols) else f"COALESCE({s_q_col}, '')"

                ptr_filter = "" if include_ptr else f"AND {s_q_expr} NOT LIKE '%.in-addr.arpa%' AND {s_q_expr} NOT LIKE '%.ip6.arpa%' AND l.response_type != 'SPECIAL' AND COALESCE(l.reason, '') NOT LIKE '%Special%'"
                cursor.execute(f"""
                SELECT 
                    {s_id} as id,
                    l.request_ts,
                    l.client_ip,
                    COALESCE(d.friendly_name, d.hostname, l.client_ip) as client_name,
                    COALESCE(d.icon, 'device') as client_icon,
                    {s_q_expr} as question,
                    COALESCE(l.question_type, 'A') as question_type,
                    l.response_type,
                    l.duration_ms,
                    l.reason,
                    l.answer
                FROM log_entries l
                LEFT JOIN devices d ON l.client_ip = d.client_ip
                WHERE {s_id} > ? {ptr_filter}
                ORDER BY {s_id} ASC
                LIMIT 50;
                """, (current_id,))
                raw_new_rows = [dict(r) for r in cursor.fetchall()]
                new_rows = enrich_log_rows(raw_new_rows, cursor)
                conn.close()

                if new_rows:
                    current_id = max(r["id"] for r in new_rows)
                    for r in new_rows:
                        yield f"data: {json.dumps(r)}\n\n"
            except Exception as err:
                pass

            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

