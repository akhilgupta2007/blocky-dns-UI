import time
import base64
import ssl
import asyncio
import httpx
import dns.message
import dns.query

DEFAULT_CANDIDATES = [
    {"name": "Cloudflare DoH", "endpoint": "https://1.1.1.1/dns-query", "protocol": "doh", "enabled": 1, "is_custom": 0},
    {"name": "Cloudflare Security DoH", "endpoint": "https://security.cloudflare-dns.com/dns-query", "protocol": "doh", "enabled": 1, "is_custom": 0},
    {"name": "Google Public DoH", "endpoint": "https://dns.google/dns-query", "protocol": "doh", "enabled": 1, "is_custom": 0},
    {"name": "Quad9 Secure DoH", "endpoint": "https://dns.quad9.net/dns-query", "protocol": "doh", "enabled": 1, "is_custom": 0},
    {"name": "AdGuard Public DoH", "endpoint": "https://dns.adguard-dns.com/dns-query", "protocol": "doh", "enabled": 0, "is_custom": 0},
    {"name": "Cloudflare DoT", "endpoint": "tcp-tls:1.1.1.1:853", "protocol": "dot", "enabled": 1, "is_custom": 0},
    {"name": "Quad9 DoT", "endpoint": "tcp-tls:9.9.9.9:853", "protocol": "dot", "enabled": 0, "is_custom": 0},
]

# SSL Context for DoT benchmark lookups
DOT_SSL_CTX = ssl.create_default_context()
DOT_SSL_CTX.check_hostname = False
DOT_SSL_CTX.verify_mode = ssl.CERT_NONE

async def benchmark_single_udp(endpoint: str, domain: str = "wikipedia.org") -> dict:
    """Measures latency of standard unencrypted DNS over UDP (port 53)."""
    start = time.perf_counter()
    try:
        clean = endpoint.replace("udp:", "").replace("udp+", "").strip()
        parts = clean.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 53

        q = dns.message.make_query(domain, "A")
        await asyncio.to_thread(
            dns.query.udp,
            q,
            host,
            port=port,
            timeout=3.0
        )
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        return {"latency_ms": elapsed_ms, "status": "online"}
    except Exception as e:
        return {"latency_ms": None, "status": f"Error: {type(e).__name__}"}

