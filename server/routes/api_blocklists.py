from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
import httpx
import asyncio
from database import get_connection
from auth import get_current_user
from blocky_client import sync_config_from_db, refresh_lists, flush_cache

router = APIRouter(prefix="/api/blocklists", tags=["blocklists"], dependencies=[Depends(get_current_user)])

class AddBlocklistRequest(BaseModel):
    name: str
    url: str
    category: str = "Custom"

class ToggleRequest(BaseModel):
    id: int
    enabled: bool

async def count_rules_from_url(url: str) -> int:
    """Streams and counts valid DNS blocking rules from a remote hosts/domain list URL."""
    count = 0
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    print(f"[Blocklist Counter] HTTP {resp.status_code} when fetching {url}")
                    return 0
                async for line in resp.aiter_lines():
                    clean = line.strip()
                    if not clean or clean.startswith("#") or clean.startswith("!") or clean.startswith("//"):
                        continue
                    parts = clean.split()
                    # If hosts format: 0.0.0.0 example.com or 127.0.0.1 example.com
                    if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1", "::", "::1"):
                        domain = parts[1].strip()
                        if domain in ("localhost", "localhost.localdomain", "broadcasthost", "local"):
                            continue
                    count += 1
    except Exception as e:
        print(f"[Blocklist Counter] Error counting rules for {url}: {e}")
        return 0
    return count

async def refresh_single_blocklist_stats(list_id: int, url: str):
    """Fetches rule count for a single blocklist and updates SQLite."""
    count = await count_rules_from_url(url)
    if count > 0:
        try:
            conn = get_connection()
            conn.execute("""
            UPDATE blocklists 
            SET rule_count = ?, last_updated = datetime('now') 
            WHERE id = ?;
            """, (count, list_id))
            conn.commit()
            conn.close()
            print(f"[Blocklist Counter] Successfully updated list #{list_id} with {count:,} rules.")
        except Exception as e:
            print(f"[Blocklist Counter] Database update error for list #{list_id}: {e}")

async def refresh_all_blocklists_stats():
    """Background job to re-count rules for all enabled blocklists."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, url FROM blocklists WHERE enabled = 1;")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        for row in rows:
            await refresh_single_blocklist_stats(row["id"], row["url"])
    except Exception as e:
        print(f"[Blocklist Counter] Error in refresh_all_blocklists_stats: {e}")

_counting_active = False

@router.get("")
async def list_blocklists(background_tasks: BackgroundTasks):
    global _counting_active
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blocklists ORDER BY id ASC;")
    lists = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # Automatically trigger a background rule count for any list currently having 0 rules
    uncounted = [l for l in lists if (l.get("rule_count") or 0) == 0 and l.get("enabled")]
    if uncounted and not _counting_active:
        _counting_active = True
        async def _run_uncounted():
            global _counting_active
            try:
                for item in uncounted:
                    await refresh_single_blocklist_stats(item["id"], item["url"])
            finally:
                _counting_active = False
        background_tasks.add_task(_run_uncounted)

    return lists

@router.post("/toggle")
async def toggle_blocklist(req: ToggleRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE blocklists SET enabled = ? WHERE id = ?;", (1 if req.enabled else 0, req.id))
    conn.commit()
    conn.close()

    sync_config_from_db()
    await refresh_lists()
    await flush_cache()
    return {"success": True}

@router.post("/add")
async def add_blocklist(req: AddBlocklistRequest, background_tasks: BackgroundTasks):
    url = req.url.strip()
    name = req.name.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Blocklist URL must start with http:// or https://")

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT OR REPLACE INTO blocklists (name, url, category, enabled, rule_count, last_updated)
        VALUES (?, ?, ?, 1, 0, datetime('now'));
        """, (name, url, req.category))
        conn.commit()
        cursor.execute("SELECT id FROM blocklists WHERE url = ?;", (url,))
        row = cursor.fetchone()
        new_id = row["id"] if row else None
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Failed to save blocklist: {e}")
    conn.close()

    sync_config_from_db()
    await refresh_lists()
    await flush_cache()

    if new_id:
        background_tasks.add_task(refresh_single_blocklist_stats, new_id, url)

    return {"success": True}

@router.delete("/{target:path}")
async def delete_blocklist(target: str):
    conn = get_connection()
    cursor = conn.cursor()
    target_clean = target.strip()
    if target_clean.isdigit():
        cursor.execute("DELETE FROM blocklists WHERE id = ?;", (int(target_clean),))
    else:
        cursor.execute("DELETE FROM blocklists WHERE url = ? OR name = ?;", (target_clean, target_clean))
    conn.commit()
    conn.close()

    sync_config_from_db()
    await refresh_lists()
    await flush_cache()
    return {"success": True}

@router.post("/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    sync_config_from_db()
    ok = await refresh_lists()
    await flush_cache()

    # Update last_updated immediately in SQLite
    try:
        conn = get_connection()
        conn.execute("UPDATE blocklists SET last_updated = datetime('now') WHERE enabled = 1;")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Blocklist] Failed to update last_updated: {e}")

    background_tasks.add_task(refresh_all_blocklists_stats)
    return {"success": ok}
