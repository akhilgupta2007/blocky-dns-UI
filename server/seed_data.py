import datetime
import random
import json
from database import get_connection

def _sync_services_catalog(cursor):
    services = [
        ("tiktok", "TikTok", "Social Media", "🎵", json.dumps([
            "tiktok.com", "tiktokcdn.com", "musical.ly", "byteoversea.com", "ibytedtos.com", "tiktokv.com"
        ])),
        ("youtube", "YouTube", "Video & Streaming", "▶️", json.dumps([
            "youtube.com", "youtu.be", "ytimg.com", "googlevideo.com", "youtube-nocookie.com"
        ])),
        ("roblox", "Roblox", "Gaming", "🧱", json.dumps([
            "roblox.com", "rbxcdn.com", "robloxlabs.com", "rbxtrk.com"
        ])),
        ("facebook_instagram", "Facebook & Instagram", "Social Media", "👥", json.dumps([
            "facebook.com", "fbcdn.net", "instagram.com", "cdninstagram.com", "meta.com", "messenger.com"
        ])),
        ("twitter_x", "Twitter / X", "Social Media", "🐦", json.dumps([
            "twitter.com", "x.com", "twimg.com", "t.co"
        ])),
        ("discord", "Discord", "Messaging", "💬", json.dumps([
            "discord.com", "discordapp.com", "discord.gg", "discordapp.net", "discordstatus.com"
        ])),
        ("steam", "Steam", "Gaming", "🎮", json.dumps([
            "steampowered.com", "steamcommunity.com", "steamstatic.com", "steamcontent.com"
        ])),
        ("epic_games", "Epic Games / Fortnite", "Gaming", "⚔️", json.dumps([
            "epicgames.com", "unrealengine.com", "fortnite.com"
        ])),
        ("reddit", "Reddit", "Social Media", "🤖", json.dumps([
            "reddit.com", "redd.it", "redditmedia.com", "redditstatic.com"
        ])),
        ("netflix", "Netflix", "Video & Streaming", "🍿", json.dumps([
            "netflix.com", "nflxvideo.net", "nflxext.com", "nflximg.net"
        ])),
        ("spotify", "Spotify", "Audio & Music", "🎧", json.dumps([
            "spotify.com", "scdn.co", "spotifycdn.com"
        ])),
        ("twitch", "Twitch", "Video & Streaming", "📺", json.dumps([
            "twitch.tv", "ttvnw.net", "jtvnw.net"
        ])),
        ("telegram", "Telegram", "Messaging", "✈️", json.dumps([
            "telegram.org", "t.me", "telesco.pe"
        ])),
        ("whatsapp", "WhatsApp", "Messaging", "📞", json.dumps([
            "whatsapp.com", "whatsapp.net"
        ])),
        ("snapchat", "Snapchat", "Social Media", "👻", json.dumps([
            "snapchat.com", "sc-cdn.net"
        ])),
        ("tinder", "Tinder & Dating", "Adult & Dating", "🔥", json.dumps([
            "tinder.com", "gotinder.com", "tindersparks.com", "badoo.com", "bumble.com"
        ])),
        ("pinterest", "Pinterest", "Social Media", "📌", json.dumps([
            "pinterest.com", "pinimg.com"
        ])),
        ("amazon_shopping", "Amazon Shopping", "Shopping", "📦", json.dumps([
            "amazon.com", "ssl-images-amazon.com", "media-amazon.com"
        ])),
        ("ebay_aliexpress", "eBay & AliExpress", "Shopping", "🛒", json.dumps([
            "ebay.com", "aliexpress.com", "alicdn.com"
        ])),
        ("adult_explicit", "Adult / Explicit Sites", "Adult & Dating", "🔞", json.dumps([
            "pornhub.com", "www.pornhub.com", "phncdn.com", "pornhubpremium.com",
            "xvideos.com", "www.xvideos.com", "xvideos-cdn.com",
            "xnxx.com", "www.xnxx.com", "xnxx-cdn.com",
            "onlyfans.com", "chaturbate.com",
            "redtube.com", "youporn.com", "tube8.com",
            "spankbang.com", "brazzers.com", "stripchat.com",
            "cam4.com", "livejasmin.com", "bongacams.com",
            "xhamster.com", "xhamsterlive.com"
        ]))
    ]
    for s_id, s_name, s_cat, s_icon, s_domains in services:
        cursor.execute("""
        INSERT INTO blocked_services (id, name, category, icon, domains_json, enabled, updated_at)
        VALUES (?, ?, ?, ?, ?, 0, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            category = excluded.category,
            icon = excluded.icon,
            domains_json = excluded.domains_json;
        """, (s_id, s_name, s_cat, s_icon, s_domains))

