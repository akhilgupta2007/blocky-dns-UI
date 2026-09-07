import os
import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

# Set testing environment paths
os.environ["DATA_DIR"] = str(Path(__file__).parent / "data")
os.environ["CERTS_DIR"] = str(Path(__file__).parent / "certs")
os.environ["BLOCKY_CONFIG_PATH"] = str(Path(__file__).parent / "config" / "config.yml")
os.environ["ENABLE_HTTPS"] = "false"

sys.path.insert(0, str(Path(__file__).parent / "server"))
sys.path.insert(0, str(Path(__file__).parent / "server" / "routes"))

from database import init_db
from seed_data import seed_initial_data
from tls_manager import ensure_tls_certificates, get_certificate_info
from main import app

class TestBlockyDnsHub(unittest.TestCase):
    headers = {}

    @classmethod
    def setUpClass(cls):
        init_db()
        seed_initial_data()
        ensure_tls_certificates()
        cls.client = TestClient(app)
        from auth import create_access_token
        token = create_access_token("admin")
        cls.headers = {"Authorization": f"Bearer {token}"}

    def test_01_tls_certificates_generated(self):
        cert_info = get_certificate_info()
        self.assertTrue(cert_info.get("active"))
        self.assertTrue("localhost" in cert_info.get("sans", []))
        print("[OK] TLS Certificate generation verified with SANs:", cert_info.get("sans"))

    def test_02_auth_setup_and_login(self):
        # 1. Check status
        res = self.client.get("/api/auth/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("setup_completed", data)

        # 2. Setup admin or login
        setup_res = self.client.post("/api/auth/setup", json={
            "username": "admin",
            "password": "StrongPassword123!",
            "integration_mode": "all-in-one"
        })
        if setup_res.status_code == 200:
            token = setup_res.json().get("token")
        else:
            login_res = self.client.post("/api/auth/login", json={
                "username": "admin",
                "password": "StrongPassword123!"
            })
            self.assertEqual(login_res.status_code, 200)
            token = login_res.json().get("token")

        self.assertIsNotNone(token)
        TestBlockyDnsHub.headers = {"Authorization": f"Bearer {token}"}
        print("[OK] Authentication & JWT session token verified")

    def test_03_stats_and_telemetry(self):
        res = self.client.get("/api/stats/summary", headers=TestBlockyDnsHub.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["total_queries_24h"], 0)
        self.assertGreater(data["active_rules_count"], 0)
        print(f"[OK] Stats Summary: {data['total_queries_24h']} queries, {data['blocked_queries_24h']} blocked ({data['blocked_percent']}%)")

        # Timeline
        timeline_res = self.client.get("/api/stats/timeline", headers=TestBlockyDnsHub.headers)
        self.assertEqual(timeline_res.status_code, 200)
        self.assertIsInstance(timeline_res.json(), list)
        print(f"[OK] 24h Timeline buckets verified: {len(timeline_res.json())} hours")

        # Top devices
        devices_res = self.client.get("/api/stats/top-devices", headers=TestBlockyDnsHub.headers)
        self.assertEqual(devices_res.status_code, 200)
        top_devs = devices_res.json()
        self.assertGreater(len(top_devs), 0)
        print(f"[OK] Top client device: {top_devs[0]['name']} ({top_devs[0]['client_ip']})")

    def test_04_query_logs_with_friendly_names(self):
        res = self.client.get("/api/logs?page=1&limit=20", headers=TestBlockyDnsHub.headers)
        self.assertEqual(res.status_code, 200)
        logs = res.json()
        self.assertGreater(logs["total_records"], 0)
        first_record = logs["records"][0]
        self.assertIn("client_name", first_record)
        self.assertIn("question", first_record)
        self.assertIn("response_type", first_record)
        print(f"[OK] Query log row verified: {first_record['request_ts']} | {first_record['client_name']} -> {first_record['question']} [{first_record['response_type']}]")

        # Test Date Range Filter
        range_res = self.client.get(
            "/api/logs?page=1&limit=20&from_ts=2020-01-01T00:00:00Z&to_ts=2030-01-01T00:00:00Z",
            headers=TestBlockyDnsHub.headers
        )
        self.assertEqual(range_res.status_code, 200)
        range_logs = range_res.json()
        self.assertGreater(range_logs["total_records"], 0)
        print(f"[OK] Query log date range filter verified: {range_logs['total_records']} records matched")


    def test_05_blocklists_and_custom_rules(self):
        # 1. List blocklists
        res = self.client.get("/api/blocklists", headers=TestBlockyDnsHub.headers)
        self.assertEqual(res.status_code, 200)
        lists = res.json()
        self.assertGreaterEqual(len(lists), 3)

        # 2. Add custom blacklist rule
        add_rule = self.client.post("/api/rules/add", headers=TestBlockyDnsHub.headers, json={
            "rule_type": "blacklist",
            "domain": "*.testtracker.local",
            "comment": "Test rule"
        })
        self.assertEqual(add_rule.status_code, 200)
        print("[OK] Custom Blacklist rule addition verified")

    def test_06_local_dns_and_wildcards(self):
        # Add local wildcard
        add_res = self.client.post("/api/local-dns/add", headers=TestBlockyDnsHub.headers, json={
            "domain": "*.homelab.lan",
            "ip_address": "192.168.1.200",
            "record_type": "A"
        })
        self.assertEqual(add_res.status_code, 200)

        # List local DNS
        list_res = self.client.get("/api/local-dns", headers=TestBlockyDnsHub.headers)
        self.assertEqual(list_res.status_code, 200)
        records = list_res.json()
        self.assertTrue(any(r["domain"] == "*.homelab.lan" for r in records))
        print("[OK] Wildcard Local DNS (*.homelab.lan -> 192.168.1.200) verified")

    def test_07_domain_routing_geo_bypass(self):
        add_route = self.client.post("/api/routing/add", headers=TestBlockyDnsHub.headers, json={
            "domain_pattern": "streaming-uk.service",
            "resolver": "https://uk.dns.mullvad.net/dns-query",
            "tag": "UK Geo-Bypass"
        })
        self.assertEqual(add_route.status_code, 200)

        list_route = self.client.get("/api/routing", headers=TestBlockyDnsHub.headers)
        self.assertEqual(list_route.status_code, 200)
        self.assertTrue(any(r["domain_pattern"] == "streaming-uk.service" for r in list_route.json()))
        print("[OK] Domain-specific Geo-Bypass upstream routing verified")

    def test_08_tools_diagnostic(self):
        diag_res = self.client.post("/api/tools/diagnostic", headers=TestBlockyDnsHub.headers, json={
            "domain": "google-analytics.com"
        })
        self.assertEqual(diag_res.status_code, 200)
        diag = diag_res.json()
        self.assertEqual(diag["status"], "BLOCKED")
        self.assertIn("Blocked by", diag["rule_match"])
        print(f"[OK] Interactive DNS diagnostic verified: {diag['domain']} -> {diag['status']} ({diag['rule_match']})")

    def test_09_strict_encrypted_dns_mode(self):
        res = self.client.post("/api/upstreams/strict-mode", headers=TestBlockyDnsHub.headers, json={"enabled": True})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["strict_encrypted_mode"])
        print("[OK] Strict Encrypted DNS Mode policy enforcement verified")

    def test_10_strict_ipv6_blocking(self):
        res = self.client.post("/api/upstreams/block-ipv6", headers=TestBlockyDnsHub.headers, json={"enabled": True})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["block_ipv6"])

        # Verify config.yml has filtering queryTypes AAAA
        config_path = Path(os.environ["BLOCKY_CONFIG_PATH"])
        self.assertTrue(config_path.exists())
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("connectIPVersion: v4", content)
        self.assertIn("AAAA", content)
    def test_11_change_password(self):
        # 1. Attempt with incorrect current password
        bad_res = self.client.post("/api/auth/change-password", headers=TestBlockyDnsHub.headers, json={
            "current_password": "WrongPassword!",
            "new_password": "NewStrongPassword123!"
        })
        self.assertEqual(bad_res.status_code, 400)

        # 2. Change with correct password
        ok_res = self.client.post("/api/auth/change-password", headers=TestBlockyDnsHub.headers, json={
            "current_password": "StrongPassword123!",
            "new_password": "NewStrongPassword123!"
        })
        self.assertEqual(ok_res.status_code, 200)

        # 3. Verify login works with new password
        login_res = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "NewStrongPassword123!"
        })
        self.assertEqual(login_res.status_code, 200)

        # Restore original password for any subsequent tests
        self.client.post("/api/auth/change-password", headers=TestBlockyDnsHub.headers, json={
            "current_password": "NewStrongPassword123!",
            "new_password": "StrongPassword123!"
        })
        print("[OK] Change password verification & validation passed")

    def test_12_blocky_integration(self):
        # 1. GET integration details
        res = self.client.get("/api/control/integration", headers=TestBlockyDnsHub.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("integration_mode", data)
        self.assertIn("blocky_api_url", data)

        # 2. Update to existing instance
        update_res = self.client.post("/api/control/integration", headers=TestBlockyDnsHub.headers, json={
            "integration_mode": "existing",
            "blocky_api_url": "http://192.168.1.50:4000",
            "blocky_config_path": "/app/config/config.yml"
        })
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.json()["integration_mode"], "existing")

        # 3. Test connection endpoint
        test_res = self.client.post("/api/control/test-integration", headers=TestBlockyDnsHub.headers, json={
            "blocky_api_url": "http://127.0.0.1:4000"
        })
        self.assertEqual(test_res.status_code, 200)
        self.assertIn("online", test_res.json())

        # 4. Restore all-in-one mode
        self.client.post("/api/control/integration", headers=TestBlockyDnsHub.headers, json={
            "integration_mode": "all-in-one",
            "blocky_api_url": "http://localhost:4000",
            "blocky_config_path": os.environ.get("BLOCKY_CONFIG_PATH", "")
        })
        print("[OK] Blocky integration setup & test endpoints verified")

    def test_13_blocked_services_catalog(self):
        # 1. GET services catalog
        res = self.client.get("/api/services", headers=TestBlockyDnsHub.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("services", data)
        self.assertGreaterEqual(len(data["services"]), 15)

        service_names = [s["name"] for s in data["services"]]
        self.assertIn("TikTok", service_names)
        self.assertIn("YouTube", service_names)
        self.assertIn("Roblox", service_names)

        # 2. Toggle single service (TikTok)
        toggle_res = self.client.post("/api/services/toggle", headers=TestBlockyDnsHub.headers, json={
            "service_id": "tiktok",
            "enabled": True
        })
        self.assertEqual(toggle_res.status_code, 200)
        self.assertTrue(toggle_res.json()["enabled"])

        # Check custom_blacklist.txt has tiktok.com and config.yml references it
        config_path = Path(os.environ["BLOCKY_CONFIG_PATH"])
        self.assertTrue(config_path.exists())
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = f.read()
        self.assertIn("custom_blacklist.txt", cfg)

        blacklist_path = Path(os.environ["DATA_DIR"]) / "custom_blacklist.txt"
        self.assertTrue(blacklist_path.exists())
        with open(blacklist_path, "r", encoding="utf-8") as f:
            bl_content = f.read()
        self.assertIn("tiktok.com", bl_content)

        # 3. Bulk toggle Gaming category
        bulk_res = self.client.post("/api/services/bulk", headers=TestBlockyDnsHub.headers, json={
            "category": "Gaming",
            "enabled": True
        })
        self.assertEqual(bulk_res.status_code, 200)
        self.assertGreater(bulk_res.json()["updated_count"], 0)

        # 4. Clean up / disable
        self.client.post("/api/services/toggle", headers=TestBlockyDnsHub.headers, json={
            "service_id": "tiktok",
            "enabled": False
        })
        self.client.post("/api/services/bulk", headers=TestBlockyDnsHub.headers, json={
            "category": "Gaming",
            "enabled": False
        })
        print(f"[OK] 1-Click Blocked Services catalog & engine compilation verified ({len(data['services'])} services)")

    def test_14_high_speed_caching_and_prefetching(self):
        # 1. GET caching settings
        res = self.client.get("/api/control/caching", headers=TestBlockyDnsHub.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("caching_enabled", data)
        self.assertIn("prefetching_enabled", data)

        # 2. POST update caching settings
        post_res = self.client.post("/api/control/caching", headers=TestBlockyDnsHub.headers, json={
            "caching_enabled": True,
            "cache_min_ttl": 600,
            "cache_max_ttl": 86400,
            "cache_neg_ttl": 300,
            "prefetching_enabled": True,
            "prefetch_threshold": 3
        })
        self.assertEqual(post_res.status_code, 200)

        # Check config.yml has caching block
        config_path = Path(os.environ["BLOCKY_CONFIG_PATH"])
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = f.read()
        self.assertIn("caching:", cfg)
        self.assertIn("minTime: 600s", cfg)
        self.assertIn("prefetching: true", cfg)
        self.assertIn("prefetchThreshold: 3", cfg)
        print("[OK] In-memory caching & prefetching settings and config.yml compilation verified")

    def test_15_dnssec_and_privacy_shield(self):
        # 1. GET & POST dnssec settings
        res = self.client.get("/api/control/dnssec", headers=TestBlockyDnsHub.headers)
        self.assertEqual(res.status_code, 200)

        post_res = self.client.post("/api/control/dnssec", headers=TestBlockyDnsHub.headers, json={
            "dnssec_enabled": True,
            "edns_anonymize_ecs": True
        })
        self.assertEqual(post_res.status_code, 200)

        # Check config.yml has ecs and dnssec
        config_path = Path(os.environ["BLOCKY_CONFIG_PATH"])
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = f.read()
        self.assertIn("ecs:", cfg)
        self.assertIn("useAsClient: false", cfg)
        self.assertIn("dnssec:", cfg)

        # 2. Interactive DNSSEC Inspector test
        inspect_res = self.client.post("/api/tools/dnssec-inspect", headers=TestBlockyDnsHub.headers, json={
            "domain": "cloudflare.com"
        })
        self.assertEqual(inspect_res.status_code, 200)
        insp = inspect_res.json()
        self.assertEqual(insp["domain"], "cloudflare.com")
        self.assertIn(insp["status"], ["SECURE", "PARTIAL", "UNSIGNED"])
        print(f"[OK] DNSSEC inspection for cloudflare.com: Status={insp['status']}, DNSKEY={insp['has_dnskey']}, DS={insp['has_ds']}")

    def test_16_query_log_stream_endpoint(self):
        # Verify SSE stream endpoint is properly registered in api_logs routes
        from api_logs import router as logs_router
        route_paths = [r.path for r in logs_router.routes]
        self.assertIn("/api/logs/stream", route_paths)
        print("[OK] Real-time SSE Query Log stream endpoint registered and verified (/api/logs/stream)")

    def test_17_blocked_services_and_custom_blacklist(self):
        # 1. Fetch blocked services catalog
        res = self.client.get("/api/services", headers=TestBlockyDnsHub.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["total_services"], 15)

        # 2. Toggle "adult_explicit" to ON
        toggle_res = self.client.post("/api/services/toggle", headers=TestBlockyDnsHub.headers, json={
            "service_id": "adult_explicit",
            "enabled": True
        })
        self.assertEqual(toggle_res.status_code, 200)
        self.assertTrue(toggle_res.json()["enabled"])

        # 3. Verify custom_blacklist.txt contains pornhub.com
        blacklist_path = Path(os.environ["DATA_DIR"]) / "custom_blacklist.txt"
        self.assertTrue(blacklist_path.exists())
        with open(blacklist_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("pornhub.com", content)
        self.assertIn("phncdn.com", content)
        self.assertIn("xvideos.com", content)

        # 4. Verify config.yml references custom_blacklist.txt as a valid source (not bare domains)
        config_path = Path(os.environ["BLOCKY_CONFIG_PATH"])
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = f.read()
        self.assertIn("custom_blacklist.txt", cfg)
        self.assertNotIn("- pornhub.com", cfg)  # Bare domains must not be in YAML list sources!

        # 5. Test flush-cache endpoint
        flush_res = self.client.post("/api/control/flush-cache", headers=TestBlockyDnsHub.headers)
        self.assertEqual(flush_res.status_code, 200)

        # 6. Test custom blacklist rule
        rule_res = self.client.post("/api/rules/add", headers=TestBlockyDnsHub.headers, json={
            "rule_type": "blacklist",
            "domain": "*.badtracker.xyz",
            "comment": "Wildcard tracker test"
        })
        self.assertEqual(rule_res.status_code, 200)
        with open(blacklist_path, "r", encoding="utf-8") as f:
            updated_blacklist = f.read()
        self.assertIn("badtracker.xyz", updated_blacklist)

        # 7. Test custom whitelist rule
        wrule_res = self.client.post("/api/rules/add", headers=TestBlockyDnsHub.headers, json={
            "rule_type": "whitelist",
            "domain": "internal.lan",
            "comment": "Internal whitelist test"
        })
        self.assertEqual(wrule_res.status_code, 200)
        whitelist_path = Path(os.environ["DATA_DIR"]) / "custom_whitelist.txt"
        self.assertTrue(whitelist_path.exists())
        with open(whitelist_path, "r", encoding="utf-8") as f:
            updated_whitelist = f.read()
        self.assertIn("internal.lan", updated_whitelist)

        print("[OK] Blocked services & custom blacklist/whitelist file-based ingestion and cache flush verified!")

    def test_18_noisy_logging_suppression_and_audit(self):
        # 1. Test updating system settings with log_ptr_queries = False (default)
        set_res1 = self.client.post("/api/control/settings", headers=TestBlockyDnsHub.headers, json={
            "log_retention_days": 7,
            "router_ip": "10.0.0.1",
            "log_ptr_queries": False
        })
        self.assertEqual(set_res1.status_code, 200)

        # Verify config.yml contains queryLog ignore section
        config_path = Path(os.environ["BLOCKY_CONFIG_PATH"])
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = f.read()
        self.assertIn("ignore:", cfg)
        self.assertIn("sudn: true", cfg)
        self.assertIn("in-addr.arpa", cfg)
        self.assertIn("0.0.10.in-addr.arpa", cfg) # Router subnet PTR mapping verified

        # 2. Test updating system settings with log_ptr_queries = True (user enabled)
        set_res2 = self.client.post("/api/control/settings", headers=TestBlockyDnsHub.headers, json={
            "log_retention_days": 7,
            "router_ip": "10.0.0.1",
            "log_ptr_queries": True
        })
        self.assertEqual(set_res2.status_code, 200)
        with open(config_path, "r", encoding="utf-8") as f:
            cfg2 = f.read()
        self.assertNotIn("sudn: true", cfg2)

        # Reset to False (default recommended)
        self.client.post("/api/control/settings", headers=TestBlockyDnsHub.headers, json={
            "log_retention_days": 7,
            "router_ip": "10.0.0.1",
            "log_ptr_queries": False
        })

        # 3. Test Query Log filtering for SUDN & PTR records
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO log_entries (request_ts, client_ip, question_name, question, response_type, reason)
        VALUES (datetime('now'), '10.0.0.15', '250.0.0.10.in-addr.arpa', '250.0.0.10.in-addr.arpa', 'SPECIAL', 'Special-Use Domain Name');
        """)
        conn.commit()
        conn.close()

        # Query with include_ptr = False (default) -> should NOT return the special/PTR query
        logs_hidden = self.client.get("/api/logs?include_ptr=false&search=250.0.0.10", headers=TestBlockyDnsHub.headers).json()
        self.assertEqual(logs_hidden["total_records"], 0)

        # Query with include_ptr = True -> should return the query
        logs_shown = self.client.get("/api/logs?include_ptr=true&search=250.0.0.10", headers=TestBlockyDnsHub.headers).json()
        self.assertGreaterEqual(logs_shown["total_records"], 1)

        # 4. Test Domain-Specific Routing add and delete by string pattern
        route_add = self.client.post("/api/routing/add", headers=TestBlockyDnsHub.headers, json={
            "domain_pattern": "audit-test.org",
            "resolver": "https://dns.quad9.net/dns-query",
            "tag": "Audit Geo"
        })
        self.assertEqual(route_add.status_code, 200)
        # Delete by domain string
        route_del = self.client.delete("/api/routing/audit-test.org", headers=TestBlockyDnsHub.headers)
        self.assertEqual(route_del.status_code, 200)

        # 5. Test Blocklist Subscriptions add and delete by URL string
        list_add = self.client.post("/api/blocklists/add", headers=TestBlockyDnsHub.headers, json={
            "name": "Audit Adlist",
            "url": "https://example.com/audit-adlist.txt",
            "category": "Custom"
        })
        self.assertEqual(list_add.status_code, 200)
        # Delete by URL string
        list_del = self.client.delete("/api/blocklists/https%3A%2F%2Fexample.com%2Faudit-adlist.txt", headers=TestBlockyDnsHub.headers)
        self.assertEqual(list_del.status_code, 200)

        # 6. Test Client Devices PTR trigger
        ptr_res = self.client.post("/api/devices/resolve-ptr/10.0.0.15", headers=TestBlockyDnsHub.headers)
        self.assertEqual(ptr_res.status_code, 200)
        self.assertTrue(ptr_res.json()["success"])

        print("[OK] SUDN/PTR log suppression, Domain Routing, Blocklists, and PTR dispatch audited & verified!")

    def test_19_resolved_ip_and_whois_lookup(self):
        # 1. Verify query log returns answer field for resolved IP
        res = self.client.get("/api/logs?page=1&limit=10", headers=TestBlockyDnsHub.headers)
        self.assertEqual(res.status_code, 200)
        logs = res.json()
        self.assertGreater(len(logs["records"]), 0)
        record = logs["records"][0]
        self.assertIn("answer", record)

        # 2. Verify WHOIS endpoint returns domain intelligence
        whois_res = self.client.get("/api/tools/whois?domain=google.com", headers=TestBlockyDnsHub.headers)
        self.assertEqual(whois_res.status_code, 200)
        w_data = whois_res.json()
        self.assertEqual(w_data["domain"], "google.com")
        self.assertIn("whois_url", w_data)
        self.assertIn("virustotal_url", w_data)
        self.assertIn("whotracksme_url", w_data)
        self.assertIn("ghostery.com", w_data["whotracksme_url"])
        self.assertIn("resolved_ips", w_data)
        print(f"[OK] WHOIS lookup verified: Registrar={w_data['registrar']}, IPs={w_data['resolved_ips']}, WhoTracksMe={w_data['whotracksme_url']}")

    def test_20_upstream_latency_benchmark_and_quad9_http2(self):
        import asyncio
        from benchmark import benchmark_single_doh, benchmark_single_dot
        # Verify Quad9 DoH benchmark succeeds over HTTP/2 without returning HTTP 505
        res = asyncio.run(benchmark_single_doh("https://9.9.9.9/dns-query"))
        self.assertEqual(res.get("status"), "online")
        self.assertIsNotNone(res.get("latency_ms"))
        self.assertNotEqual(res.get("status"), "HTTP 505")

        # Verify Quad9 DoT benchmark executes
        dot_res = asyncio.run(benchmark_single_dot("tcp-tls:9.9.9.9:853"))
        self.assertIn(dot_res.get("status"), ["online", "Error: ConnectionResetError", "Error: TimeoutError"])

        # Clean up if already exists in test DB
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM upstreams WHERE endpoint = 'https://common.dot.dns.yandex.net/dns-query';")
        conn.commit()
        conn.close()

        # Verify custom resolver (e.g. Yandex) appears in GET /api/tools/benchmark and GET /api/upstreams
        add_yandex = self.client.post("/api/upstreams/add", headers=TestBlockyDnsHub.headers, json={
            "name": "Yandex DoH",
            "endpoint": "https://common.dot.dns.yandex.net/dns-query",
            "protocol": "doh"
        })
        self.assertEqual(add_yandex.status_code, 200)

        bench_get = self.client.get("/api/tools/benchmark", headers=TestBlockyDnsHub.headers)
        self.assertEqual(bench_get.status_code, 200)
        b_data = bench_get.json()
        self.assertIn("results", b_data)
        names = [r["name"] for r in b_data["results"]]
        self.assertIn("Yandex DoH", names)

        # Check /api/upstreams includes Yandex
        upstreams_res = self.client.get("/api/upstreams", headers=TestBlockyDnsHub.headers).json()
        u_names = [u["name"] for u in upstreams_res["upstreams"]]
        self.assertIn("Yandex DoH", u_names)

        print(f"[OK] Upstream benchmark & custom resolver verified: Yandex DoH in benchmark & routing selector (No HTTP 505)")

    def test_21_restart_engine_endpoint(self):
        res = self.client.post("/api/control/restart-engine", headers=TestBlockyDnsHub.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("restarted", data)
        self.assertIn("cache_flushed", data)
        print(f"[OK] Reload engine endpoint verified: restarted={data['restarted']}, cache_flushed={data['cache_flushed']}")

    def test_22_adguard_bulk_rules_import(self):
        from database import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM custom_rules WHERE comment = 'Imported AdGuard Rule';")
        conn.commit()
        conn.close()

        user_adguard_rules = """
@@||mobile-data.onetrust.io^$important
@@||content22.bmo.com^$important
@@||wup-content23.bmo.com^$important
||dns.google^
||cloudflare-dns.com^
||mozilla.cloudflare-dns.com^
||dns.quad9.net^
||dns.nextdns.io^
||doh.opendns.com^
||doh.cleanbrowsing.org^
||www.baidu.com^$important
||bureau.id^
||dia.bureau.id^
||api.bureau.id^
||signals.bureau.id^
||identity.bureau.id^
||fraud.bureau.id^
||mobile.events.data.microsoft.com^
@@||web.facebook.com^
@@||graph.facebook.com^
@@||connect.facebook.net^
||ads.linkedin.com^
||analytics.pointdrive.linkedin.com^
||px.ads.linkedin.com^
||snap.licdn.com^
||pixel.facebook.com^
||analytics.facebook.com^
||events.facebook.com^
||dns.google.com^
||cloudflare-dns.com^
||one.one.one.one^
||dns.quad9.net^
||dns.nextdns.io^
||opendns.com^
@@||findmydevice-pa.googleapis.com^
@@||f.wishabi.net^
@@||tags.tiqcdn.com^
@@||userlocation.googleapis.com^
@@||device-api.urbanairship.com^
@@||spot-pa.googleapis.com^
@@||semanticlocation-pa.googleapis.com^
@@||ar-genai.graph.meta.com^
@@||s.youtube.com^
"""
        res = self.client.post("/api/rules/import", headers=TestBlockyDnsHub.headers, json={
            "rules_text": user_adguard_rules,
            "default_type": "blacklist"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["added_whitelist"], 15)
        # Note: cloudflare-dns.com, dns.quad9.net, dns.nextdns.io appear twice in the list
        self.assertGreaterEqual(data["total_added"], 35)

        # Verify disk files contain cleaned domains without syntax junk
        data_dir = Path(os.environ["DATA_DIR"])
        wl_file = data_dir / "custom_whitelist.txt"
        bl_file = data_dir / "custom_blacklist.txt"
        self.assertTrue(wl_file.exists())
        self.assertTrue(bl_file.exists())

        wl_content = wl_file.read_text(encoding="utf-8")
        bl_content = bl_file.read_text(encoding="utf-8")

        self.assertIn("mobile-data.onetrust.io", wl_content)
        self.assertNotIn("@@||", wl_content)
        self.assertNotIn("$important", wl_content)
        self.assertIn("content22.bmo.com", wl_content)
        self.assertIn("web.facebook.com", wl_content)

        self.assertIn("dns.google", bl_content)
        self.assertNotIn("||dns.google^", bl_content)
        self.assertIn("bureau.id", bl_content)
        self.assertIn("www.baidu.com", bl_content)

        print(f"[OK] AdGuard bulk rules import verified: Whitelist={data['added_whitelist']}, Blacklist={data['added_blacklist']}")

if __name__ == "__main__":
    unittest.main()


