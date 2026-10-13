from pathlib import Path

html = Path("public/index.html").read_text(encoding="utf-8")

assert 'id="headerShieldPod"' in html, "Missing #headerShieldPod in index.html"
assert 'id="btnShieldToggle"' in html, "Missing #btnShieldToggle in index.html"
assert 'id="shieldPopoverMenu"' in html, "Missing #shieldPopoverMenu in index.html"
assert 'id="headerPauseCountdown"' in html, "Missing #headerPauseCountdown in index.html"
assert 'id="btnResumeProtectionHeader"' in html, "Missing #btnResumeProtectionHeader in index.html"
assert 'handlePauseBlocking(\'1m\'' in html, "Missing 1m pause button in popover"
assert 'handlePauseBlocking(\'10m\'' in html, "Missing 10m pause button in popover"
assert 'handlePauseBlocking(\'permanent\'' in html, "Missing permanent pause button in popover"

# Ensure duplicate Change Password button was removed from header-actions
assert 'Change Password</button>' not in html.split('<header class="top-header">')[1].split('</header>')[0], \
    "Duplicate Change Password button still in top-header!"

print("ALL SHIELD POD CHECKS PASSED!")
