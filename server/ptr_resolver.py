import socket
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from database import get_connection

# Bounded LRU cache to avoid memory leaks and router query hammering
_CACHE_MAX_SIZE = 2000
_CACHE_TTL_SECONDS = 86400  # 24 hours
_cache_lock = threading.Lock()
_RESOLVED_CACHE = OrderedDict()

# Dedicated bounded thread pool for async PTR lookups
_ptr_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ptr_resolver")

def _get_cached_ptr(ip: str):
    with _cache_lock:
        if ip in _RESOLVED_CACHE:
            hostname, ts = _RESOLVED_CACHE[ip]
            if time.time() - ts < _CACHE_TTL_SECONDS:
                _RESOLVED_CACHE.move_to_end(ip)
                return hostname
            else:
                del _RESOLVED_CACHE[ip]
    return None

def _set_cached_ptr(ip: str, hostname: str):
    with _cache_lock:
        if ip in _RESOLVED_CACHE:
            _RESOLVED_CACHE.move_to_end(ip)
        _RESOLVED_CACHE[ip] = (hostname, time.time())
        if len(_RESOLVED_CACHE) > _CACHE_MAX_SIZE:
            _RESOLVED_CACHE.popitem(last=False)

def determine_device_icon(name_or_ip: str) -> str:
    lower = name_or_ip.lower()
    if any(k in lower for k in ["tv", "roku", "chromecast", "appletv", "firetv", "bravia"]):
        return "tv"
    if any(k in lower for k in ["macbook", "laptop", "thinkpad", "desktop", "pc", "windows"]):
        return "laptop"
    if any(k in lower for k in ["iphone", "android", "galaxy", "pixel", "phone", "mobile"]):
        return "phone"
    if any(k in lower for k in ["ipad", "tablet"]):
        return "tablet"
    if any(k in lower for k in ["nas", "synology", "truenas", "qnap", "server"]):
        return "server"
    if any(k in lower for k in ["esp", "iot", "bulb", "switch", "sonoff", "tasmota", "plug"]):
        return "iot"
    if any(k in lower for k in ["printer", "canon", "epson", "hp"]):
        return "printer"
    return "device"

def resolve_ptr_async(ip: str, force: bool = False):
    if force:
        with _cache_lock:
            _RESOLVED_CACHE.pop(ip, None)
    elif _get_cached_ptr(ip) is not None:
        return

    def worker():
        hostname = None
        # 1. Try querying router's DNS server directly for DHCP hostname if router_ip is configured
        conn_set = None
        try:
            conn_set = get_connection()
            c_set = conn_set.cursor()
            c_set.execute("SELECT value FROM settings WHERE key = 'router_ip';")
            r_row = c_set.fetchone()
            router_ip = r_row["value"].strip() if r_row and r_row["value"].strip() else None

            if router_ip:
                import dns.resolver
                import dns.reversename
                rev_name = dns.reversename.from_address(ip)
                res = dns.resolver.Resolver()
                res.nameservers = [router_ip]
                res.timeout = 1.5
                res.lifetime = 1.5
                answers = res.resolve(rev_name, "PTR")
                for rdata in answers:
                    val = str(rdata.target).rstrip(".")
                    if val:
                        hostname = val.split(".")[0]
                        break
        except Exception:
            hostname = None
        finally:
            if conn_set:
                try:
                    conn_set.close()
                except Exception:
                    pass

        # 2. Fallback to OS socket reverse lookup if router lookup was unsuccessful
        if not hostname:
            try:
                host_info = socket.gethostbyaddr(ip)
                if host_info and host_info[0]:
                    hostname = host_info[0].split(".")[0]
            except Exception:
                hostname = None

        if hostname:
            _set_cached_ptr(ip, hostname)

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT friendly_name, icon FROM devices WHERE client_ip = ?;", (ip,))
            existing = cursor.fetchone()

            icon = determine_device_icon(hostname or ip)
            if existing:
                # Only update hostname if not manually customized
                if not existing["friendly_name"] and hostname:
                    cursor.execute("UPDATE devices SET hostname = ?, icon = ? WHERE client_ip = ?;", (hostname, icon, ip))
            else:
                cursor.execute("""
                INSERT OR IGNORE INTO devices (client_ip, hostname, friendly_name, icon, total_queries, blocked_queries)
                VALUES (?, ?, ?, ?, 1, 0);
                """, (ip, hostname or ip, hostname, icon))

            conn.commit()
        except Exception:
            pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    try:
        _ptr_executor.submit(worker)
    except Exception:
        pass

