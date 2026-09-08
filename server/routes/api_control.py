from fastapi import APIRouter, Depends
from pydantic import BaseModel
from auth import get_current_user
from blocky_client import check_blocky_status, enable_blocking, pause_blocking, sync_config_from_db, restart_blocky_container, flush_cache
from database import get_connection

router = APIRouter(prefix="/api/control", tags=["control"], dependencies=[Depends(get_current_user)])

class PauseRequest(BaseModel):
    duration: str = "5m"

class SettingsUpdateRequest(BaseModel):
    log_retention_days: int
    router_ip: str
    log_ptr_queries: bool = False

@router.get("/status")
async def get_blocking_status():
    status = await check_blocky_status()
    if not status.get("online"):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'blocking_enabled';")
        row = cursor.fetchone()
        conn.close()
        if row:
            status["blocking_enabled"] = (row["value"] == "true")
    return status

@router.post("/enable")
async def enable():
    ok = await enable_blocking()
    await flush_cache()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blocking_enabled', 'true');")
    conn.commit()
    conn.close()
    return {"success": True}

@router.post("/pause")
async def pause(req: PauseRequest):
    ok = await pause_blocking(req.duration)
    await flush_cache()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blocking_enabled', 'false');")
    conn.commit()
    conn.close()
    return {"success": True, "duration": req.duration}

@router.post("/flush-cache")
async def flush_dns_cache():
    ok = await flush_cache()
    return {"success": ok}

@router.post("/restart-engine")
async def restart_engine():
    sync_config_from_db()
    cache_ok = await flush_cache()
    res = await restart_blocky_container()
    return {**res, "cache_flushed": cache_ok}

@router.get("/settings")
def get_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings;")
    rows = cursor.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}

@router.post("/settings")
async def update_settings(req: SettingsUpdateRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('log_retention_days', ?);", (str(req.log_retention_days),))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('router_ip', ?);", (req.router_ip.strip(),))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('log_ptr_queries', ?);", ("true" if req.log_ptr_queries else "false",))
    conn.commit()
    conn.close()

    sync_config_from_db()
    await restart_blocky_container()
    return {"success": True}

class IntegrationUpdateRequest(BaseModel):

    integration_mode: str
    blocky_api_url: str
    blocky_config_path: str = ""

class IntegrationTestRequest(BaseModel):
    blocky_api_url: str

@router.get("/integration")
async def get_integration():
    from blocky_client import get_blocky_api_url, get_blocky_config_path, get_integration_mode, check_blocky_status
    status = await check_blocky_status()
    return {
        "integration_mode": get_integration_mode(),
        "blocky_api_url": get_blocky_api_url(),
        "blocky_config_path": str(get_blocky_config_path()),
        "status": status
    }

@router.post("/integration")
def update_integration(req: IntegrationUpdateRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('integration_mode', ?);", (req.integration_mode,))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blocky_api_url', ?);", (req.blocky_api_url.strip().rstrip("/"),))
    if req.blocky_config_path.strip():
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('blocky_config_path', ?);", (req.blocky_config_path.strip(),))
    conn.commit()
    conn.close()

    sync_config_from_db()
    return {"success": True, "integration_mode": req.integration_mode}

@router.post("/test-integration")
async def test_integration(req: IntegrationTestRequest):
    from blocky_client import test_blocky_connection
    return await test_blocky_connection(req.blocky_api_url)

from typing import Union

class CachingUpdateRequest(BaseModel):
    caching_enabled: bool = True
    cache_min_ttl: Union[int, str] = "5m"
    cache_max_ttl: Union[int, str] = "30m"
    cache_neg_ttl: Union[int, str] = "30m"
    prefetching_enabled: bool = True
    prefetch_threshold: int = 3

class DnssecUpdateRequest(BaseModel):
    dnssec_enabled: bool = True
    edns_anonymize_ecs: bool = True

@router.get("/caching")
def get_caching_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings WHERE key IN ('caching_enabled', 'cache_min_ttl', 'cache_max_ttl', 'cache_neg_ttl', 'prefetching_enabled', 'prefetch_threshold');")
    data = {r["key"]: r["value"] for r in cursor.fetchall()}
    conn.close()
    return {
        "caching_enabled": data.get("caching_enabled", "true") == "true",
        "cache_min_ttl": data.get("cache_min_ttl", "5m"),
        "cache_max_ttl": data.get("cache_max_ttl", "30m"),
        "cache_neg_ttl": data.get("cache_neg_ttl", "30m"),
        "prefetching_enabled": data.get("prefetching_enabled", "true") == "true",
        "prefetch_threshold": int(data.get("prefetch_threshold", "3"))
    }

def _normalize_ttl(ttl: Union[int, str]) -> str:
    s = str(ttl).strip()
    if s.isdigit():
        return f"{s}s"
    return s

@router.post("/caching")
def update_caching_settings(req: CachingUpdateRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('caching_enabled', ?);", ("true" if req.caching_enabled else "false",))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('cache_min_ttl', ?);", (_normalize_ttl(req.cache_min_ttl),))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('cache_max_ttl', ?);", (_normalize_ttl(req.cache_max_ttl),))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('cache_neg_ttl', ?);", (_normalize_ttl(req.cache_neg_ttl),))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('prefetching_enabled', ?);", ("true" if req.prefetching_enabled else "false",))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('prefetch_threshold', ?);", (str(req.prefetch_threshold),))
    conn.commit()
    conn.close()

    sync_config_from_db()
    return {"success": True}

@router.get("/dnssec")
def get_dnssec_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings WHERE key IN ('dnssec_enabled', 'edns_anonymize_ecs');")
    data = {r["key"]: r["value"] for r in cursor.fetchall()}
    conn.close()
    return {
        "dnssec_enabled": data.get("dnssec_enabled", "true") == "true",
        "edns_anonymize_ecs": data.get("edns_anonymize_ecs", "true") == "true"
    }

@router.post("/dnssec")
def update_dnssec_settings(req: DnssecUpdateRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('dnssec_enabled', ?);", ("true" if req.dnssec_enabled else "false",))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('edns_anonymize_ecs', ?);", ("true" if req.edns_anonymize_ecs else "false",))
    conn.commit()
    conn.close()

    sync_config_from_db()
    return {"success": True}


