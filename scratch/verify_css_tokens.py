import re
from pathlib import Path

css_path = Path("public/css/style.css")
content = css_path.read_text(encoding="utf-8")

# Check 1: --bg-main is #0b0f17
assert "--bg-main: #0b0f17;" in content, "Missing --bg-main: #0b0f17;"

# Check 2: --bg-card is #111622
assert "--bg-card: #111622;" in content, "Missing --bg-card: #111622;"

# Check 3: --inner-rim is defined
assert "--inner-rim" in content, "Missing --inner-rim definition;"

# Check 4: .card should NOT have backdrop-filter: blur
card_match = re.search(r"\.card\s*\{([^}]+)\}", content)
assert card_match, "Could not find .card rule in style.css"
card_body = card_match.group(1)
assert "backdrop-filter" not in card_body, ".card still contains backdrop-filter!"

# Check 5: tabular-nums should be enabled
assert "tabular-nums" in content, "Missing tabular-nums rule in style.css"

print("ALL CSS TOKEN CHECKS PASSED!")
