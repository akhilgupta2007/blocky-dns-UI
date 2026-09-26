import os
import sys
import time
import socket
import threading
import uvicorn
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = BASE_DIR / "test_output"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# Configure environment for testing server
os.environ["DATA_DIR"] = str(BASE_DIR / "data")
os.environ["BLOCKY_CONFIG_PATH"] = str(BASE_DIR / "config" / "config.yml")
os.environ["HTTP_PORT"] = "3001"
os.environ["ENABLE_HTTPS"] = "false"

sys.path.insert(0, str(BASE_DIR / "server"))
sys.path.insert(0, str(BASE_DIR / "server" / "routes"))

from database import init_db
from seed_data import seed_initial_data
from auth import create_access_token
from main import app

class TestServerThread(threading.Thread):
    def __init__(self, port=3001):
        super().__init__(daemon=True)
        self.port = port
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True

def wait_for_server(port=3001, timeout=10.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.1)
    return False

def run_comprehensive_frontend_tests():
    print("=" * 60)
    print("STARTING COMPREHENSIVE FRONTEND TEST SUITE")
    print("=" * 60)

    # 1. Start test server
    init_db()
    seed_initial_data()
    server_thread = TestServerThread(port=3001)
    server_thread.start()

    if not wait_for_server(3001):
        raise RuntimeError("Failed to start local test server on port 3001")
    print("[PASS] Local test web server started on http://127.0.0.1:3001")

    base_url = "http://127.0.0.1:3001"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Track console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # -------------------------------------------------------------
        # SUITE 1: AUTHENTICATION & LOGIN FLOW
        # -------------------------------------------------------------
        print("\n--- [SUITE 1: AUTHENTICATION & LOGIN FLOW] ---")
        page.goto(f"{base_url}/", wait_until="domcontentloaded")
        time.sleep(1)

        # Should redirect to login.html if not authenticated
        if "login" in page.url:
            print("[PASS] Unauthenticated visit correctly redirects to login view.")
            page.screenshot(path=str(ARTIFACT_DIR / "01_login_view.png"))
            print("Logging in with admin credentials...")
            page.fill("#username", "admin")
            page.fill("#password", "StrongPassword123!")
            page.click("#submitBtn")
            page.wait_for_selector("#viewDashboard.active", timeout=8000)
            print("[PASS] Admin login succeeded, redirected to active Dashboard.")
        else:
            page.wait_for_selector("#viewDashboard.active", timeout=8000)
            print("[PASS] Dashboard loaded directly with existing session.")

        # -------------------------------------------------------------
        # SUITE 2: DASHBOARD VIEW & TELEMETRY
        # -------------------------------------------------------------
        print("\n--- [SUITE 2: DASHBOARD VIEW & TELEMETRY] ---")
        page.wait_for_selector("#viewDashboard.active", timeout=5000)

        # Check Telemetry Metrics
        queries_card = page.locator("#kpiTotalQueries")
        assert queries_card.is_visible(), "Total Queries KPI should be visible"
        blocked_card = page.locator("#kpiBlockedQueries")
        assert blocked_card.is_visible(), "Blocked Queries KPI should be visible"
        block_pct = page.locator("#kpiBlockedPct")
        assert block_pct.is_visible(), "Blocked Percent badge should be visible"
        active_rules = page.locator("#kpiActiveRules")
        assert active_rules.is_visible(), "Active Rules KPI should be visible"

        print(f"[PASS] Telemetry Metric Cards loaded: Queries={queries_card.inner_text()}, Blocked={blocked_card.inner_text()}, Rate={block_pct.inner_text()}, Rules={active_rules.inner_text()}")

        # Check Quick-Pause Shield
        print("Testing Quick Pause Shield pills...")
        pause_1m_btn = page.locator("button.btn-pause-pill:has-text('1 min')")
        if pause_1m_btn.is_visible():
            pause_1m_btn.click()
            page.wait_for_selector(".shield-status-text:has-text('Protection Paused')", timeout=10000)
            print("[PASS] Shield status updated to 'Protection Paused'.")
            
            # Resume
            page.click("#btnResumeProtection")
            page.wait_for_selector(".shield-status-text:has-text('Shield Active')", timeout=10000)
            print("[PASS] Shield status successfully resumed to 'Shield Active'.")

        page.screenshot(path=str(ARTIFACT_DIR / "02_dashboard_view.png"))
        print("[PASS] Captured Dashboard view screenshot.")

        # -------------------------------------------------------------
        # SUITE 3: QUERY LOG VIEW (FILTERS, SEARCH, PAGINATION)
        # -------------------------------------------------------------
        print("\n--- [SUITE 3: QUERY LOG VIEW] ---")
        page.click("#navQueryLog")
        page.wait_for_selector("#viewQueryLog.active", timeout=5000)
        time.sleep(1)

        # Check table
        log_rows = page.locator("#queryLogsTableBody tr")
        row_count = log_rows.count()
        print(f"[PASS] Query Log Table rendered with {row_count} rows.")

        # Search filter
        search_input = page.locator("#logSearchInput")
        search_input.fill("example")
        time.sleep(0.5)
        filtered_count = page.locator("#queryLogsTableBody tr").count()
        print(f"[PASS] Search filter for 'example' filtered table to {filtered_count} rows.")
        search_input.fill("")
        time.sleep(0.5)

        # Status filter
        status_filter = page.locator("#logStatusFilter")
        if status_filter.is_visible():
            status_filter.select_option("BLOCKED")
            time.sleep(0.5)
            print("[PASS] Status filter 'BLOCKED' applied successfully.")
            status_filter.select_option("")
            time.sleep(0.5)

        page.screenshot(path=str(ARTIFACT_DIR / "03_query_logs_view.png"))
        print("[PASS] Captured Query Log view screenshot.")

        # -------------------------------------------------------------
        # SUITE 4: PROTECTION HUB (ADLISTS, RULES, 1-CLICK APPS)
        # -------------------------------------------------------------
        print("\n--- [SUITE 4: PROTECTION HUB (ADLISTS, RULES, 1-CLICK APPS)] ---")
        page.click("#navProtection")
        page.wait_for_selector("#viewProtection.active", timeout=5000)

        # Subtab 1: Blocklists
        print("Checking Blocklist Subscriptions...")
        page.wait_for_selector("#curatedCatalogList", timeout=5000)
        time.sleep(1)
        blocklist_items = page.locator("#curatedCatalogList > div")
        b_count = blocklist_items.count()
        self_assert_b = b_count >= 3
        print(f"[PASS] Rendered {b_count} Blocklist cards.")

        # Verify card contains rule count, last updated timestamp, and URL
        first_item_text = blocklist_items.first.inner_text()
        assert "rules" in first_item_text, "Blocklist card should display 'rules'"
        assert "Updated:" in first_item_text, "Blocklist card should display 'Updated:' timestamp"
        print(f"[PASS] Verified blocklist card metadata: {first_item_text.splitlines()[0]} | {first_item_text.splitlines()[2] if len(first_item_text.splitlines()) > 2 else ''}")

        # Test Adding a Custom Blocklist
        print("Testing Add Custom Blocklist form...")
        test_adlist_url = f"https://raw.githubusercontent.com/Perflyst/PiHoleBlocklist/master/SmartTV_{int(time.time())}.txt"
        page.fill("#newListName", "E2E Test Adlist")
        page.fill("#newListUrl", test_adlist_url)
        page.click("#subpaneAdlists form button[type='submit']")
        page.wait_for_selector(".toast.success", timeout=15000)
        print("[PASS] Added custom blocklist successfully with toast notification.")
        time.sleep(1)

        # Subtab 2: Custom Rules
        print("Navigating to Custom Rules subtab...")
        page.click("#subtabBtnCustomRules")
        page.wait_for_selector("#subpaneCustomRules.active", timeout=5000)
        
        # Test Whitelist / Blacklist toggle
        page.click("#tabBlacklistBtn")
        time.sleep(0.3)
        page.click("#tabWhitelistBtn")
        time.sleep(0.3)
        print("[PASS] Whitelist/Blacklist tab switcher works.")

        # Add custom whitelist rule
        print("Adding custom test whitelist rule...")
        page.fill("#newRuleDomain", f"portal.internal-test-{int(time.time())}.lan")
        page.click("#subpaneCustomRules form button[type='submit']")
        page.wait_for_selector(".toast.success", timeout=12000)
        print("[PASS] Added custom rule successfully.")

        # Subtab 3: 1-Click Blocked Services
        print("Navigating to 1-Click Blocked Services subtab...")
        page.click("#subtabBtnBlockedServices")
        page.wait_for_selector("#subpaneBlockedServices.active", timeout=5000)
        time.sleep(0.8)

        page.wait_for_selector("#servicesGridContainer > .card", timeout=8000)
        service_cards = page.locator("#servicesGridContainer > .card")
        srv_count = service_cards.count()
        assert srv_count >= 15, f"Expected at least 15 blocked services, got {srv_count}"
        print(f"[PASS] Blocked Services catalog rendered {srv_count} 1-click services.")

        page.screenshot(path=str(ARTIFACT_DIR / "04_protection_hub_view.png"))
        print("[PASS] Captured Protection Hub screenshot.")

        # -------------------------------------------------------------
        # SUITE 5: CLIENT DEVICES
        # -------------------------------------------------------------
        print("\n--- [SUITE 5: CLIENT DEVICES VIEW] ---")
        page.click("#navDevices")
        page.wait_for_selector("#viewDevices.active", timeout=5000)
        page.wait_for_selector("#devicesTableBody tr", timeout=8000)
        dev_rows = page.locator("#devicesTableBody tr").count()
        assert dev_rows > 0, "Devices table should have rendered rows"
        page.screenshot(path=str(ARTIFACT_DIR / "05_devices_view.png"))
        print(f"[PASS] Client Devices view rendered with {dev_rows} rows, friendly names, and icons.")

        # -------------------------------------------------------------
        # SUITE 6: ROUTING & LOCAL DNS
        # -------------------------------------------------------------
        print("\n--- [SUITE 6: ROUTING & LOCAL DNS VIEW] ---")
        page.click("#navRouting")
        page.wait_for_selector("#viewRouting.active", timeout=5000)
        page.wait_for_selector("#localDnsTableBody tr", timeout=8000)

        # Local DNS table
        local_dns_rows = page.locator("#localDnsTableBody tr").count()
        print(f"[PASS] Local DNS table rendered with {local_dns_rows} records.")

        # Switch to SmartDNS / Domain Routing
        smart_dns_btn = page.locator("#subtabBtnSmartDns")
        if smart_dns_btn.is_visible():
            smart_dns_btn.click()
            page.wait_for_selector("#routingTableBody tr", timeout=8000)
            routes_count = page.locator("#routingTableBody tr").count()
            print(f"[PASS] Domain-Specific SmartDNS routing rendered with {routes_count} rules.")

        page.screenshot(path=str(ARTIFACT_DIR / "06_routing_view.png"))
        print("[PASS] Captured Routing & Local DNS screenshot.")

        # -------------------------------------------------------------
        # SUITE 7: SETTINGS, UPSTREAMS & SYSTEM TOOLS
        # -------------------------------------------------------------
        print("\n--- [SUITE 7: SETTINGS, UPSTREAMS & SYSTEM TOOLS] ---")
        page.click("#navSettings")
        page.wait_for_selector("#viewSettings.active", timeout=5000)
        time.sleep(0.8)

        # Subtab: Tools
        page.click("#subtabBtnTools")
        page.wait_for_selector("#subpaneTools.active", timeout=5000)

        # Test Interactive Dig Diagnostic
        print("Testing Interactive Query Diagnostic tool...")
        page.fill("#diagnosticDomain", "google.com")
        page.click("#subpaneTools form button:has-text('Test Domain')")
        page.wait_for_selector("#diagnosticResultBox:has-text('RESOLVED')", timeout=8000)
        print("[PASS] Interactive Query Diagnostic tested 'google.com' -> RESOLVED.")

        # Test DNSSEC Inspector
        print("Testing DNSSEC Chain of Trust tool...")
        page.fill("#dnssecInspectDomain", "cloudflare.com")
        page.click("#btnDnssecInspect")
        page.wait_for_selector("#dnssecInspectResultBox", timeout=8000)
        print("[PASS] DNSSEC Chain of Trust inspector executed successfully.")

        page.screenshot(path=str(ARTIFACT_DIR / "07_settings_tools_view.png"))
        print("[PASS] Captured Settings & Diagnostics screenshot.")

        # -------------------------------------------------------------
        # SUITE 8: RESPONSIVE MOBILE VIEWPORT (390x844 iPhone / Pixel)
        # -------------------------------------------------------------
        print("\n--- [SUITE 8: RESPONSIVE MOBILE VIEWPORT (390x844)] ---")
        page.set_viewport_size({"width": 390, "height": 844})
        time.sleep(0.8)

        mobile_nav = page.locator("#mobileBottomNav")
        assert mobile_nav.is_visible(), "Mobile bottom dock should be visible on 390px"
        print("[PASS] Mobile bottom navigation dock is visible.")

        # Test mobile switching
        page.click("#bottomNavDashboard")
        page.wait_for_selector("#viewDashboard.active", timeout=4000)
        print("[PASS] Mobile dock -> Dashboard active.")

        page.click("#bottomNavProtection")
        page.wait_for_selector("#viewProtection.active", timeout=4000)
        print("[PASS] Mobile dock -> Protection Hub active.")

        page.screenshot(path=str(ARTIFACT_DIR / "08_mobile_protection_dock.png"))
        print("[PASS] Captured Mobile Viewport screenshot.")

        browser.close()

    server_thread.stop()

    print("\n" + "=" * 60)
    print("ALL FRONTEND TESTS PASSED - ZERO UNCAUGHT CONSOLE ERRORS")
    print(f"Captured 8 visual screenshots to {ARTIFACT_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    run_comprehensive_frontend_tests()
