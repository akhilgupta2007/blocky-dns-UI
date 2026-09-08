from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import get_connection
from auth import get_current_user
from blocky_client import sync_config_from_db, schedule_blocky_restart

router = APIRouter(prefix="/api/local-dns", tags=["local-dns"], dependencies=[Depends(get_current_user)])

class AddLocalDnsRequest(BaseModel):
    domain: str
    ip_address: str
    record_type: str = "A"

@router.get("")
def list_local_dns():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM local_dns ORDER BY id ASC;")
    records = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return records

@router.post("/add")
async def add_local_dns(req: AddLocalDnsRequest):
    domain = req.domain.strip().lower()
    ip = req.ip_address.strip()
    if not domain or not ip:
        raise HTTPException(status_code=400, detail="Domain and IP are required")

    is_wildcard = 1 if domain.startswith("*.") else 0

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO local_dns (domain, ip_address, record_type, is_wildcard, enabled, created_at)
    VALUES (?, ?, ?, ?, 1, datetime('now'));
    """, (domain, ip, req.record_type.upper(), is_wildcard))
    conn.commit()
    conn.close()

    sync_config_from_db()
    schedule_blocky_restart()
    return {"success": True}

@router.delete("/{target}")
async def delete_local_dns(target: str):
    conn = get_connection()
    cursor = conn.cursor()
    target_clean = target.strip()
    if target_clean.isdigit():
        cursor.execute("DELETE FROM local_dns WHERE id = ?;", (int(target_clean),))
    else:
        cursor.execute("DELETE FROM local_dns WHERE domain = ? OR domain = ?;", (target_clean.lower(), target_clean))
    conn.commit()
    conn.close()

    sync_config_from_db()
    schedule_blocky_restart()
    return {"success": True}
