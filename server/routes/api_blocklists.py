from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import get_connection
from auth import get_current_user
from blocky_client import sync_config_from_db, refresh_lists, flush_cache, restart_blocky_container

router = APIRouter(prefix="/api/blocklists", tags=["blocklists"], dependencies=[Depends(get_current_user)])

class AddBlocklistRequest(BaseModel):
    name: str
    url: str
    category: str = "Custom"

class ToggleRequest(BaseModel):
    id: int
    enabled: bool

@router.get("")
def list_blocklists():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blocklists ORDER BY id ASC;")
    lists = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return lists

@router.post("/toggle")
async def toggle_blocklist(req: ToggleRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE blocklists SET enabled = ? WHERE id = ?;", (1 if req.enabled else 0, req.id))
    conn.commit()
    conn.close()

    sync_config_from_db()
    await refresh_lists()
    await flush_cache()
    return {"success": True}

@router.post("/add")
async def add_blocklist(req: AddBlocklistRequest):
    url = req.url.strip()
    name = req.name.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Blocklist URL must start with http:// or https://")

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT OR REPLACE INTO blocklists (name, url, category, enabled, rule_count, last_updated)
        VALUES (?, ?, ?, 1, 0, datetime('now'));
        """, (name, url, req.category))
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Failed to save blocklist: {e}")
    conn.close()

    sync_config_from_db()
    await refresh_lists()
    await flush_cache()
    return {"success": True}

@router.delete("/{target:path}")
async def delete_blocklist(target: str):
    conn = get_connection()
    cursor = conn.cursor()
    target_clean = target.strip()
    if target_clean.isdigit():
        cursor.execute("DELETE FROM blocklists WHERE id = ?;", (int(target_clean),))
    else:
        cursor.execute("DELETE FROM blocklists WHERE url = ? OR name = ?;", (target_clean, target_clean))
    conn.commit()
    conn.close()

    sync_config_from_db()
    await refresh_lists()
    await flush_cache()
    return {"success": True}

@router.post("/refresh")
async def trigger_refresh():
    sync_config_from_db()
    ok = await refresh_lists()
    await flush_cache()
    return {"success": ok}
