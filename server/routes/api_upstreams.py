import ipaddress
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import get_connection
from auth import get_current_user
from blocky_client import sync_config_from_db, schedule_blocky_restart, restart_blocky_container
from benchmark import benchmark_single_doh, benchmark_single_dot, benchmark_single_udp
from resolver_utils import normalize_resolver, probe_and_normalize_resolver

router = APIRouter(prefix="/api/upstreams", tags=["upstreams"], dependencies=[Depends(get_current_user)])

def is_private_or_local_ip(host_or_endpoint: str) -> bool:
    """Returns True if the endpoint resolves to a local/private RFC 1918 or loopback address."""
    clean = host_or_endpoint.replace("https://", "").replace("http://", "").replace("tcp-tls:", "").replace("udp:", "")
    clean = clean.split("/")[0].split(":")[0].strip()
    try:
        ip = ipaddress.ip_address(clean)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return clean in ["localhost", "router.lan", "local"]

class AddUpstreamRequest(BaseModel):
    name: str
    endpoint: str
    protocol: Optional[str] = None # 'doh', 'dot', 'udp'

class ProbeRequest(BaseModel):
    endpoint: str
    protocol: Optional[str] = None

class ToggleUpstreamRequest(BaseModel):
    id: int
    enabled: bool

class StrictModeRequest(BaseModel):
    enabled: bool

class BlockIpv6Request(BaseModel):
    enabled: bool

class StrategyRequest(BaseModel):
    strategy: str # 'parallel_best', 'strict', 'random'

@router.get("")
def list_upstreams():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM upstreams ORDER BY id ASC;")
    upstreams = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT value FROM settings WHERE key = 'strict_encrypted_mode';")
    strict_row = cursor.fetchone()
    strict_mode = (strict_row["value"] == "true") if strict_row else True

    cursor.execute("SELECT value FROM settings WHERE key = 'block_ipv6';")
    ipv6_row = cursor.fetchone()
    block_ipv6 = (ipv6_row["value"] == "true") if ipv6_row else True

    cursor.execute("SELECT value FROM settings WHERE key = 'upstream_strategy';")
    strat_row = cursor.fetchone()
    strategy = strat_row["value"] if strat_row else "parallel_best"

    conn.close()
    return {
        "upstreams": upstreams,
        "strict_encrypted_mode": strict_mode,
        "block_ipv6": block_ipv6,
        "strategy": strategy
    }

@router.post("/strategy")
async def set_upstream_strategy(req: StrategyRequest):
    if req.strategy not in ["parallel_best", "fastest_first", "strict", "random"]:
        raise HTTPException(status_code=400, detail="Invalid strategy. Options: parallel_best, fastest_first, strict, random")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('upstream_strategy', ?);", (req.strategy,))
    conn.commit()
    conn.close()

    sync_config_from_db()
    schedule_blocky_restart()
    return {"success": True, "strategy": req.strategy}

@router.post("/auto-sort")
async def auto_sort_upstreams():
    """Re-syncs config ordering based on lowest measured latency."""
    sync_config_from_db()
    schedule_blocky_restart()
    return {"success": True}

