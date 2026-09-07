import json
from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import JSONResponse
from database import get_connection
from auth import get_current_user
from blocky_client import sync_config_from_db

router = APIRouter(prefix="/api/backup", tags=["backup"], dependencies=[Depends(get_current_user)])

@router.get("/export")
def export_backup():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT name, url, category, enabled FROM blocklists;")
    blocklists = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT rule_type, domain, is_wildcard, is_regex, enabled, comment FROM custom_rules;")
    rules = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT domain, ip_address, record_type, is_wildcard, enabled FROM local_dns;")
    local_dns = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT domain_pattern, resolver, tag, enabled FROM domain_routing;")
    routings = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT name, endpoint, protocol, enabled, is_custom FROM upstreams;")
    upstreams = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT client_ip, friendly_name, icon, group_name FROM devices WHERE friendly_name IS NOT NULL;")
    devices = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT key, value FROM settings;")
    settings = {r["key"]: r["value"] for r in cursor.fetchall()}

    conn.close()

    backup_data = {
        "version": "1.0.0",
        "app": "BlockyDNS Hub",
        "blocklists": blocklists,
        "rules": rules,
        "local_dns": local_dns,
        "domain_routing": routings,
        "upstreams": upstreams,
        "devices": devices,
        "settings": settings
    }
    return JSONResponse(
        content=backup_data,
        headers={"Content-Disposition": "attachment; filename=blockydns_backup.json"}
    )

@router.post("/import")
async def import_backup(file: UploadFile = File(...)):
    content = await file.read()
    data = json.loads(content.decode("utf-8"))

    conn = get_connection()
    cursor = conn.cursor()

    if "blocklists" in data:
        for b in data["blocklists"]:
            cursor.execute("""
            INSERT OR REPLACE INTO blocklists (name, url, category, enabled, rule_count, last_updated)
            VALUES (?, ?, ?, ?, 0, datetime('now'));
            """, (b["name"], b["url"], b.get("category", "Custom"), b.get("enabled", 1)))

    if "rules" in data:
        for r in data["rules"]:
            cursor.execute("""
            INSERT OR REPLACE INTO custom_rules (rule_type, domain, is_wildcard, is_regex, enabled, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'));
            """, (r["rule_type"], r["domain"], r.get("is_wildcard", 0), r.get("is_regex", 0), r.get("enabled", 1), r.get("comment", "")))

    if "local_dns" in data:
        for l in data["local_dns"]:
            cursor.execute("""
            INSERT OR REPLACE INTO local_dns (domain, ip_address, record_type, is_wildcard, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'));
            """, (l["domain"], l["ip_address"], l.get("record_type", "A"), l.get("is_wildcard", 0), l.get("enabled", 1)))

    if "domain_routing" in data:
        for ro in data["domain_routing"]:
            cursor.execute("""
            INSERT OR REPLACE INTO domain_routing (domain_pattern, resolver, tag, enabled, created_at)
            VALUES (?, ?, ?, ?, datetime('now'));
            """, (ro["domain_pattern"], ro["resolver"], ro.get("tag", "Geo-Bypass"), ro.get("enabled", 1)))

    conn.commit()
    conn.close()

    sync_config_from_db()
    return {"success": True, "message": "Backup restored successfully"}
