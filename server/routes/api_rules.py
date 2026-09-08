from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import get_connection
from auth import get_current_user
from blocky_client import sync_config_from_db, refresh_lists, flush_cache

router = APIRouter(prefix="/api/rules", tags=["rules"], dependencies=[Depends(get_current_user)])

class AddRuleRequest(BaseModel):
    rule_type: str # 'whitelist' or 'blacklist'
    domain: str
    comment: str = ""

class ImportRulesRequest(BaseModel):
    rules_text: str
    default_type: str = "blacklist"

def parse_adguard_rule(raw_line: str, default_type: str = "blacklist"):
    line = raw_line.strip()
    if not line or line.startswith("#") or line.startswith("!"):
        return None, None

    rule_type = default_type
    if line.startswith("@@"):
        rule_type = "whitelist"
        line = line[2:]
    elif line.startswith("||"):
        rule_type = "blacklist"
        line = line[2:]

    if line.startswith("||"):
        line = line[2:]

    # Strip modifiers ($important, $dnstype, etc.)
    if "$" in line:
        line = line.split("$", 1)[0]

    # Strip trailing separator /
    line = line.rstrip("^/").strip()

    # Strip URL schemes
    if line.startswith("http://"):
        line = line[7:]
    elif line.startswith("https://"):
        line = line[8:]

    line = line.split("/", 1)[0].split("?", 1)[0].strip().lower()

    if not line:
        return None, None

    return rule_type, line

@router.get("")
def list_rules():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM custom_rules ORDER BY id DESC;")
    rules = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rules

@router.post("/add")
async def add_rule(req: AddRuleRequest):
    # Parse in case user pasted an AdGuard/ABP rule (e.g. @@||domain^ or ||domain^)
    parsed_type, parsed_domain = parse_adguard_rule(req.domain, req.rule_type.lower())
    rule_type = parsed_type or req.rule_type.lower()
    domain = parsed_domain or req.domain.strip().lower()

    if not domain:
        raise HTTPException(status_code=400, detail="Domain cannot be empty")

    if rule_type not in ["whitelist", "blacklist"]:
        raise HTTPException(status_code=400, detail="Rule type must be whitelist or blacklist")

    is_wildcard = 1 if domain.startswith("*.") else 0
    is_regex = 1 if (domain.startswith("/") and domain.endswith("/")) else 0

    conn = get_connection()
    cursor = conn.cursor()
    # Check if already exists
    cursor.execute("SELECT id FROM custom_rules WHERE rule_type = ? AND domain = ?;", (rule_type, domain))
    existing = cursor.fetchone()
    if existing:
        cursor.execute("UPDATE custom_rules SET enabled = 1 WHERE id = ?;", (existing["id"],))
    else:
        cursor.execute("""
        INSERT INTO custom_rules (rule_type, domain, is_wildcard, is_regex, enabled, comment, created_at)
        VALUES (?, ?, ?, ?, 1, ?, datetime('now'));
        """, (rule_type, domain, is_wildcard, is_regex, req.comment))
    conn.commit()
    conn.close()

    sync_config_from_db()
    await refresh_lists()
    await flush_cache()
    return {"success": True, "domain": domain, "rule_type": rule_type}

@router.post("/import")
async def import_rules(req: ImportRulesRequest):
    lines = req.rules_text.splitlines()
    count_w = 0
    count_b = 0
    skipped = 0

    conn = get_connection()
    cursor = conn.cursor()

    for raw in lines:
        r_type, domain = parse_adguard_rule(raw, req.default_type)
        if not domain:
            continue

        is_wildcard = 1 if domain.startswith("*.") else 0
        is_regex = 1 if (domain.startswith("/") and domain.endswith("/")) else 0

        cursor.execute("SELECT id, enabled FROM custom_rules WHERE rule_type = ? AND domain = ?;", (r_type, domain))
        row = cursor.fetchone()
        if row:
            if row["enabled"] == 0:
                cursor.execute("UPDATE custom_rules SET enabled = 1 WHERE id = ?;", (row["id"],))
                if r_type == "whitelist":
                    count_w += 1
                else:
                    count_b += 1
            else:
                skipped += 1
        else:
            cursor.execute("""
            INSERT INTO custom_rules (rule_type, domain, is_wildcard, is_regex, enabled, comment, created_at)
            VALUES (?, ?, ?, ?, 1, 'Imported AdGuard Rule', datetime('now'));
            """, (r_type, domain, is_wildcard, is_regex))
            if r_type == "whitelist":
                count_w += 1
            else:
                count_b += 1

    conn.commit()
    conn.close()

    if count_w > 0 or count_b > 0:
        sync_config_from_db()
        await refresh_lists()
        await flush_cache()

    return {
        "success": True,
        "added_whitelist": count_w,
        "added_blacklist": count_b,
        "total_added": count_w + count_b,
        "skipped": skipped
    }

@router.delete("/{target}")
async def delete_rule(target: str):
    conn = get_connection()
    cursor = conn.cursor()
    target_clean = target.strip()
    if target_clean.isdigit():
        cursor.execute("DELETE FROM custom_rules WHERE id = ?;", (int(target_clean),))
    else:
        cursor.execute("DELETE FROM custom_rules WHERE domain = ?;", (target_clean.lower(),))
    conn.commit()
    conn.close()

    sync_config_from_db()
    await refresh_lists()
    await flush_cache()
    return {"success": True}