async def benchmark_single_doh(endpoint: str, domain: str = "wikipedia.org", client: httpx.AsyncClient = None) -> dict:
    start = time.perf_counter()
    q = dns.message.make_query(domain, "A")
    wire = q.to_wire()
    b64_wire = base64.urlsafe_b64encode(wire).decode("ascii").rstrip("=")

    # Normalize endpoint URL
    clean_endpoint = endpoint.strip()
    if not clean_endpoint.startswith("http://") and not clean_endpoint.startswith("https://"):
        clean_endpoint = f"https://{clean_endpoint}"
    if "/" not in clean_endpoint.replace("https://", "").replace("http://", ""):
        clean_endpoint = f"{clean_endpoint}/dns-query"

    close_client = False
    if client is None:
        try:
            # Quad9 and modern DoH servers strictly require HTTP/2 (RFC 8484 § 5.2)
            client = httpx.AsyncClient(http2=True, timeout=4.0, verify=False)
        except Exception:
            client = httpx.AsyncClient(timeout=4.0, verify=False)
        close_client = True
    try:
        # 1. Standard RFC 8484 GET with ?dns= (Primary RFC method over HTTP/2)
        try:
            url = f"{clean_endpoint}?dns={b64_wire}"
            get_headers = {"Accept": "application/dns-message", "User-Agent": "BlockyDNS-Hub/1.0"}
            resp = await client.get(url, headers=get_headers)
            if resp.status_code == 200:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
                return {"latency_ms": elapsed_ms, "status": "online"}
            elif resp.status_code == 505:
                # Upstream strictly demands HTTP/2 (e.g. Quad9)
                try:
                    async with httpx.AsyncClient(http2=True, timeout=4.0, verify=False) as h2_client:
                        h2_resp = await h2_client.get(url, headers=get_headers)
                        if h2_resp.status_code == 200:
                            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
                            return {"latency_ms": elapsed_ms, "status": "online"}
                except Exception:
                    pass
        except Exception:
            pass

        # 2. RFC 8484 POST with binary wire payload
        try:
            post_headers = {
                "Content-Type": "application/dns-message",
                "Accept": "application/dns-message",
                "User-Agent": "BlockyDNS-Hub/1.0"
            }
            resp = await client.post(clean_endpoint, content=wire, headers=post_headers)
            if resp.status_code == 200:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
                return {"latency_ms": elapsed_ms, "status": "online"}
            elif resp.status_code == 505:
                try:
                    async with httpx.AsyncClient(http2=True, timeout=4.0, verify=False) as h2_client:
                        h2_resp = await h2_client.post(clean_endpoint, content=wire, headers=post_headers)
                        if h2_resp.status_code == 200:
                            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
                            return {"latency_ms": elapsed_ms, "status": "online"}
                except Exception:
                    pass
        except Exception:
            pass

        # 3. JSON DoH fallback
        try:
            json_url = clean_endpoint.replace("/dns-query", "/resolve") if "dns.google" in clean_endpoint else clean_endpoint
            resp = await client.get(
                f"{json_url}?name={domain}&type=A",
                headers={"Accept": "application/dns-json", "User-Agent": "BlockyDNS-Hub/1.0"}
            )
            if resp.status_code == 200:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
                return {"latency_ms": elapsed_ms, "status": "online"}
            return {"latency_ms": None, "status": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"latency_ms": None, "status": f"Error: {type(e).__name__}"}

    finally:
        if close_client:
            await client.aclose()


async def benchmark_single_dot(endpoint: str, domain: str = "wikipedia.org") -> dict:
    start = time.perf_counter()
    try:
        clean = endpoint.replace("tcp-tls:", "").strip()
        parts = clean.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 853

        q = dns.message.make_query(domain, "A")
        await asyncio.to_thread(
            dns.query.tls,
            q,
            host,
            port=port,
            timeout=3.0,
            ssl_context=DOT_SSL_CTX,
            server_hostname=host
        )
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        return {"latency_ms": elapsed_ms, "status": "online"}
    except Exception as e:
        return {"latency_ms": None, "status": f"Error: {type(e).__name__}"}


async def run_upstream_benchmark(test_domain: str = "wikipedia.org") -> list:
    """Benchmarks all upstream resolvers concurrently and returns status and latency."""
    candidates = []
    try:
        try:
            from database import get_connection
        except ImportError:
            from server.database import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, endpoint, protocol, enabled, is_custom FROM upstreams ORDER BY enabled DESC, id ASC;")
        db_rows = cursor.fetchall()
        conn.close()
        candidates = [dict(r) for r in db_rows]
    except Exception as e:
        print(f"[Benchmark] Warning loading upstreams from database: {e}")

    # Fallback to defaults if database returned no upstreams
    if not candidates:
        candidates = list(DEFAULT_CANDIDATES)

    # 2. Run concurrent benchmark queries with HTTP/2 enabled
    try:
        shared_client = httpx.AsyncClient(http2=True, timeout=4.0, verify=False)
    except Exception:
        shared_client = httpx.AsyncClient(timeout=4.0, verify=False)

    async with shared_client as client:
        tasks = []
        for c in candidates:
            proto = c.get("protocol", "doh").lower()
            endpoint = c.get("endpoint", "")
            if proto == "doh":
                tasks.append(benchmark_single_doh(endpoint, test_domain, client))
            elif proto == "dot":
                tasks.append(benchmark_single_dot(endpoint, test_domain))
            elif proto == "udp":
                tasks.append(benchmark_single_udp(endpoint, test_domain))
            else:
                # Fallback check: if endpoint starts with tcp-tls, treat as dot; if http, doh; else udp
                if endpoint.startswith("tcp-tls:"):
                    tasks.append(benchmark_single_dot(endpoint, test_domain))
                elif endpoint.startswith("http://") or endpoint.startswith("https://"):
                    tasks.append(benchmark_single_doh(endpoint, test_domain, client))
                else:
                    tasks.append(benchmark_single_udp(endpoint, test_domain))

        raw_results = await asyncio.gather(*tasks)

    # 3. Format and attach results
    results = []
    for c, res in zip(candidates, raw_results):
        results.append({
            "id": c.get("id"),
            "name": c["name"],
            "endpoint": c["endpoint"],
            "protocol": c.get("protocol", "doh"),
            "enabled": bool(c.get("enabled", 1)),
            "is_custom": bool(c.get("is_custom", 0)),
            "latency_ms": res.get("latency_ms"),
            "status": res.get("status"),
            "is_best": False
        })

    # Identify the fastest upstream
    online = [r for r in results if r["latency_ms"] is not None]
    if online:
        fastest = min(online, key=lambda x: x["latency_ms"])
        fastest["is_best"] = True

    results.sort(key=lambda x: (x["latency_ms"] is None, x["latency_ms"] or 999999))
    return results

