import socket
import threading
from database import get_connection

# Cache to avoid hammering router PTR queries
RESOLVED_CACHE = {}

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
        RESOLVED_CACHE.pop(ip, None)
    elif ip in RESOLVED_CACHE:
        return

    def worker():
        hostname = None
        # 1. Try querying router's DNS server directly for DHCP hostname if router_ip is configured
        try:
            conn_set = get_connection()
            c_set = conn_set.cursor()
            c_set.execute("SELECT value FROM settings WHERE key = 'router_ip';")
            r_row = c_set.fetchone()
            router_ip = r_row["value"].strip() if r_row and r_row["value"].strip() else None
            conn_set.close()

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

        # 2. Fallback to OS socket reverse lookup if router lookup was unsuccessful
        if not hostname:
            try:
                host_info = socket.gethostbyaddr(ip)
                if host_info and host_info[0]:
                    hostname = host_info[0].split(".")[0]
            except Exception:
                hostname = None

        if hostname:
            RESOLVED_CACHE[ip] = hostname

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
        conn.close()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

def get_friendly_name_for_ip(ip: str, conn=None) -> str:
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    cursor = conn.cursor()
    cursor.execute("SELECT friendly_name, hostname FROM devices WHERE client_ip = ?;", (ip,))
    row = cursor.fetchone()
    if close_after:
        conn.close()

    if row:
        if row["friendly_name"] and row["friendly_name"].strip():
            return row["friendly_name"]
        if row["hostname"] and row["hostname"].strip():
            return row["hostname"]
    return ip
