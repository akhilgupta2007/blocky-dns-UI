import json
import asyncio
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from database import get_connection
from auth import get_current_user
from retention import prune_old_logs

router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(get_current_user)])

@router.get("")
def get_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=10, le=250),
    search: str = Query("", max_length=100),
    client_ip: str = Query("", max_length=50),
    status: str = Query("ALL", max_length=20),
    from_ts: str = Query("", max_length=60),
    to_ts: str = Query("", max_length=60),
    include_ptr: bool = Query(False)
):
    offset = (page - 1) * limit
    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params = []

    # Hide noisy PTR and Special-Use Domain Name queries by default
    if not include_ptr:
        conditions.append("(COALESCE(l.question_name, l.question) NOT LIKE '%.in-addr.arpa%' AND COALESCE(l.question_name, l.question) NOT LIKE '%.ip6.arpa%' AND l.response_type != 'SPECIAL' AND COALESCE(l.reason, '') NOT LIKE '%Special%')")

    if search.strip():
        conditions.append("(COALESCE(l.question_name, l.question) LIKE ? OR l.client_ip LIKE ? OR d.friendly_name LIKE ?)")
        term = f"%{search.strip()}%"
        params.extend([term, term, term])

    if client_ip.strip():
        conditions.append("l.client_ip = ?")
        params.append(client_ip.strip())

    if status.upper() != "ALL":
        conditions.append("l.response_type = ?")
        params.append(status.upper())

    if from_ts.strip():
        conditions.append("datetime(l.request_ts) >= datetime(?)")
        params.append(from_ts.strip())

    if to_ts.strip():
        conditions.append("datetime(l.request_ts) <= datetime(?)")
        params.append(to_ts.strip())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""


    # Count total matching rows
    count_query = f"""
    SELECT COUNT(*) as total
    FROM log_entries l
    LEFT JOIN devices d ON l.client_ip = d.client_ip
    {where_clause};
    """
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()["total"]

    # Select paginated rows
    query = f"""
    SELECT 
        l.id,
        l.request_ts,
        l.client_ip,
        COALESCE(d.friendly_name, d.hostname, l.client_ip) as client_name,
        COALESCE(d.icon, 'device') as client_icon,
        COALESCE(l.question_name, l.question, '') as question,
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
    rows = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "page": page,
        "limit": limit,
        "total_records": total_count,
        "total_pages": (total_count + limit - 1) // limit if limit > 0 else 1,
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
                c.execute("SELECT MAX(id) as max_id FROM log_entries;")
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
                ptr_filter = "" if include_ptr else "AND COALESCE(l.question_name, l.question) NOT LIKE '%.in-addr.arpa%' AND COALESCE(l.question_name, l.question) NOT LIKE '%.ip6.arpa%' AND l.response_type != 'SPECIAL' AND COALESCE(l.reason, '') NOT LIKE '%Special%'"
                cursor.execute(f"""
                SELECT 
                    l.id,
                    l.request_ts,
                    l.client_ip,
                    COALESCE(d.friendly_name, d.hostname, l.client_ip) as client_name,
                    COALESCE(d.icon, 'device') as client_icon,
                    COALESCE(l.question_name, l.question, '') as question,
                    COALESCE(l.question_type, 'A') as question_type,
                    l.response_type,
                    l.duration_ms,
                    l.reason,
                    l.answer
                FROM log_entries l
                LEFT JOIN devices d ON l.client_ip = d.client_ip
                WHERE l.id > ? {ptr_filter}
                ORDER BY l.id ASC
                LIMIT 50;
                """, (current_id,))
                new_rows = [dict(r) for r in cursor.fetchall()]
                conn.close()

                if new_rows:
                    current_id = max(r["id"] for r in new_rows)
                    yield f"event: log\ndata: {json.dumps(new_rows)}\n\n"
            except Exception as err:
                yield f"event: error\ndata: {json.dumps({'error': str(err)})}\n\n"

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

