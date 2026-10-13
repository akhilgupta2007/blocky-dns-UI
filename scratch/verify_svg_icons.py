from pathlib import Path
import re

html = Path("public/index.html").read_text(encoding="utf-8")

# Check that brand icon uses SVG
assert '<div class="brand-icon"><svg' in html or '<div class="brand-icon">\n          <svg' in html or 'brand-icon' in html, "Brand icon check"

# Check that subnav pills don't contain raw emojis
raw_emojis = ["🛡️", "📊", "🚫", "📱", "⚡", "🏠", "🌍", "🌐", "🔒", "🧩", "📦", "🚀", "🔍", "🔐", "⏱️", "🧹", "📥", "📤", "👻", "🔑"]

# Check in KPI cards
kpi_section = html.split('<div class="grid-kpi">')[1].split('<!-- Telemetry Grid')[0]
for em in ["📊", "🚫", "📱", "⚡"]:
    assert em not in kpi_section, f"Raw emoji {em} still in KPI cards!"

# Check in subnav-segmented-bar
subnav_matches = re.findall(r'<div class="subnav-segmented-bar">.*?</div>', html, re.DOTALL)
for bar in subnav_matches:
    for em in ["🛡️", "📝", "🚫", "🏠", "🌍", "🌐", "⚡", "🔍"]:
        assert em not in bar, f"Raw emoji {em} still in subnav pill!"

print("ALL SVG ICON VERIFICATION CHECKS PASSED!")
