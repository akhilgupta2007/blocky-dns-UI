from pathlib import Path

html = Path("public/index.html").read_text(encoding="utf-8")

# Check 4 pillars
assert "Monitor" in html, "Missing Monitor group in sidebar"
assert "Filtering & Rules" in html or "Filtering" in html, "Missing Filtering group in sidebar"
assert "DNS & Network" in html, "Missing DNS & Network group in sidebar"
assert "System & Tools" in html or "System" in html, "Missing System group in sidebar"

# Check nav IDs
assert 'id="navDashboard"' in html, "Missing #navDashboard"
assert 'id="navQueryLog"' in html, "Missing #navQueryLog"
assert 'id="navProtectionAdlists"' in html, "Missing #navProtectionAdlists"
assert 'id="navProtectionCustom"' in html, "Missing #navProtectionCustom"
assert 'id="navProtectionServices"' in html, "Missing #navProtectionServices"
assert 'id="navSettingsResolvers"' in html, "Missing #navSettingsResolvers"
assert 'id="navRoutingLocalDns"' in html, "Missing #navRoutingLocalDns"
assert 'id="navRoutingSmartDns"' in html, "Missing #navRoutingSmartDns"
assert 'id="navDevices"' in html, "Missing #navDevices"
assert 'id="navSettingsEngine"' in html, "Missing #navSettingsEngine"
assert 'id="navSettingsTools"' in html, "Missing #navSettingsTools"

# Check version badge
assert "v1.1.0" in html, "Missing v1.1.0 version badge"

# Check removal of duplicate dashboard-action-bar
dashboard_section = html.split('<section id="viewDashboard"')[1].split('</section>')[0]
assert 'class="dashboard-action-bar"' not in dashboard_section, \
    "Duplicate dashboard-action-bar still present on Dashboard view!"

print("ALL 4-PILLAR NAVIGATION & DASHBOARD DECLUTTER CHECKS PASSED!")
