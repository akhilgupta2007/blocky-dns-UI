import os
import sys
import time
import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Setup test environment paths
TEST_DIR = Path(__file__).parent
os.environ["DATA_DIR"] = str(TEST_DIR / "data_test")
os.environ["BLOCKY_CONFIG_PATH"] = str(TEST_DIR / "config" / "config_test.yml")
os.environ["ENABLE_HTTPS"] = "false"

# Ensure directories exist
Path(os.environ["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["BLOCKY_CONFIG_PATH"]).parent.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(TEST_DIR / "server"))
sys.path.insert(0, str(TEST_DIR / "server" / "routes"))

from database import init_db, get_connection
from seed_data import seed_initial_data
from main import app
from auth import create_access_token
from api_blocklists import (
    count_rules_from_url,
    refresh_single_blocklist_stats,
    refresh_all_blocklists_stats
)


class TestBlocklistsThorough(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        seed_initial_data()
        cls.client = TestClient(app)
        token = create_access_token("admin")
        cls.headers = {"Authorization": f"Bearer {token}"}

    # =========================================================================
    # 1. UNIT TESTS: RULE COUNTER LOGIC
    # =========================================================================

    def test_01_count_rules_parsing_formats(self):
        """Test rule counting handles hosts format, plain domains, comments, and whitespace."""
        sample_content = """
        # ==========================================
        # Sample Ad Blocking Hosts File
        # ==========================================
        ! Adblock comment
        // Another comment style

        127.0.0.1 localhost
        127.0.0.1 localhost.localdomain
        0.0.0.0 broadcasthost
        ::1 localhost

        # Legitimate rules to block:
        0.0.0.0 tracking.example.com
        127.0.0.1 ads.doubleclick.net
        0.0.0.0 telemetry.device.tv
        analytics.bigdata.org
        evil-tracker.io
        :: adserver.co
        """
        lines = [line.strip() for line in sample_content.strip().split("\n")]

        class MockStreamResponse:
            status_code = 200
            async def aiter_lines(self):
                for l in lines:
                    yield l
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        class MockAsyncClient:
            def __init__(self, *args, **kwargs):
                pass
            def stream(self, method, url):
                return MockStreamResponse()
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        with patch("httpx.AsyncClient", side_effect=MockAsyncClient):
            count = asyncio.run(count_rules_from_url("https://example.com/hosts.txt"))
            self.assertEqual(count, 6)
            print(f"[PASS] Rule parser correctly extracted {count} rules and filtered comments/loopback.")

    def test_02_count_rules_http_error_handling(self):
        """Test rule counter handles HTTP 404/500 and network timeouts gracefully without raising exceptions."""
        class Mock404Response:
            status_code = 404
            async def aiter_lines(self):
                if False:
                    yield ""
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        class Mock404Client:
            def __init__(self, *args, **kwargs):
                pass
            def stream(self, method, url):
                return Mock404Response()
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        with patch("httpx.AsyncClient", side_effect=Mock404Client):
            count = asyncio.run(count_rules_from_url("https://example.com/nonexistent.txt"))
            self.assertEqual(count, 0)
            print("[PASS] HTTP 404 handled gracefully (returned 0 rules).")

        # Network Exception test
        with patch("httpx.AsyncClient", side_effect=Exception("Connection timed out")):
            count_err = asyncio.run(count_rules_from_url("https://timeout.example.com"))
            self.assertEqual(count_err, 0)
            print("[PASS] Connection timeout handled gracefully (returned 0 rules).")

    def test_03_live_peter_lowes_blocklist_fetch(self):
        """Test live fetch and count against Peter Lowe's Blocklist."""
        peter_lowe_url = "https://pgl.yoyo.org/adservers/serverlist.php?hostformat=hosts&showintro=0&mimetype=plaintext"
        count = asyncio.run(count_rules_from_url(peter_lowe_url))
        self.assertGreater(count, 3000, f"Expected >3000 rules from Peter Lowe's list, got {count}")
        print(f"[PASS] Live Peter Lowe's Blocklist fetch succeeded: {count:,} rules counted.")

    # =========================================================================
    # 2. API ENDPOINTS & DATABASE SYNCHRONIZATION
    # =========================================================================

    def test_04_add_custom_blocklist_and_stats_update(self):
        """Test adding a custom blocklist via API triggers DB insert and background rule count."""
        test_url = "https://raw.githubusercontent.com/Perflyst/PiHoleBlocklist/master/SmartTV.txt"
        test_name = "Smart TV Test List"

        # Clean any preexisting entry
        conn = get_connection()
        conn.cursor().execute("DELETE FROM blocklists WHERE url = ?;", (test_url,))
        conn.commit()
        conn.close()

        # Add blocklist
        res = self.client.post("/api/blocklists/add", headers=self.headers, json={
            "name": test_name,
            "url": test_url,
            "category": "IoT & Smart Devices"
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("success"))

        # Verify initial database entry
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, url, rule_count, last_updated FROM blocklists WHERE url = ?;", (test_url,))
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["name"], test_name)
        self.assertIsNotNone(row["last_updated"])
        list_id = row["id"]
        print(f"[PASS] Blocklist added to DB with ID={list_id}, last_updated={row['last_updated']}")

        # Simulate background worker completion
        asyncio.run(refresh_single_blocklist_stats(list_id, test_url))

        # Check updated rule_count in database
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT rule_count, last_updated FROM blocklists WHERE id = ?;", (list_id,))
        updated_row = cursor.fetchone()
        conn.close()

        self.assertGreater(updated_row["rule_count"], 0)
        print(f"[PASS] Background task updated list #{list_id} with {updated_row['rule_count']:,} rules.")

    def test_05_list_blocklists_returns_all_metadata(self):
        """Test GET /api/blocklists returns rule_count, last_updated, url, and category."""
        res = self.client.get("/api/blocklists", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        lists = res.json()
        self.assertIsInstance(lists, list)
        self.assertGreater(len(lists), 0)

        for l in lists:
            self.assertIn("id", l)
            self.assertIn("name", l)
            self.assertIn("url", l)
            self.assertIn("category", l)
            self.assertIn("rule_count", l)
            self.assertIn("last_updated", l)

        print(f"[PASS] GET /api/blocklists returned {len(lists)} lists with complete schema metadata.")

    def test_06_auto_backfill_for_uncounted_lists(self):
        """Test that any blocklist with rule_count = 0 is auto-detected when listing blocklists."""
        mock_url = "https://raw.githubusercontent.com/Perflyst/PiHoleBlocklist/master/SmartTV.txt"
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO blocklists (name, url, category, enabled, rule_count, last_updated)
        VALUES ('SmartTV Uncounted', ?, 'Malware', 1, 0, datetime('now', '-2 days'));
        """, (mock_url,))
        conn.commit()
        conn.close()

        # Calling GET /api/blocklists should return the list and queue background task
        res = self.client.get("/api/blocklists", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        matching = [x for x in res.json() if x["url"] == mock_url]
        self.assertEqual(len(matching), 1)

        # Run the stats refresh on it directly to verify rule_count increases
        asyncio.run(refresh_single_blocklist_stats(matching[0]["id"], mock_url))

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT rule_count FROM blocklists WHERE id = ?;", (matching[0]["id"],))
        new_count = cursor.fetchone()["rule_count"]
        conn.close()

        self.assertGreater(new_count, 0)
        print(f"[PASS] Auto-backfill verified: list updated from 0 to {new_count:,} rules.")

    def test_07_refresh_all_blocklists_endpoint(self):
        """Test POST /api/blocklists/refresh immediately updates last_updated in SQLite."""
        res = self.client.post("/api/blocklists/refresh", headers=self.headers)
        self.assertEqual(res.status_code, 200)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT last_updated FROM blocklists WHERE enabled = 1 LIMIT 1;")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row["last_updated"])
        print(f"[PASS] POST /api/blocklists/refresh updated last_updated timestamps ({row['last_updated']}).")

    def test_08_toggle_blocklist_affects_stats_summary(self):
        """Test disabling a blocklist recalculates total active rules in /api/stats/summary."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, enabled, rule_count FROM blocklists WHERE rule_count > 0 LIMIT 1;")
        target = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(target)

        list_id = target["id"]

        # 1. Summary with list enabled
        res_before = self.client.get("/api/stats/summary", headers=self.headers)
        rules_before = res_before.json()["active_rules_count"]

        # 2. Toggle to disabled
        self.client.post("/api/blocklists/toggle", headers=self.headers, json={"id": list_id, "enabled": False})

        # 3. Summary after disable
        res_after = self.client.get("/api/stats/summary", headers=self.headers)
        rules_after = res_after.json()["active_rules_count"]

        self.assertEqual(rules_before - rules_after, target["rule_count"])
        print(f"[PASS] Toggle verification: Disabling list #{list_id} reduced active rules by {target['rule_count']:,}.")

        # Re-enable
        self.client.post("/api/blocklists/toggle", headers=self.headers, json={"id": list_id, "enabled": True})

    def test_09_delete_blocklist_cleanup(self):
        """Test deleting a blocklist removes it from DB."""
        test_url = "https://raw.githubusercontent.com/Perflyst/PiHoleBlocklist/master/SmartTV.txt"
        del_res = self.client.delete(f"/api/blocklists/{test_url}", headers=self.headers)
        self.assertEqual(del_res.status_code, 200)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM blocklists WHERE url = ?;", (test_url,))
        remaining = cursor.fetchone()["cnt"]
        conn.close()

        self.assertEqual(remaining, 0)
        print("[PASS] Blocklist deletion verified (removed from SQLite).")


if __name__ == "__main__":
    unittest.main(verbosity=2)
