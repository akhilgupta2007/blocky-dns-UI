import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import get_connection
from auth import get_current_user
from blocky_client import sync_config_from_db, refresh_lists, flush_cache

router = APIRouter(prefix="/api/services", tags=["services"], dependencies=[Depends(get_current_user)])

class ToggleServiceRequest(BaseModel):
    service_id: str
    enabled: bool

class BulkToggleRequest(BaseModel):
    category: str = "ALL"  # 'ALL' or specific category name
    enabled: bool

@router.get("")
def get_blocked_services():
    """Returns all blocked services grouped by category with domain counts and enabled states."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category, icon, domains_json, enabled, updated_at FROM blocked_services ORDER BY category ASC, name ASC;")
    rows = cursor.fetchall()
    conn.close()

    services = []
    total_blocked_services = 0
    total_blocked_domains = 0

    for r in rows:
        try:
            domains = json.loads(r["domains_json"])
        except Exception:
            domains = []

        is_enabled = bool(r["enabled"])
        if is_enabled:
            total_blocked_services += 1
            total_blocked_domains += len(domains)

        services.append({
            "id": r["id"],
            "name": r["name"],
            "category": r["category"],
            "icon": r["icon"],
            "domains": domains,
            "domain_count": len(domains),
            "enabled": is_enabled,
            "updated_at": r["updated_at"]
        })

    return {
        "services": services,
        "total_services": len(services),
        "active_blocked_services": total_blocked_services,
        "active_blocked_domains": total_blocked_domains
    }

@router.post("/toggle")
async def toggle_service(req: ToggleServiceRequest):
    """Toggles a single service ON or OFF, updates SQLite, and syncs Blocky config."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM blocked_services WHERE id = ?;", (req.service_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Service not found")

    cursor.execute("""
    UPDATE blocked_services
    SET enabled = ?, updated_at = datetime('now')
    WHERE id = ?;
    """, (1 if req.enabled else 0, req.service_id))
    conn.commit()
    conn.close()

    # Re-sync Blocky config, compile lists, and flush memory cache (Zero-Downtime in-place reload)
    sync_config_from_db()
    await refresh_lists()
    await flush_cache()

    return {
        "success": True,
        "service_id": req.service_id,
        "service_name": existing["name"],
        "enabled": req.enabled
    }

@router.post("/bulk")
async def bulk_toggle_services(req: BulkToggleRequest):
    """Enables or disables all services in a category or across the entire catalog."""
    conn = get_connection()
    cursor = conn.cursor()

    if req.category.upper() == "ALL":
        cursor.execute("""
        UPDATE blocked_services
        SET enabled = ?, updated_at = datetime('now');
        """, (1 if req.enabled else 0,))
    else:
        cursor.execute("""
        UPDATE blocked_services
        SET enabled = ?, updated_at = datetime('now')
        WHERE category = ?;
        """, (1 if req.enabled else 0, req.category))

    affected = cursor.rowcount
    conn.commit()
    conn.close()

    sync_config_from_db()
    await refresh_lists()
    await flush_cache()

    return {
        "success": True,
        "category": req.category,
        "enabled": req.enabled,
        "affected_services": affected,
        "updated_count": affected
    }
