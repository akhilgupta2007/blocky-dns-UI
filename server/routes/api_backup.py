import json
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from database import get_connection
from auth import get_current_user
from blocky_client import sync_config_from_db

router = APIRouter(prefix="/api/backup", tags=["backup"], dependencies=[Depends(get_current_user)])

MAX_BACKUP_SIZE = 10 * 1024 * 1024  # 10 MB limit to prevent memory exhaustion

@router.get("/export")
def export_backup():
    conn = get_connection()
    try:
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

        cursor.execute("SELECT id, name, category, icon, domains_json, enabled FROM blocked_services;")
        blocked_services = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT key, value FROM settings WHERE key != 'jwt_secret';")
        settings = {r["key"]: r["value"] for r in cursor.fetchall()}

        backup_data = {
            "version": "1.0.0",
            "app": "BlockyDNS Hub",
            "blocklists": blocklists,
            "rules": rules,
            "local_dns": local_dns,
            "domain_routing": routings,
            "upstreams": upstreams,
            "devices": devices,
            "blocked_services": blocked_services,
            "settings": settings
        }
        return JSONResponse(
            content=backup_data,
            headers={"Content-Disposition": "attachment; filename=blockydns_backup.json"}
        )
    finally:
        conn.close()

@router.post("/import")
async def import_backup(file: UploadFile = File(...)):
    content = await file.read(MAX_BACKUP_SIZE + 1)
    if len(content) > MAX_BACKUP_SIZE:
        raise HTTPException(status_code=413, detail="Backup file exceeds maximum allowed size (10 MB)")

    try:
        data = json.loads(content.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in backup file: {e}")

    conn = get_connection()
    try:
        cursor = conn.cursor()

        if "blocklists" in data and isinstance(data["blocklists"], list):
            for b in data["blocklists"]:
                cursor.execute("""
                INSERT OR REPLACE INTO blocklists (name, url, category, enabled, rule_count, last_updated)
                VALUES (?, ?, ?, ?, 0, datetime('now'));
                """, (b["name"], b["url"], b.get("category", "Custom"), b.get("enabled", 1)))

        if "rules" in data and isinstance(data["rules"], list):
            for r in data["rules"]:
                cursor.execute("""
                INSERT OR REPLACE INTO custom_rules (rule_type, domain, is_wildcard, is_regex, enabled, comment, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'));
                """, (r["rule_type"], r["domain"], r.get("is_wildcard", 0), r.get("is_regex", 0), r.get("enabled", 1), r.get("comment", "")))

        if "local_dns" in data and isinstance(data["local_dns"], list):
            for l in data["local_dns"]:
                cursor.execute("""
                INSERT OR REPLACE INTO local_dns (domain, ip_address, record_type, is_wildcard, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'));
                """, (l["domain"], l["ip_address"], l.get("record_type", "A"), l.get("is_wildcard", 0), l.get("enabled", 1)))

        if "domain_routing" in data and isinstance(data["domain_routing"], list):
            for ro in data["domain_routing"]:
                cursor.execute("""
                INSERT OR REPLACE INTO domain_routing (domain_pattern, resolver, tag, enabled, created_at)
                VALUES (?, ?, ?, ?, datetime('now'));
                """, (ro["domain_pattern"], ro["resolver"], ro.get("tag", "Geo-Bypass"), ro.get("enabled", 1)))

        if "upstreams" in data and isinstance(data["upstreams"], list):
            for u in data["upstreams"]:
                cursor.execute("""
                INSERT OR REPLACE INTO upstreams (name, endpoint, protocol, enabled, is_custom)
                VALUES (?, ?, ?, ?, ?);
                """, (u["name"], u["endpoint"], u["protocol"], u.get("enabled", 1), u.get("is_custom", 0)))

        if "devices" in data and isinstance(data["devices"], list):
            for d in data["devices"]:
                cursor.execute("""
                INSERT INTO devices (client_ip, friendly_name, icon, group_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(client_ip) DO UPDATE SET
                    friendly_name = excluded.friendly_name,
                    icon = excluded.icon,
                    group_name = excluded.group_name;
                """, (d["client_ip"], d.get("friendly_name"), d.get("icon", "device"), d.get("group_name", "default")))

        if "blocked_services" in data and isinstance(data["blocked_services"], list):
            for s in data["blocked_services"]:
                cursor.execute("""
                INSERT OR REPLACE INTO blocked_services (id, name, category, icon, domains_json, enabled, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'));
                """, (s["id"], s["name"], s["category"], s["icon"], s["domains_json"], s.get("enabled", 0)))

        if "settings" in data and isinstance(data["settings"], dict):
            for k, v in data["settings"].items():
                if k == "jwt_secret":
                    continue
                cursor.execute("""
                INSERT OR REPLACE INTO settings (key, value)
                VALUES (?, ?);
                """, (k, str(v)))

        conn.commit()
    finally:
        conn.close()

    sync_config_from_db()
    return {"success": True, "message": "Backup restored successfully"}
