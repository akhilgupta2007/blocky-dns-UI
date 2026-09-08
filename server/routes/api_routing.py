from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import get_connection
from auth import get_current_user
from blocky_client import sync_config_from_db, schedule_blocky_restart
from resolver_utils import normalize_resolver
from routing_cache import reload_routing_cache

router = APIRouter(prefix="/api/routing", tags=["routing"], dependencies=[Depends(get_current_user)])

class AddRoutingRequest(BaseModel):
    domain_pattern: str
    resolver: str
    tag: str = "Geo-Bypass"

class ToggleRoutingRequest(BaseModel):
    id: int
    enabled: bool

@router.get("")
def list_routings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM domain_routing ORDER BY id ASC;")
    routings = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return routings

@router.post("/add")
async def add_routing(req: AddRoutingRequest):
    pattern = req.domain_pattern.strip().lower()
    raw_resolver = req.resolver.strip()
    if not pattern or not raw_resolver:
        raise HTTPException(status_code=400, detail="Pattern and resolver required")

    # Smart auto-detection and normalization for Blocky syntax (DoT, DoH, UDP)
    resolver, _ = normalize_resolver(raw_resolver)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO domain_routing (domain_pattern, resolver, tag, enabled, created_at)
    VALUES (?, ?, ?, 1, datetime('now'));
    """, (pattern, resolver, req.tag))
    conn.commit()
    conn.close()

    sync_config_from_db()
    schedule_blocky_restart()
    reload_routing_cache()
    return {"success": True, "normalized_resolver": resolver}

@router.post("/toggle")
async def toggle_routing(req: ToggleRoutingRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE domain_routing SET enabled = ? WHERE id = ?;", (1 if req.enabled else 0, req.id))
    conn.commit()
    conn.close()

    sync_config_from_db()
    schedule_blocky_restart()
    reload_routing_cache()
    return {"success": True}

@router.delete("/{target}")
async def delete_routing(target: str):
    conn = get_connection()
    cursor = conn.cursor()
    target_clean = target.strip()
    if target_clean.isdigit():
        cursor.execute("DELETE FROM domain_routing WHERE id = ?;", (int(target_clean),))
    else:
        cursor.execute("DELETE FROM domain_routing WHERE domain_pattern = ?;", (target_clean,))
    conn.commit()
    conn.close()

    sync_config_from_db()
    schedule_blocky_restart()
    reload_routing_cache()
    return {"success": True}
