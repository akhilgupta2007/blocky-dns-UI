import time
import os
import json
import yaml
import httpx
import asyncio
from pathlib import Path
from database import get_connection


BASE_DIR = Path(__file__).resolve().parent.parent

def get_blocky_api_url() -> str:
    # In Docker container environments, always respect the container's environment URL
    env_url = os.getenv("BLOCKY_API_URL")
    if env_url:
        return env_url.rstrip("/")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'blocky_api_url';")
        row = cursor.fetchone()
        conn.close()
        if row and row["value"]:
            return row["value"].rstrip("/")
    except Exception:
        pass
    return "http://localhost:4000"

def get_blocky_config_path() -> Path:
    # In Docker container environments, always respect the container's environment path
    env_path = os.getenv("BLOCKY_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'blocky_config_path';")
        row = cursor.fetchone()
        conn.close()
        if row and row["value"]:
            val = row["value"].strip()
            # Guard against Windows drive paths inside Linux containers
            if os.name != 'nt' and (':' in val or '\\' in val):
                return BASE_DIR / "config" / "config.yml"
            return Path(val)
    except Exception:
        pass
    return BASE_DIR / "config" / "config.yml"

def get_integration_mode() -> str:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'integration_mode';")
        row = cursor.fetchone()
        conn.close()
        if row and row["value"]:
            return row["value"]
    except Exception:
        pass
    return os.getenv("INTEGRATION_MODE", "all-in-one")

async def test_blocky_connection(api_url: str) -> dict:
    """Tests connection to a target Blocky API endpoint and returns latency/blocking status."""
    url = api_url.rstrip("/")
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{url}/api/blocking/status")
            elapsed = round((time.perf_counter() - start) * 1000, 1)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "online": True,
                    "latency_ms": elapsed,
                    "status_code": 200,
                    "blocking_enabled": data.get("enabled", True),
                    "disabled_duration": data.get("disabledDuration", 0),
                    "auto_enable_in_sec": data.get("autoEnableInSec", 0),
                    "extra": data
                }
            return {
                "online": False,
                "latency_ms": elapsed,
                "status_code": resp.status_code,
                "error": f"HTTP {resp.status_code}: {resp.text[:100]}"
            }
    except Exception as e:
        return {
            "online": False,
            "error": f"{type(e).__name__}: {str(e)}"
        }

async def check_blocky_status():
    """Queries Blocky's HTTP API for blocking status."""
    api_url = get_blocky_api_url()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{api_url}/api/blocking/status")
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "online": True,
                    "blocking_enabled": data.get("enabled", True),
                    "disabled_duration": data.get("disabledDuration", 0),
                    "auto_enable_in_sec": data.get("autoEnableInSec", 0),
                    "extra": data
                }
    except Exception as e:
        return {
            "online": False,
            "blocking_enabled": True,
            "error": str(e)
        }
    return {"online": False, "blocking_enabled": True}

async def enable_blocking():
    """Enables DNS blocking via Blocky API."""
    api_url = get_blocky_api_url()
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{api_url}/api/blocking/enable")
            return resp.status_code == 200
    except Exception:
        return False

async def pause_blocking(duration_str: str = "5m"):
    """Temporarily or indefinitely disables DNS blocking (e.g. 1m, 10m, 30m, 1h, permanent)."""
    api_url = get_blocky_api_url()
    try:
        url = f"{api_url}/api/blocking/disable"
        if duration_str and duration_str.lower() != "permanent":
            url = f"{api_url}/api/blocking/disable?duration={duration_str}"
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except Exception:
        return False

async def refresh_lists():
    """Instructs Blocky to re-download and re-compile all blocklists."""
    api_url = get_blocky_api_url()
    try:
        timeout = httpx.Timeout(connect=2.0, read=60.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{api_url}/api/lists/refresh")
            return resp.status_code == 200
    except Exception:
        return False

async def flush_cache() -> bool:
    """Instructs Blocky to clear its in-memory DNS cache via POST /api/cache/flush."""
    api_url = get_blocky_api_url()
    try:
        timeout = httpx.Timeout(connect=1.5, read=4.0, write=2.0, pool=2.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{api_url}/api/cache/flush")
            if resp.status_code == 200:
                print("[Blocky] Flushed DNS response cache successfully.")
                return True
    except Exception as e:
        print(f"[Blocky] Flush cache notice: {e}")
    return False

async def query_diagnostic_api(domain: str, query_type: str = "A"):
    """Runs a query resolution test through Blocky's query API if available."""
    api_url = get_blocky_api_url()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{api_url}/api/query", json={"query": domain, "type": query_type})
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None

DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))