async def execute_periodic_benchmark():
    """Runs latency benchmark in the background, updates DB, and syncs engine if fastest_first is active."""
    try:
        import datetime
        try:
            from database import get_connection
        except ImportError:
            from server.database import get_connection
        try:
            from blocky_client import sync_config_from_db, restart_blocky_container
        except ImportError:
            from server.blocky_client import sync_config_from_db, restart_blocky_container

        print("[Auto-Benchmark] Running scheduled daily latency benchmark...")
        results = await run_upstream_benchmark()

        conn = get_connection()
        cursor = conn.cursor()
        for r in results:
            if r.get("latency_ms") is not None:
                cursor.execute("UPDATE upstreams SET last_latency_ms = ? WHERE endpoint = ?;", (r["latency_ms"], r["endpoint"]))

        now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_benchmark_timestamp', ?);", (now_iso,))

        cursor.execute("SELECT value FROM settings WHERE key = 'upstream_strategy';")
        strat_row = cursor.fetchone()
        strat = strat_row["value"] if strat_row else "parallel_best"

        conn.commit()
        conn.close()

        # If fastest_first strategy is active, update Blocky's config with new fastest resolver at #1
        if strat == "fastest_first":
            sync_config_from_db()
            await restart_blocky_container()

        print(f"[Auto-Benchmark] Completed daily run. Tested {len(results)} upstreams at {now_iso}.")
        return results
    except Exception as e:
        print(f"[Auto-Benchmark Error]: {e}")
        return []

def start_benchmark_scheduler():
    """Starts background worker thread that executes the upstream benchmark periodically (default 24h)."""
    import threading

    def background_loop():
        import asyncio
        # Initial warm-up delay before first auto-benchmark (45s after boot)
        time.sleep(45)
        while True:
            try:
                try:
                    from database import get_connection
                except ImportError:
                    from server.database import get_connection

                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM settings WHERE key = 'auto_benchmark_interval';")
                row = cursor.fetchone()
                interval_hours = int(row["value"]) if row and row["value"].isdigit() else 24
                conn.close()

                if interval_hours > 0:
                    asyncio.run(execute_periodic_benchmark())
                    sleep_seconds = interval_hours * 3600
                else:
                    sleep_seconds = 3600 # Check again in 1 hour if disabled
            except Exception as e:
                print(f"[Benchmark Scheduler Warning]: {e}")
                sleep_seconds = 3600

            time.sleep(sleep_seconds)

    thread = threading.Thread(target=background_loop, daemon=True, name="AutoBenchmarkScheduler")
    thread.start()
    print("[Server] Started periodic upstream speed latency benchmark scheduler (Daily / 24h).")