def seed_initial_data():
    conn = get_connection()
    cursor = conn.cursor()

    # Always ensure the blocked_services catalog is up to date without resetting user toggles
    _sync_services_catalog(cursor)

    # Check if database has already been initialized previously
    cursor.execute("SELECT value FROM settings WHERE key = 'initial_seed_completed';")
    seed_row = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) as cnt FROM users;")
    has_users = cursor.fetchone()["cnt"] > 0

    if (seed_row and seed_row["value"] == "true") or has_users:
        # Mark setting if missing
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('initial_seed_completed', 'true');")
        conn.commit()
        conn.close()
        print("[DB] Database already initialized. Preserving all user records, local DNS, and custom configurations.")
        return

    # 0. Seed Default Admin User if no user exists
    from auth import hash_password
    print("[DB] Seeding primary administrator account (admin)...")
    cursor.execute("""
    INSERT INTO users (username, password_hash, created_at, last_login)
    VALUES (?, ?, datetime('now'), datetime('now'));
    """, ("admin", hash_password("StrongPassword123!")))

    # 1. Seed Blocklists
    blocklists = [
        ("StevenBlack Unified Adware/Malware", "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts", "Adware & Tracking", 1, 165420),
        ("OISD Anti-Tracking (Big)", "https://big.oisd.nl", "Privacy & Telemetry", 1, 241980),
        ("HaGeZi Threat Intelligence", "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/pro.txt", "Malware & Phishing", 1, 120540),
        ("Smart TV Telemetry Blocker", "https://raw.githubusercontent.com/Perflyst/PiHoleBlocklist/master/SmartTV.txt", "IoT & Smart Devices", 0, 8450),
        ("Parental & Adult Filter", "https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/porn/hosts", "Family & Safety", 0, 68900)
    ]
    for b in blocklists:
        cursor.execute("""
        INSERT OR IGNORE INTO blocklists (name, url, category, enabled, rule_count, last_updated)
        VALUES (?, ?, ?, ?, ?, datetime('now'));
        """, b)

    # 2. Seed Upstreams
    upstreams = [
        ("Cloudflare DoH", "https://1.1.1.1/dns-query", "doh", 1, 0, 11.4),
        ("Cloudflare Security DoH", "https://security.cloudflare-dns.com/dns-query", "doh", 1, 0, 12.1),
        ("Quad9 Secure DoH", "https://dns.quad9.net/dns-query", "doh", 1, 0, 18.2),
        ("Google Public DoH", "https://dns.google/dns-query", "doh", 0, 0, 24.3),
        ("Cloudflare DoT", "tcp-tls:1.1.1.1:853", "dot", 1, 0, 14.5),
        ("Quad9 DoT", "tcp-tls:9.9.9.9:853", "dot", 0, 0, 19.8)
    ]
    for u in upstreams:
        cursor.execute("""
        INSERT OR IGNORE INTO upstreams (name, endpoint, protocol, enabled, is_custom, last_latency_ms)
        VALUES (?, ?, ?, ?, ?, ?);
        """, u)

    # 3. Seed Local DNS & Wildcards
    local_records = [
        ("router.lan", "192.168.1.1", "A", 0, 1),
        ("nas.home", "192.168.1.50", "A", 0, 1),
        ("*.lab.internal", "192.168.1.100", "A", 1, 1),
        ("proxmox.lan", "192.168.1.20", "A", 0, 1)
    ]
    for r in local_records:
        cursor.execute("""
        INSERT OR IGNORE INTO local_dns (domain, ip_address, record_type, is_wildcard, enabled, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'));
        """, r)

    # 4. Seed Domain Routing (Geo-Bypass)
    routings = [
        ("bbc.co.uk", "https://uk.dns.mullvad.net/dns-query", "UK Geo-Bypass", 1),
        ("hulu.com", "198.51.100.4", "SmartDNS US", 1),
        ("blocked-news.org", "https://dns.quad9.net/dns-query", "Swiss Uncensored", 1),
        ("*.corp.internal", "172.16.0.2", "Company VPN", 1)
    ]
    for ro in routings:
        cursor.execute("""
        INSERT OR IGNORE INTO domain_routing (domain_pattern, resolver, tag, enabled, created_at)
        VALUES (?, ?, ?, ?, datetime('now'));
        """, ro)

    # 5. Seed Settings
    settings_kv = [
        ("strict_encrypted_mode", "true"),
        ("block_ipv6", "true"),
        ("log_retention_days", "7"),
        ("router_ip", "192.168.1.1"),
        ("upstream_strategy", "parallel_best"),
        ("auto_benchmark_interval", "24"),
        ("last_benchmark_timestamp", ""),
        ("rebinding_shield", "true"),
        ("integration_mode", "all-in-one"),
        ("theme", "dark"),
        ("caching_enabled", "true"),
        ("cache_min_ttl", "5m"),
        ("cache_max_ttl", "30m"),
        ("cache_neg_ttl", "30m"),
        ("prefetching_enabled", "true"),
        ("prefetch_threshold", "3"),
        ("dnssec_enabled", "true"),
        ("edns_anonymize_ecs", "true"),
        ("log_ptr_queries", "false")
    ]
    for k, v in settings_kv:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?);", (k, v))

    # 6. Seed Devices & Sample logs only if demo data has NOT been cleared by the user
    cursor.execute("SELECT value FROM settings WHERE key = 'demo_data_cleared';")
    cleared_row = cursor.fetchone()
    demo_cleared = (cleared_row and cleared_row["value"] == "true")

    if not demo_cleared:
        sample_devices = [
            ("192.168.1.45", "appletv.lan", "Living Room Apple TV", "tv", "living-room", 2450, 441),
            ("192.168.1.12", "macbook-pro.lan", "MacBook Pro", "laptop", "work", 1280, 166),
            ("192.168.1.15", "macbook-air.lan", "MacBook Air", "laptop", "personal", 890, 72),
            ("192.168.1.22", "ipad-pro.lan", "iPad Pro", "tablet", "personal", 640, 95),
            ("192.168.1.99", "smart-fridge.lan", "Smart Fridge", "iot", "iot", 573, 34),
            ("192.168.1.10", "desktop-pc.lan", "Desktop PC", "laptop", "gaming", 1420, 210)
        ]
        for d in sample_devices:
            cursor.execute("""
            INSERT OR IGNORE INTO devices (client_ip, hostname, friendly_name, icon, group_name, total_queries, blocked_queries, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', '-3 days'), datetime('now'));
            """, d)

        # 7. Check if log_entries are empty; if so, populate initial realistic queries for past 24 hours
        cursor.execute("SELECT COUNT(*) as cnt FROM log_entries;")
        if cursor.fetchone()["cnt"] == 0:
            print("[DB] Populating initial realistic query logs for analytics...")
        domains_allowed = [
            "github.com", "google.com", "cloudflare.com", "apple.com", "wikipedia.org",
            "youtube.com", "netflix.com", "reddit.com", "amazon.com", "discord.com",
            "microsoft.com", "spotify.com", "docker.com", "archlinux.org", "nas.home"
        ]
        domains_blocked = [
            "google-analytics.com", "doubleclick.net", "telemetry.samsungcloud.com",
            "track.itunes.apple.com", "metrics.ads.co", "ads.yahoo.com",
            "app-measurement.com", "pixel.facebook.com", "adservice.google.com"
        ]
        ips = [d[0] for d in sample_devices]

        now = datetime.datetime.now(datetime.timezone.utc)
        # Create 180 realistic query log entries spaced out over 24 hours
        for i in range(180):
            ts = now - datetime.timedelta(minutes=random.randint(1, 1400))
            is_blocked = random.random() < 0.18 # ~18% blocked rate
            ip = random.choice(ips)
            q_type = random.choice(["A", "A", "AAAA", "HTTPS"])
            dur = random.randint(1, 28)

            if is_blocked:
                domain = random.choice(domains_blocked)
                resp_type = "BLOCKED"
                reason = "Blocked by list: StevenBlack Unified"
                answer = "0.0.0.0"
            else:
                domain = random.choice(domains_allowed)
                resp_type = random.choice(["RESOLVED", "RESOLVED", "CACHED"])
                reason = "Upstream Cloudflare DoH" if resp_type == "RESOLVED" else "Cache hit"
                answer = f"104.{random.randint(16,28)}.{random.randint(1,250)}.{random.randint(1,250)}"

            cursor.execute("""
            INSERT INTO log_entries (request_ts, client_ip, client_name, duration_ms, reason, response_type, question, answer)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (ts.strftime("%Y-%m-%d %H:%M:%S"), ip, ip, dur, reason, resp_type, domain, answer))

    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('initial_seed_completed', 'true');")
    conn.commit()
    conn.close()
    print("[DB] Seed data verified and ready.")

if __name__ == "__main__":
    seed_initial_data()