def sync_config_from_db():
    """Generates and writes Blocky's config.yml using current database settings."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Fetch enabled upstreams
    cursor.execute("SELECT endpoint, protocol, last_latency_ms FROM upstreams WHERE enabled = 1 ORDER BY id ASC;")
    upstream_rows = cursor.fetchall()

    # 2. Fetch local DNS mappings (strip wildcard prefixes so Blocky's engine resolves apex and subdomains)
    cursor.execute("SELECT domain, ip_address FROM local_dns WHERE enabled = 1;")
    local_dns_rows = cursor.fetchall()
    custom_dns_mapping = {}
    for row in local_dns_rows:
        dom = row["domain"].strip().lower()
        if dom.startswith("*."):
            dom = dom[2:]
        elif dom.startswith("."):
            dom = dom[1:]
        dom = dom.rstrip(".")
        if dom:
            custom_dns_mapping[dom] = row["ip_address"]

    # 3. Fetch domain-specific routing (conditional upstreams)
    # Strip wildcard prefixes (*.domain.com -> domain.com) so Blocky matches domain and all subdomains
    cursor.execute("SELECT domain_pattern, resolver FROM domain_routing WHERE enabled = 1;")
    routing_rows = cursor.fetchall()
    conditional_mapping = {}
    for row in routing_rows:
        pat = row["domain_pattern"].strip().lower()
        if pat.startswith("*."):
            clean_pat = pat[2:]
        elif pat.startswith("."):
            clean_pat = pat[1:]
        else:
            clean_pat = pat
        clean_pat = clean_pat.rstrip(".")
        if clean_pat:
            conditional_mapping[clean_pat] = row["resolver"]

    # Always ensure local subnet reverse PTR forwarding is included if enabled
    cursor.execute("SELECT value FROM settings WHERE key = 'router_ip';")
    router_row = cursor.fetchone()
    router_ip = router_row["value"].strip() if router_row and router_row["value"].strip() else "192.168.1.1"
    conditional_mapping["168.192.in-addr.arpa"] = router_ip

    # Dynamically derive local reverse in-addr.arpa zones for the configured router subnet
    try:
        parts = router_ip.split(".")
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            p0, p1, p2 = parts[0], parts[1], parts[2]
            if p0 == "10":
                conditional_mapping[f"{p2}.{p1}.10.in-addr.arpa"] = router_ip
                conditional_mapping["10.in-addr.arpa"] = router_ip
            elif p0 == "172" and 16 <= int(p1) <= 31:
                conditional_mapping[f"{p1}.172.in-addr.arpa"] = router_ip
            elif p0 == "192" and p1 == "168":
                conditional_mapping[f"{p2}.168.192.in-addr.arpa"] = router_ip
    except Exception:
        pass

    # 4. Fetch enabled blocklists
    cursor.execute("SELECT url FROM blocklists WHERE enabled = 1;")
    blocklist_rows = cursor.fetchall()
    ads_lists = [row["url"] for row in blocklist_rows] if blocklist_rows else [
        "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts"
    ]

    # 5. Fetch custom rules (whitelists / blacklists)
    cursor.execute("SELECT domain FROM custom_rules WHERE rule_type = 'whitelist' AND enabled = 1;")
    whitelist_rows = cursor.fetchall()
    whitelist_domains = [row["domain"].strip().lower() for row in whitelist_rows if row["domain"].strip()]

    cursor.execute("SELECT domain FROM custom_rules WHERE rule_type = 'blacklist' AND enabled = 1;")
    blacklist_rows = cursor.fetchall()
    blacklist_domains = [row["domain"].strip().lower() for row in blacklist_rows if row["domain"].strip()]

    # 5.5 Fetch enabled blocked services (1-Click App Blocker)
    cursor.execute("SELECT domains_json FROM blocked_services WHERE enabled = 1;")
    service_rows = cursor.fetchall()
    service_domains = []
    for s_row in service_rows:
        try:
            domains = json.loads(s_row["domains_json"])
            for d in domains:
                d_clean = d.strip().lower()
                if d_clean:
                    service_domains.append(d_clean)
        except Exception:
            pass

    all_blacklisted_domains = sorted(list(set(blacklist_domains + service_domains)))
    all_whitelisted_domains = sorted(list(set(whitelist_domains)))

    # Write custom files on disk for Blocky's file-based blocklist ingestion
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    blacklist_file = DATA_DIR / "custom_blacklist.txt"
    whitelist_file = DATA_DIR / "custom_whitelist.txt"

    with open(blacklist_file, "w", encoding="utf-8") as f:
        f.write("# BlockyDNS Active Blacklist & 1-Click Blocked Services\n")
        for d in all_blacklisted_domains:
            # Strip wildcard prefix if present (*.example.com -> example.com)
            clean_d = d[2:] if d.startswith("*.") else d
            f.write(f"{clean_d}\n")

    with open(whitelist_file, "w", encoding="utf-8") as f:
        f.write("# BlockyDNS Active Whitelist\n")
        for d in all_whitelisted_domains:
            clean_d = d[2:] if d.startswith("*.") else d
            f.write(f"{clean_d}\n")

    try:
        os.chmod(str(blacklist_file), 0o666)
        os.chmod(str(whitelist_file), 0o666)
    except Exception:
        pass

    # Source paths for Blocky container
    # Inside docker-compose, blocky-engine container always mounts ./data at /app/data
    blocky_blacklist_source = "/app/data/custom_blacklist.txt"
    blocky_whitelist_source = "/app/data/custom_whitelist.txt"

    # Blacklist sources: external remote lists + local blacklist file
    blacklists_sources = list(ads_lists)
    blacklists_sources.append(blocky_blacklist_source)

    # Whitelist sources: only include whitelist file if custom whitelist domains actually exist
    whitelists_sources = [blocky_whitelist_source] if all_whitelisted_domains else []

    # 6. Fetch retention days, IPv6 blocking & upstream strategy
    cursor.execute("SELECT value FROM settings WHERE key = 'log_retention_days';")
    retention_row = cursor.fetchone()
    retention_days = int(retention_row["value"]) if retention_row else 7

    cursor.execute("SELECT value FROM settings WHERE key = 'log_ptr_queries';")
    ptr_row = cursor.fetchone()
    log_ptr_queries = (ptr_row["value"] == "true") if ptr_row else False

    cursor.execute("SELECT value FROM settings WHERE key = 'block_ipv6';")
    ipv6_row = cursor.fetchone()
    block_ipv6 = (ipv6_row["value"] == "true") if ipv6_row else True

    cursor.execute("SELECT value FROM settings WHERE key = 'upstream_strategy';")
    strat_row = cursor.fetchone()
    upstream_strategy = strat_row["value"] if strat_row else "parallel_best"
    if upstream_strategy not in ["parallel_best", "fastest_first", "strict", "random"]:
        upstream_strategy = "parallel_best"

    # 7. Fetch caching, prefetching & EDNS settings
    cursor.execute("SELECT key, value FROM settings WHERE key IN ('caching_enabled', 'cache_min_ttl', 'cache_max_ttl', 'cache_neg_ttl', 'prefetching_enabled', 'prefetch_threshold', 'edns_anonymize_ecs');")
    cache_settings = {row["key"]: row["value"] for row in cursor.fetchall()}

    conn.close()


    # Determine upstreams ordering & Blocky engine strategy
    if upstream_strategy == "fastest_first":
        # Sort enabled upstreams by lowest measured latency
        sorted_rows = sorted(
            upstream_rows,
            key=lambda r: (r["last_latency_ms"] is None or r["last_latency_ms"] <= 0, r["last_latency_ms"] or 999999)
        )
        upstreams_list = [row["endpoint"] for row in sorted_rows]
        blocky_strategy = "strict"
    elif upstream_strategy == "strict":
        upstreams_list = [row["endpoint"] for row in upstream_rows]
        blocky_strategy = "strict"
    elif upstream_strategy == "random":
        upstreams_list = [row["endpoint"] for row in upstream_rows]
        blocky_strategy = "random"
    else:  # parallel_best
        # Sort by latency so fastest resolvers are weighted favorably
        sorted_rows = sorted(
            upstream_rows,
            key=lambda r: (r["last_latency_ms"] is None or r["last_latency_ms"] <= 0, r["last_latency_ms"] or 999999)
        )
        upstreams_list = [row["endpoint"] for row in sorted_rows]
        blocky_strategy = "parallel_best"

    if not upstreams_list:
        upstreams_list = [
            "https://1.1.1.1/dns-query",
            "tcp-tls:1.1.1.1:853",
            "https://dns.quad9.net/dns-query"
        ]

    # Build config dict
    config_data = {
        "upstreams": {
            "groups": {
                "default": upstreams_list
            },
            "strategy": blocky_strategy,
            "timeout": "2s"
        },
        "bootstrapDns": [
            "1.1.1.1",
            "8.8.8.8"
        ],
        "customDNS": {
            "customTTL": "1h",
            "mapping": custom_dns_mapping
        },
        "conditional": {
            "fallbackUpstream": True,
            "mapping": conditional_mapping
        },
        "blocking": {
            "denylists": {
                "ads": blacklists_sources
            },
            "allowlists": {
                "ads": whitelists_sources
            },
            "clientGroupsBlock": {
                "default": ["ads"]
            },
            "blockType": "zeroIp",
            "loading": {
                "refreshPeriod": "4h",
                "strategy": "fast"
            }
        },
        "queryLog": {
            "type": "sqlite",
            "target": os.getenv("BLOCKY_DB_TARGET", "/app/data/blockydns.db"),
            "logRetentionDays": retention_days,
            "flushInterval": "2s"
        },
        "ports": {
            "dns": 53,
            "http": 4000
        },
        "prometheus": {
            "enable": True,
            "path": "/metrics"
        }
    }

    # Suppress noisy PTR / SUDN reverse DNS queries by default unless explicitly enabled
    if not log_ptr_queries:
        config_data["queryLog"]["ignore"] = {
            "sudn": True,
            "domains": [
                "/.*\\.in-addr\\.arpa$/",
                "/.*\\.ip6\\.arpa$/"
            ]
        }

    # Caching & Prefetching
    caching_enabled = cache_settings.get("caching_enabled", "true") == "true"
    if caching_enabled:
        config_data["caching"] = {
            "minTime": cache_settings.get("cache_min_ttl", "5m"),
            "maxTime": cache_settings.get("cache_max_ttl", "30m"),
            "cacheTimeNegative": cache_settings.get("cache_neg_ttl", "30m"),
            "prefetching": cache_settings.get("prefetching_enabled", "true") == "true",
            "prefetchThreshold": int(cache_settings.get("prefetch_threshold", "3")),
            "prefetchExpires": "2h",
            "prefetchMaxItemsCount": 1000
        }

    # ECS (EDNS Client Subnet) & Privacy
    anonymize_ecs = cache_settings.get("edns_anonymize_ecs", "true") == "true"
    config_data["ecs"] = {
        "useAsClient": False,
        "forward": not anonymize_ecs
    }

    # DNSSEC Validation
    dnssec_val = cache_settings.get("dnssec_enabled", "true") == "true"
    if dnssec_val:
        config_data["dnssec"] = {
            "validate": True
        }

    if block_ipv6:
        config_data["connectIPVersion"] = "v4"
        config_data["filtering"] = {
            "queryTypes": ["AAAA"]
        }


    config_path = get_blocky_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
    try:
        os.chmod(str(config_path), 0o666)
        os.chmod(str(config_path.parent), 0o777)
    except Exception:
        pass
    print(f"[Blocky] Synced active config to {config_path}")
    return True



_restart_task = None

def schedule_blocky_restart(delay_seconds: float = 0.5):
    """Debounces rapid configuration updates and restarts blocky in the background without blocking the UI."""
    global _restart_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        if _restart_task and not _restart_task.done():
            _restart_task.cancel()

        async def _delayed_restart():
            try:
                await asyncio.sleep(delay_seconds)
                await restart_blocky_container()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"[Blocky] Restart error: {e}")

        _restart_task = loop.create_task(_delayed_restart())

async def restart_blocky_container():
    """Attempts to restart blocky-engine container via Docker socket if mounted."""
    docker_sock = Path("/var/run/docker.sock")
    if not docker_sock.exists():
        return {"restarted": False, "reason": "Docker socket /var/run/docker.sock not mounted"}
    try:
        transport = httpx.AsyncHTTPTransport(uds=str(docker_sock))
        async with httpx.AsyncClient(transport=transport, timeout=10.0) as client:
            # Pass ?t=1 so Docker shuts down Blocky in 1s rather than waiting for 10s default stop timeout
            resp = await client.post("http://localhost/containers/blocky-engine/restart?t=1")
            if resp.status_code in [200, 204]:
                print("[Blocky] Fast-restarted blocky-engine container via Docker socket.")
                return {"restarted": True, "status": "restarted", "container": "blocky-engine"}

            # Fallback: query containers if renamed or default compose naming used
            if resp.status_code == 404:
                list_resp = await client.get("http://localhost/containers/json")
                if list_resp.status_code == 200:
                    containers = list_resp.json()
                    for c in containers:
                        names = c.get("Names", [])
                        for n in names:
                            clean_n = n.lstrip("/")
                            if "blocky" in clean_n and "hub" not in clean_n:
                                retry_resp = await client.post(f"http://localhost/containers/{clean_n}/restart?t=1")
                                if retry_resp.status_code in [200, 204]:
                                    print(f"[Blocky] Fast-restarted {clean_n} via Docker socket.")
                                    return {"restarted": True, "status": "restarted", "container": clean_n}

            return {"restarted": False, "status": f"HTTP {resp.status_code}", "body": resp.text}
    except Exception as e:
        print(f"[Blocky] Docker socket restart notice: {e}")
        return {"restarted": False, "error": str(e)}