@router.post("/strict-mode")
async def set_strict_mode(req: StrictModeRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('strict_encrypted_mode', ?);", ("true" if req.enabled else "false",))
    
    if req.enabled:
        # Disable unencrypted public WAN resolvers (allow private homelab IPs to remain)
        cursor.execute("SELECT id, endpoint FROM upstreams WHERE protocol = 'udp';")
        for row in cursor.fetchall():
            if not is_private_or_local_ip(row["endpoint"]):
                cursor.execute("UPDATE upstreams SET enabled = 0 WHERE id = ?;", (row["id"],))

    conn.commit()
    conn.close()

    sync_config_from_db()
    schedule_blocky_restart()
    return {"success": True, "strict_encrypted_mode": req.enabled}

@router.post("/block-ipv6")
async def set_block_ipv6(req: BlockIpv6Request):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('block_ipv6', ?);", ("true" if req.enabled else "false",))
    conn.commit()
    conn.close()

    sync_config_from_db()
    schedule_blocky_restart()
    return {"success": True, "block_ipv6": req.enabled}

@router.post("/toggle")
async def toggle_upstream(req: ToggleUpstreamRequest):
    conn = get_connection()
    cursor = conn.cursor()

    # Check strict mode
    cursor.execute("SELECT value FROM settings WHERE key = 'strict_encrypted_mode';")
    strict_row = cursor.fetchone()
    strict_mode = (strict_row["value"] == "true") if strict_row else False

    if strict_mode and req.enabled:
        cursor.execute("SELECT endpoint, protocol FROM upstreams WHERE id = ?;", (req.id,))
        u = cursor.fetchone()
        if u and u["protocol"] == "udp" and not is_private_or_local_ip(u["endpoint"]):
            conn.close()
            raise HTTPException(status_code=400, detail="Cannot enable unencrypted public UDP resolver when Strict Encrypted DNS Mode is active.")

    cursor.execute("UPDATE upstreams SET enabled = ? WHERE id = ?;", (1 if req.enabled else 0, req.id))
    conn.commit()
    conn.close()

    sync_config_from_db()
    schedule_blocky_restart()
    return {"success": True}

@router.post("/probe")
async def probe_endpoint(req: ProbeRequest):
    """Probes and auto-detects DoT/DoH/UDP protocol and measures latency."""
    res = await probe_and_normalize_resolver(req.endpoint, req.protocol)
    return res

@router.post("/add")
async def add_upstream(req: AddUpstreamRequest):
    raw_endpoint = req.endpoint.strip()
    name = req.name.strip()
    raw_proto = req.protocol.strip().lower() if req.protocol else None

    # Smart auto-detector and normalizer for DoT / DoH / UDP
    endpoint, protocol = normalize_resolver(raw_endpoint, raw_proto)
    if not name:
        name = endpoint

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'strict_encrypted_mode';")
    strict_row = cursor.fetchone()
    if strict_row and strict_row["value"] == "true" and protocol == "udp":
        # Allow private/local LAN homelab DNS resolvers
        if not is_private_or_local_ip(endpoint):
            conn.close()
            raise HTTPException(status_code=400, detail="Plain unencrypted public UDP resolvers are disallowed in Strict Encrypted DNS Mode.")

    # 1. Initial latency probe so latency is available immediately
    initial_latency = 0.0
    try:
        if protocol == "doh":
            bench_res = await benchmark_single_doh(endpoint)
            if bench_res.get("latency_ms"):
                initial_latency = float(bench_res["latency_ms"])
        elif protocol == "dot":
            bench_res = await benchmark_single_dot(endpoint)
            if bench_res.get("latency_ms"):
                initial_latency = float(bench_res["latency_ms"])
        elif protocol == "udp":
            bench_res = await benchmark_single_udp(endpoint)
            if bench_res.get("latency_ms"):
                initial_latency = float(bench_res["latency_ms"])
    except Exception:
        pass

    try:
        cursor.execute("""
        INSERT INTO upstreams (name, endpoint, protocol, enabled, is_custom, last_latency_ms)
        VALUES (?, ?, ?, 1, 1, ?)
        ON CONFLICT(endpoint) DO UPDATE SET
            name = excluded.name,
            protocol = excluded.protocol,
            enabled = 1,
            last_latency_ms = excluded.last_latency_ms;
        """, (name, endpoint, protocol, initial_latency))
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Failed to save upstream: {e}")
    conn.close()

    sync_config_from_db()
    schedule_blocky_restart()
    return {"success": True}

@router.post("/test")
async def test_upstream(req: AddUpstreamRequest):
    endpoint = req.endpoint.strip()
    proto = req.protocol.lower()
    if proto == "doh":
        res = await benchmark_single_doh(endpoint)
    elif proto == "dot":
        res = await benchmark_single_dot(endpoint)
    elif proto == "udp":
        res = await benchmark_single_udp(endpoint)
    else:
        res = {"latency_ms": None, "status": "unsupported"}
    return res

@router.delete("/{upstream_id}")
async def delete_upstream(upstream_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM upstreams WHERE id = ? AND is_custom = 1;", (upstream_id,))
    conn.commit()
    conn.close()

    sync_config_from_db()
    schedule_blocky_restart()
    return {"success": True}
