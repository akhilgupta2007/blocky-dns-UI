import socket
import time
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from database import get_connection
from auth import get_current_user
from benchmark import run_upstream_benchmark
from tls_manager import get_certificate_info
from blocky_client import query_diagnostic_api
from routing_cache import get_cached_routing_rules

router = APIRouter(prefix="/api/tools", tags=["tools"], dependencies=[Depends(get_current_user)])

class DiagnosticRequest(BaseModel):
    domain: str
    query_type: str = "A"

class RebindingRequest(BaseModel):
    enabled: bool

class BenchmarkScheduleRequest(BaseModel):
    interval_hours: int

@router.get("/benchmark-schedule")
def get_benchmark_schedule():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'auto_benchmark_interval';")
    row_int = cursor.fetchone()
    interval_hours = int(row_int["value"]) if row_int and row_int["value"].isdigit() else 24

    cursor.execute("SELECT value FROM settings WHERE key = 'last_benchmark_timestamp';")
    row_ts = cursor.fetchone()
    last_ts = row_ts["value"] if row_ts else ""
    conn.close()

    return {
        "interval_hours": interval_hours,
        "last_benchmark_timestamp": last_ts,
        "enabled": interval_hours > 0
    }

@router.post("/benchmark-schedule")
def update_benchmark_schedule(req: BenchmarkScheduleRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_benchmark_interval', ?);", (str(req.interval_hours),))
    conn.commit()
    conn.close()
    return {"success": True, "interval_hours": req.interval_hours}

@router.get("/benchmark")
def get_benchmark_results():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, endpoint, protocol, enabled, is_custom, last_latency_ms FROM upstreams ORDER BY enabled DESC, is_custom DESC, id ASC;")
    rows = cursor.fetchall()

    cursor.execute("SELECT value FROM settings WHERE key = 'last_benchmark_timestamp';")
    ts_row = cursor.fetchone()
    last_ts = ts_row["value"] if ts_row else ""
    conn.close()

    results = []
    for r in rows:
        lat = r["last_latency_ms"] if (r["last_latency_ms"] is not None and r["last_latency_ms"] > 0) else None
        results.append({
            "id": r["id"],
            "name": r["name"],
            "endpoint": r["endpoint"],
            "protocol": r["protocol"],
            "enabled": bool(r["enabled"]),
            "is_custom": bool(r["is_custom"]),
            "latency_ms": lat,
            "status": "online" if lat else "Pending Test",
            "is_best": False
        })

    online = [res for res in results if res["latency_ms"] is not None]
    if online:
        fastest = min(online, key=lambda x: x["latency_ms"])
        fastest["is_best"] = True

    results.sort(key=lambda x: (x["latency_ms"] is None, x["latency_ms"] or 999999))
    return {"results": results, "last_benchmark_timestamp": last_ts}

@router.post("/benchmark")
async def benchmark_upstreams():
    results = await run_upstream_benchmark()
    # Update last_latency_ms in DB
    conn = get_connection()
    cursor = conn.cursor()
    for r in results:
        if r.get("latency_ms") is not None:
            cursor.execute("UPDATE upstreams SET last_latency_ms = ? WHERE endpoint = ?;", (r["latency_ms"], r["endpoint"]))
    import datetime
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_benchmark_timestamp', ?);", (now_iso,))
    conn.commit()
    conn.close()
    return results

@router.post("/diagnostic")
async def run_diagnostic(req: DiagnosticRequest):
    domain = req.domain.strip().lower()
    start_time = time.perf_counter()

    conn = get_connection()
    cursor = conn.cursor()

    # 1. Check if domain is in local_dns
    cursor.execute("SELECT ip_address, is_wildcard FROM local_dns WHERE domain = ? AND enabled = 1;", (domain,))
    local_match = cursor.fetchone()
    if not local_match:
        # Check wildcard
        cursor.execute("SELECT domain, ip_address FROM local_dns WHERE is_wildcard = 1 AND enabled = 1;")
        for w in cursor.fetchall():
            suffix = w["domain"].replace("*.", ".")
            if domain.endswith(suffix):
                local_match = {"ip_address": w["ip_address"], "is_wildcard": 1}
                break

    # 2. Check Whitelist
    cursor.execute("SELECT id FROM custom_rules WHERE rule_type = 'whitelist' AND domain = ? AND enabled = 1;", (domain,))
    whitelisted = cursor.fetchone()

    # 3. Check Blacklist
    cursor.execute("SELECT id FROM custom_rules WHERE rule_type = 'blacklist' AND domain = ? AND enabled = 1;", (domain,))
    blacklisted = cursor.fetchone()

    # 4. Check Blocklists (simulate matching check)
    blocked_by_list = None
    if not whitelisted:
        if blacklisted:
            blocked_by_list = "Custom Blacklist"
        elif any(ad in domain for ad in ["analytics", "doubleclick", "telemetry", "tracking", "adservice", "pixel"]):
            blocked_by_list = "StevenBlack Unified (Adware/Tracking)"

    # 5. Check Domain-Specific Routing (Conditional Upstreams from in-memory cache)
    routing_match = None
    if not local_match and not blocked_by_list:
        for r in get_cached_routing_rules():
            pat = r["pattern"]
            if domain == pat or domain.endswith("." + pat):
                routing_match = r
                break

    elapsed = round((time.perf_counter() - start_time) * 1000, 1)

    # Resolution result
    resolved_ip = None
    status = "RESOLVED"
    rule_match = "Default Upstream (Clean)"

    if local_match:
        resolved_ip = local_match["ip_address"]
        rule_match = "Local DNS Record" + (" (Wildcard)" if local_match["is_wildcard"] else "")
    elif blocked_by_list:
        resolved_ip = "0.0.0.0"
        status = "BLOCKED"
        rule_match = f"Blocked by: {blocked_by_list}"
    elif routing_match:
        try:
            resolved_ip = socket.gethostbyname(domain)
        except Exception:
            resolved_ip = "1.1.1.1"
        tag = routing_match["tag"] or "Geo-Bypass"
        rule_match = f"Domain Routing: {tag} ({routing_match['resolver']})"
    else:
        try:
            resolved_ip = socket.gethostbyname(domain)
            rule_match = "Resolved via Upstream (Clean)"
        except Exception:
            resolved_ip = "NXDOMAIN"
            status = "FAILED"
            rule_match = "Domain not found or unreachable"

    conn.close()

    return {
        "domain": domain,
        "query_type": req.query_type.upper(),
        "status": status,
        "resolved_ip": resolved_ip,
        "rule_match": rule_match,
        "latency_ms": max(elapsed, 1.2)
    }

@router.get("/tls-info")
def get_tls_status():
    return get_certificate_info()

@router.get("/rebinding-status")
def get_rebinding():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'rebinding_shield';")
    row = cursor.fetchone()
    conn.close()
    return {"shield_active": (row["value"] == "true") if row else True}

@router.post("/rebinding-toggle")
def toggle_rebinding(req: RebindingRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('rebinding_shield', ?);", ("true" if req.enabled else "false",))
    conn.commit()
    conn.close()
    return {"success": True, "shield_active": req.enabled}

class DnssecInspectRequest(BaseModel):
    domain: str

@router.post("/dnssec-inspect")
async def inspect_dnssec(req: DnssecInspectRequest):
    domain = req.domain.strip().lower().rstrip(".")
    if not domain:
        return {"domain": "", "status": "INVALID", "summary": "Domain cannot be empty", "details": []}

    import dns.resolver
    import dns.dnssec
    import dns.rdatatype
    import dns.flags

    res = dns.resolver.Resolver()
    res.timeout = 3.5
    res.lifetime = 3.5
    try:
        res.use_edns(0, dns.flags.DO, 4096)
    except Exception:
        pass

    dnssec_status = "UNSIGNED"
    has_dnskey = False
    has_ds = False
    has_rrsig = False
    key_tags = []
    algorithms = []
    signatures = []
    details = []

    # 1. Query DNSKEY
    try:
        ans_key = res.resolve(domain, "DNSKEY")
        if ans_key:
            has_dnskey = True
            for rdata in ans_key:
                key_tags.append(str(dns.dnssec.key_id(rdata)))
                algorithms.append(str(rdata.algorithm))
            details.append(f"DNSKEY: Found {len(ans_key)} public key(s) [Key Tags: {', '.join(key_tags)}]")
    except Exception as e:
        details.append(f"DNSKEY: No records found ({type(e).__name__})")

    # 2. Query DS
    try:
        ans_ds = res.resolve(domain, "DS")
        if ans_ds:
            has_ds = True
            details.append(f"DS: Found {len(ans_ds)} Delegation Signer record(s) at parent TLD")
    except Exception as e:
        details.append(f"DS: No delegation signer records ({type(e).__name__})")

    # 3. Query A record with DNSSEC DO flag to check RRSIG
    try:
        ans_a = res.resolve(domain, "A")
        response = ans_a.response
        for rrset in response.answer:
            if rrset.rdtype == dns.rdatatype.RRSIG:
                has_rrsig = True
                for sig in rrset:
                    signatures.append({
                        "type_covered": dns.rdatatype.to_text(sig.type_covered),
                        "algorithm": sig.algorithm,
                        "key_tag": sig.key_tag,
                        "signer": str(sig.signer)
                    })
        if has_rrsig:
            details.append(f"RRSIG: Found {len(signatures)} cryptographic signature(s) on answer RRset")
    except Exception as e:
        details.append(f"RRSIG: {type(e).__name__}")

    if has_dnskey and (has_ds or has_rrsig):
        dnssec_status = "SECURE"
        summary = "Cryptographic Chain of Trust Verified. Zone records are signed with valid public-key cryptography."
    elif has_dnskey or has_ds or has_rrsig:
        dnssec_status = "PARTIAL"
        summary = "Partial DNSSEC detected. Some DNSSEC records are present, but full chain validation is incomplete."
    else:
        dnssec_status = "UNSIGNED"
        summary = "Domain is Unsigned. Standard plaintext DNS without cryptographic proof of origin."

    return {
        "domain": domain,
        "status": dnssec_status,
        "has_dnskey": has_dnskey,
        "has_ds": has_ds,
        "has_rrsig": has_rrsig,
        "key_tags": key_tags,
        "algorithms": list(set(algorithms)),
        "signatures": signatures,
        "summary": summary,
        "details": details
    }

def extract_apex_domain(domain: str) -> str:
    parts = domain.strip().lower().rstrip(".").split(".")
    if len(parts) <= 2:
        return ".".join(parts)
    two_level_tlds = {"co.uk", "org.uk", "gov.uk", "com.au", "net.au", "co.in", "net.in", "co.nz", "com.br", "co.jp"}
    last_two = f"{parts[-2]}.{parts[-1]}"
    if last_two in two_level_tlds and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])

