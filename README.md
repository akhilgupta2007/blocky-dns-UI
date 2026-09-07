# 🛡️ BlockyDNS Hub

> **High-Performance, Privacy-First Homelab DNS Appliance & Next-Gen Management Dashboard**  
> Powered by the ultra-fast Go DNS engine (**Blocky**) and an end-to-end encrypted management portal.

[![Docker](https://img.shields.io/badge/Docker-Multi--Arch%20(ARMv7%20%7C%20ARM64%20%7C%20AMD64)-blue?logo=docker)](docker-compose.yml)
[![DNS Engine](https://img.shields.io/badge/DNS%20Engine-Blocky%20(Go)-00ADD8?logo=go)](https://github.com/0xERR0R/blocky)
[![Security](https://img.shields.io/badge/Security-TLS%201.3%20%2B%20Strict%20DoH%2FDoT-00f5d4)](#-security--anti-sniffing-shield)
[![RAM Footprint](https://img.shields.io/badge/Total%20RAM-%7E118%20MB-purple)](#-performance-benchmarks-raspberry-pi-1gb-ram)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📖 What is BlockyDNS Hub?

**BlockyDNS Hub** is a self-hosted, full-featured DNS ad-blocker and network management suite. It decouples core DNS packet processing from the management web interface, pairing the blazing-fast **Blocky Go engine** (`0xERR0R/blocky`) with an asynchronous **FastAPI/SQLite Hub** wrapped in a modern, dark glassmorphic dashboard.

Engineered specifically to deliver enterprise-grade performance on single-board computers (like **Raspberry Pi 2/3/4/5, Pi Zero 2W, or mini-PCs**), BlockyDNS Hub delivers sub-millisecond query responses, native DoH/DoT encryption, live threat telemetry, domain-specific geo-bypass routing, and seamless AdGuard/ABP rule compatibility.

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="BlockyDNS Hub Modern Cyberpunk Dashboard" width="92%" style="border-radius: 8px;">
</p>

---

## 📸 Visual Tour & Screenshots

| Modern Dark Cyberpunk Dashboard | Live Query Log & Threat Telemetry |
| :---: | :---: |
| <img src="docs/screenshots/dashboard.png" width="100%" alt="Dashboard"> | <img src="docs/screenshots/query-log.png" width="100%" alt="Query Log"> |
| **Domain Geo-Bypass & Latency Routing** | **AdGuard / ABP Custom Rules Engine** |
| <img src="docs/screenshots/domain-routing.png" width="100%" alt="Domain Routing"> | <img src="docs/screenshots/rules-management.png" width="100%" alt="Rules Management"> |
| **Homelab Local DNS & Reverse Records** | **1-Click Deep WHOIS & Threat Intel** |
| <img src="docs/screenshots/local-dns.png" width="100%" alt="Local DNS"> | <img src="docs/screenshots/whois-threat-telemetry.png" width="100%" alt="WHOIS Intel"> |

---

## ⚖️ How Does It Compare to AdGuard Home & Pi-hole?

Most homelab setups rely on either **Pi-hole** or **AdGuard Home**. BlockyDNS was engineered to eliminate the fundamental architectural compromises present in both:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        BLOCKYDNS DECOUPLED STACK                       │
├──────────────────────────────────┬─────────────────────────────────────┤
│   [ blocky-engine (Pure Go) ]    │      [ blockydns-hub (FastAPI) ]    │
│   • Answers UDP/TCP/DoH/DoT      │      • Web Portal (TLS 1.3)         │
│   • In-Memory Optimistic Cache   │      • Real-time Query SSE Stream   │
│   • Parallel Upstream Racing     │      • WHOIS & Ghostery Intelligence│
│   • Zero downtime during restarts│      • SQLite WAL Storage & Pruning │
└──────────────────────────────────┴─────────────────────────────────────┘
```

### Feature & Architecture Comparison Matrix

| Capability | **BlockyDNS Hub** (Our Setup) | **AdGuard Home** | **Pi-hole (FTL)** |
| :--- | :--- | :--- | :--- |
| **Core Architecture** | **Decoupled 2-Container Microservice** | Monolithic (DNS + Web in 1 binary) | Multi-component (FTL + PHP + Lighttpd) |
| **Fault Isolation** | ✅ **100% Isolated**: DNS engine never drops queries when updating or restarting the Web UI | ❌ If the Web UI crashes or restarts, **all DNS in your house goes down** | ❌ Web and FTL tightly coupled through local sockets |
| **Encrypted Upstreams** | ✅ **Native DoH (HTTP/2), DoT** out of the box | ✅ Native DoH, DoT, DoQ | ❌ **No native DoH/DoT** (Requires extra sidecars like `cloudflared` or `unbound`) |
| **Upstream Racing Strategy** | ✅ **Parallel Best** (Races all upstreams simultaneously for lowest latency) | Parallel race / Load balancing | Basic fastest / Random |
| **Caching Engine** | ✅ **Optimistic Prefetching**: Serves cache in < 1ms, refreshes in background | Optimistic cache | Standard `dnsmasq` TTL cache |
| **RAM Footprint** | **~118 MB total** (~60 MB engine + ~58 MB hub) | ~90 – 160 MB | ~100 – 180 MB |
| **CPU Overhead** | **< 0.6%** on Raspberry Pi | < 1% | < 1% |
| **Query Intelligence** | ✅ **1-Click WHOIS, VirusTotal & Ghostery WhoTracks.Me** tracker breakdown | Basic IP / Client tag | Basic IP / Client tag |
| **AdGuard / ABP Syntax** | ✅ **Built-in Auto-Parser** (Converts `@@||domain^` and `||domain^` automatically) | Native ABP syntax | ❌ Plain hosts & regex only (No ABP syntax) |
| **1-Click App Blocker** | ✅ **20 Pre-Compiled Categories** (Social Media, Adult, Gaming, Streaming) | Blocked services toggle | ❌ None (Requires manual regex/domain lists) |
| **Domain Geo-Bypass Routing**| ✅ **Visual Routing Catalog + Speed Presets** (Mullvad, Quad9, SmartDNS) | Text-file config syntax (`[/domain/]upstream`) | Manual `dnsmasq` config file edits |
| **Dashboard Security** | ✅ **End-to-End TLS 1.3** + Auto-generated LAN SAN Certs + Rebinding Shield | Optional HTTPS (manual certs) | Plain HTTP port 80 by default |

---

## 🌟 Comprehensive Features

### 🚀 1. DNS Engine & Performance
* **Parallel Best Upstream Racing**: Dispatches requests across all active resolvers in parallel and returns the single fastest response to the client.
* **Optimistic Caching & Prefetching**: Immediately serves expiring records in < 1ms while asynchronously re-querying the upstream in the background.
* **RFC 8484 HTTP/2 DNS-over-HTTPS (DoH)**: Native multiplexed encrypted DNS over HTTPS with automatic protocol negotiation and zero HTTP 505 version errors.
* **DNS-over-TLS (DoT)**: Secure encrypted DNS over port 853 with strict certificate validation.
* **Strict Encrypted DNS Mode**: Prohibits unencrypted UDP port 53 upstream resolvers, eliminating ISP DNS snooping.
* **IPv6 (AAAA) Shield & RFC 9460 Stripping**: Drops AAAA queries with empty responses to prevent ISP IPv6 bypass leaks, and automatically strips `ipv6hint` from `HTTPS` and `SVCB` records.
* **EDNS Client Subnet (ECS) Stripping**: Automatically removes client IP addresses from upstream forwarding to preserve ISP-level anonymity.
* **DNS Rebinding Shield**: Blocks public WAN responses that resolve to private RFC-1918 LAN IP ranges.

### 🛡️ 2. Ad-Blocking, App Blocking & Custom Rules
* **Curated Blocklist Catalog**: 1-click toggles for verified upstream lists:
  * *StevenBlack Unified* (Adware & Malware)
  * *OISD Anti-Tracking*
  * *HaGeZi Multi PRO Threat Intelligence*
  * *Smart TV Telemetry Blocklist* (Samsung, LG, Roku, FireTV tracking)
* **1-Click Blocked Services (20 Categories)**: Instantly block popular apps and platforms across the household with pre-compiled domain lists:
  * **Social Media**: TikTok, Facebook, Instagram, Twitter/X, Snapchat, Reddit, Pinterest, LinkedIn.
  * **Video & Streaming**: YouTube, Netflix, Twitch, Disney+, Amazon Prime.
  * **Gaming**: Steam, Roblox, Discord, Epic Games, PlayStation Network.
  * **Adult & Gambling**: Pornographic networks, online casinos & gambling endpoints.
* **AdGuard / ABP Bulk Importer**:
  * Directly import rules in standard AdGuard format (e.g. `@@||domain.com^$important` for Whitelist and `||domain.com^` for Blacklist).
  * Automatically categorizes, strips syntax markers, and compiles them directly into native Blocky engine text files.
* **Structured Custom Rules List**: View rules in a clean, searchable table with domain badges, scopes (Exact / Wildcard / Regex), and instant search filtering.

### 🔍 3. Live Query Log & Threat Intelligence
* **Real-time Server-Sent Events (SSE)**: Live, non-polling stream of DNS requests as they occur.
* **Resolved IP Address Display**: Inspect exact IP addresses returned by upstream resolvers directly in the log.
* **1-Click Domain Intelligence**:
  * **🌐 WHOIS Lookup**: Registrar, registration date, organization, and IP routing blocks.
  * **🛡️ VirusTotal Integration**: 1-click sandbox score inspection for suspicious domains.
  * **👻 Ghostery WhoTracks.Me**: Inspect tracking behavior, advertising profiles, and privacy risk scores.
* **Fast Whitelist / Blacklist Actions**: 1-click allow or block buttons on every row with immediate cache flushing.

### 🌍 4. Domain-Specific Geo-Bypass Routing
* Route specific domains to dedicated international upstreams (e.g., `*.bbc.co.uk -> Mullvad UK DoH` or Swiss financial sites through `Quad9 Swiss DoH`) while keeping standard home queries on local low-latency resolvers.
* **Interactive Resolver Catalog**: View, toggle, benchmark, and bind any configured or custom DNS resolver to a routing rule with one click.

### 🏠 5. Homelab Power Tools
* **Live Upstream Latency Benchmark**: Tests round-trip latency across all configured and custom DNS providers with visual performance bars.
* **Auto-Sort by Speed**: Re-orders upstream resolvers in the database by lowest measured latency.
* **Wildcard Local DNS**: Resolve patterns like `*.homelab.lan -> 192.168.1.200` to easily route internal services through reverse proxies (Traefik, Nginx, Caddy).
* **Reverse PTR Device Discovery**: Automatically queries your router's DHCP server for friendly client hostnames, with custom nickname and icon assignments.
* **Teleporter (Backup & Restore)**: Export your complete setup (rules, upstreams, local DNS, custom routes) as portable JSON.

---

## 📊 Performance Benchmarks (Raspberry Pi, 1GB RAM)

Actual running statistics taken from `docker stats` under active network load:

```
CONTAINER ID   NAME             CPU %     MEM USAGE / LIMIT     MEM %     NET I/O
5fdb3b341083   blocky-engine    0.16%     59.88MiB / 955MiB     6.27%     4.74MB / 217kB
a9faa71fd06e   blockydns-hub    0.43%     58.57MiB / 955MiB     6.13%     863kB / 1.47MB
──────────────────────────────────────────────────────────────────────────────────────────
TOTAL COMBINED                   ~0.59%    ~118.45 MiB / 955MiB  ~12.4%    (>830 MB FREE)
```

---

## 🚀 Installation & Quickstart

### Prerequisites
* Docker Engine 20.10+ & Docker Compose v2+
* Linux (Debian, Ubuntu, Raspberry Pi OS, Alpine) on ARMv7, ARM64, or x86_64

---

### Option 1: 1-Line Automated Installer (Recommended for Pi & Linux)

Run this single command on your Raspberry Pi or server. It automatically prepares Docker, handles port 53 `systemd-resolved` conflicts, generates TLS certificates, and starts the containers:

```bash
curl -fsSL https://raw.githubusercontent.com/akhilgupta2007/blocky-dns-UI/main/scripts/install.sh | sudo bash
```

---

### Option 2: Manual Docker Compose Deployment

#### 1. Clone the repository:
```bash
git clone https://github.com/akhilgupta2007/blocky-dns-UI.git
cd blocky-dns-UI
```

#### 2. Resolve Port 53 Stub Listener (Ubuntu/Debian only):
If `systemd-resolved` occupies port 53 on your host:
```bash
sudo sed -r -i.orig 's/#?DNSStubListener=yes/DNSStubListener=no/g' /etc/systemd/resolved.conf
sudo systemctl restart systemd-resolved
```

#### 3. Launch Services:
```bash
docker compose up -d
```

#### 4. Access the Dashboard:
* **Secured Web Dashboard (HTTPS)**: `https://<YOUR-SERVER-IP>:3443`
* **HTTP (Redirects to HTTPS)**: `http://<YOUR-SERVER-IP>:3000`
* **DNS Server Port**: `53 (UDP & TCP)`

> **First Run**: Open `https://<YOUR-SERVER-IP>:3443` in your browser. The initial setup wizard will guide you through creating your master administrator password.

---

### Option 3: Connecting Hub to an Existing Standalone Blocky Instance

If you already run Blocky on another machine or container:

```bash
docker compose -f docker-compose.existing.yml up -d
```
*(Configure `BLOCKY_API_URL` in `.env` to point to your existing instance, e.g. `http://192.168.1.5:4000`)*

---

## 🔌 Port Mapping Reference

| Port | Protocol | Usage | Description |
| :---: | :---: | :--- | :--- |
| **53** | UDP / TCP | External (LAN) | Primary DNS listener for all client devices |
| **3443** | TCP (HTTPS) | External (Web) | End-to-end encrypted management dashboard & REST API |
| **3000** | TCP (HTTP) | External (Web) | Plain HTTP port (Automatically 301-redirects to HTTPS) |
| **4000** | TCP (HTTP) | Internal Bridge | Blocky internal control API & Prometheus metrics endpoint |

---

## 🔒 Security & Anti-Sniffing Shield

* **Zero-Config TLS 1.3**: On first startup, the hub automatically generates an ECDSA/RSA certificate in `certs/` with Subject Alternative Names (SAN) matching all local IP addresses and hostnames.
* **Custom SSL Certificates**: You can mount your own certificates (e.g. from Let's Encrypt or your local CA) by placing `cert.pem` and `key.pem` in the `certs/` directory.
* **Anti-Sniffing**: Eliminates cleartext HTTP session tokens and dashboard access, protecting against ARP spoofing and packet sniffing on shared home Wi-Fi networks.

---

## 🔄 Applying AdGuard Home Custom Rules

You can migrate your existing AdGuard Home custom filtering rules directly:
1. Open the dashboard and navigate to **Blocklists & Rules**.
2. Click **`📥 Bulk Import AdGuard Rules`**.
3. Paste your AdGuard rules directly (e.g.):
   ```text
   @@||content22.bmo.com^$important
   ||dns.google^
   ||cloudflare-dns.com^
   ||bureau.id^
   @@||web.facebook.com^
   ```
4. Click **`Import & Apply Rules`**. The parser automatically sorts them into Whitelist and Blacklist, strips syntax modifiers, compiles the engine files, and flushes the DNS cache.

---

## 🛠️ Updating the Installation

To update your deployment to the latest version:

```bash
cd blocky-dns
git pull
docker compose build --no-cache hub
docker compose restart
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE). Built on the shoulders of the incredible [Blocky DNS](https://github.com/0xERR0R/blocky) project by 0xERR0R.
