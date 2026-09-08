import ipaddress
import re
import urllib.parse
from typing import Tuple, Optional
from benchmark import benchmark_single_doh, benchmark_single_dot, benchmark_single_udp

def normalize_resolver(endpoint: str, protocol: Optional[str] = None) -> Tuple[str, str]:
    """
    Intelligently auto-detects and normalizes any user-provided resolver input
    into Blocky's required syntax.
    
    Returns: (normalized_endpoint, protocol)
      where protocol is one of: 'doh', 'dot', 'udp'
    """
    ep = (endpoint or "").strip().strip("'\"")
    proto = (protocol or "").lower().strip() if protocol else ""

    if not ep:
        return "", "udp"

    # 1. Explicit TLS / DoT scheme prefixes
    if ep.startswith("tls://") or ep.startswith("dot://"):
        host_part = ep.split("://", 1)[1].rstrip("/")
        if ":" not in host_part:
            host_part = f"{host_part}:853"
        return f"tcp-tls:{host_part}", "dot"

    if ep.startswith("tcp-tls:"):
        host_part = ep[len("tcp-tls:"):].rstrip("/")
        if ":" not in host_part:
            host_part = f"{host_part}:853"
        return f"tcp-tls:{host_part}", "dot"

    # 2. Explicit UDP scheme prefixes
    if ep.startswith("udp://"):
        return ep[len("udp://"):].rstrip("/"), "udp"
    if ep.startswith("udp:"):
        return ep[len("udp:"):].rstrip("/"), "udp"

    # 3. Extract hostname to inspect characteristics
    clean_host = ep.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0].strip()

    # Check if host or port explicitly indicates DoT
    has_port_853 = ":853" in ep
    has_dot_in_host = (
        ".dot." in clean_host.lower() or 
        clean_host.lower().startswith("dot.") or
        clean_host.lower().endswith(".dot")
    )

    # If explicitly marked as DoT, or has port 853, or hostname is clearly a DoT endpoint (e.g. common.dot.dns.yandex.net)
    if proto == "dot" or has_port_853 or has_dot_in_host:
        port = "853"
        raw_netloc = ep.replace("https://", "").replace("http://", "").split("/")[0]
        if ":" in raw_netloc:
            p = raw_netloc.split(":")[1].strip()
            if p.isdigit():
                port = p
        return f"tcp-tls:{clean_host}:{port}", "dot"

    # 4. Check if endpoint is an IP address
    is_ip = False
    try:
        ipaddress.ip_address(clean_host)
        is_ip = True
    except ValueError:
        pass

    if is_ip:
        # If user explicitly requested DoH or used https:// with an IP
        if proto == "doh" or ep.startswith("https://") or ep.startswith("http://"):
            if not ep.startswith("https://") and not ep.startswith("http://"):
                ep = f"https://{ep}/dns-query"
            elif "/" not in ep.replace("https://", "").replace("http://", ""):
                ep = f"{ep}/dns-query"
            return ep, "doh"

        # If port 853 was given with an IP
        if ":" in ep:
            p = ep.split(":")[1].split("/")[0].strip()
            if p == "853":
                return f"tcp-tls:{clean_host}:853", "dot"
            return ep, "udp"

        # Default IP is standard UDP port 53
        return ep, "udp"

    # 5. HTTPS / HTTP URLs or explicitly selected DoH
    if ep.startswith("https://") or ep.startswith("http://") or proto == "doh":
        if not ep.startswith("https://") and not ep.startswith("http://"):
            ep = f"https://{ep}"
        
        # Ensure path exists for Blocky DoH engine
        path_part = ep.replace("https://", "").replace("http://", "")
        if "/" not in path_part:
            ep = f"{ep}/dns-query"
        return ep, "doh"

    # 6. Fallback for bare hostnames (e.g. dns.google, dns.quad9.net)
    if proto == "udp":
        return ep, "udp"

    # Default naked hostnames to DoH with /dns-query path
    return f"https://{ep}/dns-query", "doh"


async def probe_and_normalize_resolver(endpoint: str, protocol: Optional[str] = None) -> dict:
    """
    Normalizes the endpoint and performs a rapid async verification probe.
    If the initial protocol fails (e.g. port 443 refused on a DoT server),
    it probes alternative protocols and auto-switches to the working one.
    """
    normalized, detected_proto = normalize_resolver(endpoint, protocol)
    clean_host = normalized.replace("https://", "").replace("http://", "").replace("tcp-tls:", "").split("/")[0].split(":")[0]

    result = {
        "original_input": endpoint,
        "endpoint": normalized,
        "protocol": detected_proto,
        "latency_ms": None,
        "status": "untested",
        "auto_switched": False
    }

    # 1. Probe detected protocol
    try:
        if detected_proto == "doh":
            bench = await benchmark_single_doh(normalized)
            if bench.get("latency_ms"):
                result["latency_ms"] = bench["latency_ms"]
                result["status"] = "online"
                return result
            
            # If DoH failed, test if it's a DoT server (TLS on 853)
            dot_candidate = f"tcp-tls:{clean_host}:853"
            dot_bench = await benchmark_single_dot(dot_candidate)
            if dot_bench.get("latency_ms"):
                result["endpoint"] = dot_candidate
                result["protocol"] = "dot"
                result["latency_ms"] = dot_bench["latency_ms"]
                result["status"] = "online"
                result["auto_switched"] = True
                return result

        elif detected_proto == "dot":
            bench = await benchmark_single_dot(normalized)
            if bench.get("latency_ms"):
                result["latency_ms"] = bench["latency_ms"]
                result["status"] = "online"
                return result

            # If DoT failed, test if DoH is available on port 443
            doh_candidate = f"https://{clean_host}/dns-query"
            doh_bench = await benchmark_single_doh(doh_candidate)
            if doh_bench.get("latency_ms"):
                result["endpoint"] = doh_candidate
                result["protocol"] = "doh"
                result["latency_ms"] = doh_bench["latency_ms"]
                result["status"] = "online"
                result["auto_switched"] = True
                return result

        elif detected_proto == "udp":
            bench = await benchmark_single_udp(normalized)
            if bench.get("latency_ms"):
                result["latency_ms"] = bench["latency_ms"]
                result["status"] = "online"
                return result

    except Exception:
        pass

    result["status"] = "offline_or_unreachable"
    return result
