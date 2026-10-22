"""Browser smoke test of the demo console: SSO login, sample upload, original-document viewer, tenant switch.

Run with `make ui-check` (uses the pinned Playwright image on the host network). Screenshots go to SCREENSHOT_DIR.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

BASE = os.environ.get("CONSOLE_URL", "http://localhost:9080")
PASSWORD = os.environ["DEMO_USER_PASSWORD"]
SHOTS = Path(os.environ.get("SCREENSHOT_DIR", "/tmp/ecotrace-ui"))
SHOTS.mkdir(parents=True, exist_ok=True)
failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("PASS " if ok else "FAIL ") + message)
    if not ok:
        failures.append(message)


def login(page: Page, user: str) -> None:
    page.goto(BASE)
    page.click("#login")
    page.fill("#username", user)
    page.fill("#password", PASSWORD)
    page.click("#kc-login")
    expect(page.locator("#app-view")).to_be_visible(timeout=20_000)


def upload_first_sample(page: Page) -> None:
    page.locator("#samples button").first.click()
    expect(page.locator("#result-card")).to_be_visible(timeout=120_000)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1366, "height": 900}, locale="vi-VN")

    login(page, "alice")
    check("Company A" in page.locator("#tenant-chip").inner_text(), "alice sees Company A after SSO login")
    page.screenshot(path=SHOTS / "1-alice-home.png", full_page=True)

    upload_first_sample(page)
    title = page.locator("#result-title").inner_text()
    check("điện" in title.lower(), f"electricity bill recognised (title: {title})")
    check("188" in page.locator("#fields-body").inner_text(), "188,800 kWh shown in the fields table")
    page.screenshot(path=SHOTS / "2-alice-result.png", full_page=True)

    if page.locator("#review-start").is_visible():
        page.click("#review-start")
        page.locator(".field-input[data-field=consumption_kwh]").fill("188800")
        page.locator(".field-input[data-field=meter_id]").fill("14567891")
        page.click("#review-save")
        expect(page.locator("#review-history")).to_be_visible(timeout=10_000)
        page.screenshot(path=SHOTS / "2b-alice-reviewed.png", full_page=True)
    check(page.locator("#result-reviewed").is_visible() or page.locator("#review-start").is_visible(),
          "document can be reviewed or shows who reviewed it")

    page.click("#view-original")
    expect(page.locator("#viewer")).to_be_visible()
    page.wait_for_timeout(1500)
    page.screenshot(path=SHOTS / "3-alice-original.png")
    page.click("#viewer-close")

    page.click("[data-lang=en]")
    page.wait_for_timeout(500)
    check(page.locator("#result-card h2, .card h2").first.inner_text() != "", "English labels rendered")
    check("Upload a document" in page.content(), "UI switched to English")
    page.screenshot(path=SHOTS / "4-alice-english.png", full_page=True)
    page.click("[data-lang=vi]")

    page.click("#logout")
    expect(page.locator("#login-view")).to_be_visible(timeout=20_000)

    login(page, "bob")
    check("Company B" in page.locator("#tenant-chip").inner_text(), "bob sees Company B after switching user")
    page.wait_for_timeout(1000)
    facilities = page.locator("#facilities").inner_text()
    check("Hai Phong" not in facilities and "Binh Duong" in facilities, "bob only sees Company B facilities")
    page.screenshot(path=SHOTS / "5-bob-home.png", full_page=True)

    page.click("#logout")
    expect(page.locator("#login-view")).to_be_visible(timeout=20_000)
    login(page, "an.tran")
    expect(page.locator("#ledger-card")).to_be_visible(timeout=15_000)
    approve = page.locator("#pending-body button.primary")
    if approve.count():
        approve.first.click()
        page.wait_for_timeout(2000)
    check(page.locator("#entries-body tr.clickable").count() > 0, "an.tran (approver) sees recorded emissions in the ledger")
    check(page.locator("#kpi-scope2").inner_text() not in ("–", "0"), f"Scope 2 total shown ({page.locator('#kpi-scope2').inner_text()} tCO2e)")
    page.screenshot(path=SHOTS / "6-ledger.png", full_page=True)
    page.locator("#entries-body tr.clickable").first.click()
    expect(page.locator("#lineage")).to_be_visible()
    lineage = page.locator("#lineage-body").inner_text()
    check(".pdf" in lineage and "an.tran" in lineage, "lineage shows the source document and the approver")
    page.screenshot(path=SHOTS / "7-lineage.png")
    page.click("#lineage-close")

    page.on("dialog", lambda dialog: dialog.accept())
    page.select_option("#ledger-period", "2026-09")
    page.wait_for_timeout(1500)
    if page.locator("#seal-close").is_visible():
        page.click("#seal-close")
        page.wait_for_timeout(4000)
    expect(page.locator("#seal-verify")).to_be_visible(timeout=15_000)
    page.click("#seal-verify")
    expect(page.locator("#verify-result")).to_be_visible(timeout=15_000)
    expected = os.environ.get("EXPECT_SEAL", "valid")
    result = page.locator("#verify-result").get_attribute("class") or ""
    check(("ok" in result) == (expected == "valid"), f"seal verification in the console shows '{expected}'")
    page.screenshot(path=SHOTS / f"8-seal-{expected}.png", full_page=True)

    browser.close()

print(f"Screenshots in {SHOTS}")
sys.exit(1 if failures else 0)
