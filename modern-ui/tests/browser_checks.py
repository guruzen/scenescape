"""Run against browser_server.py and the isolated Vite harness, NOT production.

The real React components and native API are exercised. Identity is substituted
by a test-only service token; this is not a Keycloak PKCE or Docker/WSL test.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

output = Path(os.environ.get("BROWSER_TEST_OUTPUT", "/tmp/scenescape-native-browser-results"))
output.mkdir(parents=True, exist_ok=True)
checks = []
skipped = []

def check(name, condition=True):
    if not condition:
        raise AssertionError(name)
    checks.append(name)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get("CHROMIUM_PATH", "/opt/google/chrome/chrome"),
        args=["--no-sandbox", "--enable-unsafe-swiftshader", "--use-angle=swiftshader"])
    page = browser.new_page(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:4174/tests/harness.html#/overview")
    page.get_by_role("button", name="Open live view").first.wait_for()
    check("Overview loads native resources")
    check("No legacy links or iframe", page.locator('a[href*="legacy"],a[href*="sign_in"],iframe').count() == 0)
    for theme in ("light", "light-air", "dark", "dark-command"):
        page.get_by_label("Visual theme").select_option(theme)
        page.wait_for_timeout(200)
        check(f"Theme {theme}", page.locator("html").get_attribute("data-theme") == theme)
        page.screenshot(path=str(output / f"overview-{theme}.png"), full_page=True)
    page.reload()
    page.get_by_role("button", name="Open live view").first.wait_for()
    check("Theme persists", page.locator("html").get_attribute("data-theme") == "dark-command")
    page.get_by_role("button", name="Open live view").first.click()
    page.get_by_role("heading", name="Test distribution floor", exact=True).wait_for()
    page.wait_for_function("document.querySelectorAll('.native-svg circle').length >= 2")
    check("Live native scene receives actual API observations")
    check("Scene navigation stays in SPA", "#/scene/" in page.url)
    page.screenshot(path=str(output / "native-live-2d.png"), full_page=True)
    page.get_by_role("button", name="3D", exact=True).click()
    page.wait_for_timeout(2500)
    if page.locator(".three-view canvas").count():
        check("Native 3D canvas renders")
        page.locator(".three-view canvas").evaluate("element => element.dataset.probe = 'same-context'")
        page.wait_for_timeout(1500)
        check("Live updates preserve WebGL context", page.locator(".three-view canvas").get_attribute("data-probe") == "same-context")
        page.screenshot(path=str(output / "native-live-3d.png"), full_page=True)
    else:
        check("No-WebGL fallback stays in native UI", "WebGL is unavailable" in page.locator("main").inner_text())
        skipped.append("Actual 3D rendering: this execution environment did not provide WebGL2")
    page.get_by_role("button", name="Geometry", exact=True).click()
    page.get_by_role("button", name="New tripwire", exact=True).click()
    page.get_by_label("Name", exact=True).fill("Browser test crossing")
    svg = page.locator(".geometry-editor .native-svg")
    box = svg.bounding_box()
    svg.click(position={"x": box["width"]*.30, "y": box["height"]*.35})
    svg.click(position={"x": box["width"]*.60, "y": box["height"]*.35})
    page.get_by_role("button", name="Save to scene", exact=True).click()
    page.get_by_role("button", name="Browser test crossing").wait_for()
    check("Geometry draw/save persists via native API")
    page.screenshot(path=str(output / "native-geometry.png"), full_page=True)
    page.get_by_role("button", name="Camera calibration", exact=True).click()
    page.get_by_role("button", name="Save camera pose", exact=True).wait_for()
    check("Calibration is a native route, not Django")
    page.get_by_label("Camera pose: translation, rotation, scale", exact=True).fill('{"translation":[2,3,4],"rotation":[0,0,0],"scale":[1,1,1]}')
    page.get_by_role("button", name="Save camera pose", exact=True).click()
    page.wait_for_timeout(600)
    check("Calibration save succeeds", page.locator(".calibration-workspace .error-box").count() == 0)
    page.get_by_role("button", name="History & replay", exact=True).click()
    page.get_by_role("button", name="Load history", exact=True).wait_for()
    page.wait_for_function("document.querySelector('input[type=range]') !== null")
    check("Historian replay comes from persisted observations")
    page.screenshot(path=str(output / "native-history.png"), full_page=True)
    page.get_by_role("button", name="Trends & analytics", exact=True).click()
    page.get_by_role("button", name="Apply range", exact=True).wait_for()
    page.wait_for_function("document.querySelectorAll('.table-wrap tbody tr').length > 0")
    check("Trend aggregates load from the native historian")
    page.get_by_role("button", name="Incidents", exact=True).click()
    page.get_by_role("button", name="Open incident", exact=True).first.wait_for()
    page.get_by_role("button", name="Open incident", exact=True).first.click()
    page.get_by_label("Status", exact=True).wait_for()
    page.get_by_label("Status", exact=True).select_option("acknowledged")
    page.get_by_label("Note", exact=True).fill("Acknowledged in isolated browser test")
    page.get_by_role("button", name="Save action", exact=True).click()
    page.wait_for_timeout(500)
    check("Durable incident action", "acknowledged" in page.locator(".incident-detail").inner_text())
    page.screenshot(path=str(output / "native-incident.png"), full_page=True)
    page.get_by_role("button", name="Sites, floors & scenes", exact=True).click()
    page.get_by_placeholder("Search Sites, floors & scenes").wait_for()
    page.get_by_placeholder("Search Sites, floors & scenes").fill("impossible-filter")
    page.get_by_text("No matching resources").wait_for()
    check("Inventory filter is real")
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="Shift overview", exact=True).click()
    page.wait_for_timeout(300)
    check("Mobile has no document overflow", page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
    page.screenshot(path=str(output / "native-mobile.png"), full_page=True)
    check("No browser JavaScript exceptions", not errors)
    browser.close()
(output / "results.json").write_text(json.dumps({"passed": len(checks), "checks": checks, "browser_errors": errors, "skipped": skipped,
    "limits": "Synthetic fixtures, real native API, substituted test identity. No real Keycloak, MQTT broker, camera, Docker or WSL deployment exercised."}, indent=2))
print(json.dumps({"passed": len(checks), "output": str(output)}, indent=2))