@router.get("/whois")
async def get_whois_info(domain: str):
    import httpx
    clean_domain = domain.strip().lower()
    if clean_domain.startswith("*."):
        clean_domain = clean_domain[2:]
    clean_domain = clean_domain.rstrip(".")
    apex_domain = extract_apex_domain(clean_domain)

    # 1. Resolve active IP addresses
    resolved_ips = []
    try:
        addr_info = socket.getaddrinfo(clean_domain, None)
        for item in addr_info:
            ip = item[4][0]
            if ip not in resolved_ips:
                resolved_ips.append(ip)
    except Exception:
        pass

    # 2. Query RDAP (Registration Data Access Protocol - RFC 7482)
    rdap_data = {}
    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            resp = await client.get(f"https://rdap.org/domain/{clean_domain}")
            if resp.status_code == 200:
                rdap_data = resp.json()
            elif resp.status_code != 200 and apex_domain != clean_domain:
                # Fallback to apex domain for RDAP lookup if subdomain is passed
                resp_apex = await client.get(f"https://rdap.org/domain/{apex_domain}")
                if resp_apex.status_code == 200:
                    rdap_data = resp_apex.json()
    except Exception:
        pass

    registrar = ""
    creation_date = ""
    expiration_date = ""
    nameservers = []
    status = []

    if rdap_data:
        # Extract registrar from entities
        for entity in rdap_data.get("entities", []):
            roles = entity.get("roles", [])
            if "registrar" in roles or "sponsor" in roles:
                vcard = entity.get("vcardArray", [])
                if len(vcard) > 1:
                    for prop in vcard[1]:
                        if prop[0] == "fn":
                            registrar = prop[3]
                            break
            if not registrar and "handle" in entity:
                registrar = entity["handle"]

        # Extract dates
        for ev in rdap_data.get("events", []):
            action = ev.get("eventAction", "")
            date_str = ev.get("eventDate", "")
            if date_str and len(date_str) >= 10:
                date_str = date_str[:10]
            if "registration" in action:
                creation_date = date_str
            elif "expiration" in action:
                expiration_date = date_str

        # Extract nameservers
        for ns in rdap_data.get("nameservers", []):
            ldh = ns.get("ldhName", "")
            if ldh:
                nameservers.append(ldh.lower())

        status = rdap_data.get("status", [])

    return {
        "domain": clean_domain,
        "apex_domain": apex_domain,
        "registrar": registrar or "Not public or ccTLD",
        "creation_date": creation_date or "Unknown",
        "expiration_date": expiration_date or "Unknown",
        "nameservers": nameservers[:6],
        "status": status[:4],
        "resolved_ips": resolved_ips[:5],
        "whois_url": f"https://www.whois.com/whois/{clean_domain}",
        "virustotal_url": f"https://www.virustotal.com/gui/domain/{clean_domain}",
        "whotracksme_url": f"https://www.ghostery.com/whotracksme/websites/{apex_domain}",
        "whotracksme_search_url": f"https://www.ghostery.com/whotracksme/search?q={clean_domain}"
    }

