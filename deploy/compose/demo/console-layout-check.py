# SPDX-FileCopyrightText: 2026 EcoTrace contributors
# SPDX-License-Identifier: Apache-2.0
"""Test the real console against API fixtures, without a running service stack.

Run: python deploy/compose/demo/console-layout-check.py
Requires Playwright and Chromium. This complements ui-check.py's live SSO checks.
"""

from __future__ import annotations

import base64
import copy
import json
import mimetypes
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "capabilities/demo-console/public"
SHOTS = Path(os.environ.get("SCREENSHOT_DIR", Path(tempfile.gettempdir()) / "ecotrace-console-layout"))
LABEL = {"vi": "Hoá đơn điện", "en": "Electricity bill"}
DOC = {
    "id": "fixture-document", "filename": "electricity-bill-2026-09.xml",
    "created_at": "2026-09-30T08:00:00Z", "document_type_label": LABEL,
    "type_confidence": 1, "extractor": "einvoice-xml", "status": "needs_review",
    "sha256": "a" * 64, "uploaded_by": "alice", "content_type": "image/png",
}
RESULT = {
    "document": DOC,
    "fields": [{"name": "consumption_kwh", "label": {"vi": "Điện tiêu thụ", "en": "Consumption"},
                "value": "188800", "type": "number", "unit": "kWh", "confidence": .7, "needs_review": True}],
    "pipeline": [{"step": step, "status": "ok", "detail": "", "ms": 1}
                 for step in ("gateway", "scan", "store", "classify", "extract", "persist", "publish")],
    "reviews": [],
}
ENTRY = {"id": "fixture-entry", "period": "2026-09", "source_id": "electricity",
         "quantity": 188800, "unit": "kWh", "scope": 2, "co2e_kg": 128572.8}
TASK = {"id": "fixture-task", "name": "Trưởng bộ phận", "process_key": "verify-activity",
        "summary": "Electricity bill", "created": "2026-09-30T08:00:00Z", "decisions": [],
        "document_id": DOC["id"]}


class Fixture:
    def __init__(self, modules=True):
        self.modules = modules
        self.result = copy.deepcopy(RESULT)
        self.tasks = [copy.deepcopy(TASK)]
        self.period = {"period": "2026-09", "status": "open"}
        self.requests = []

    def route(self, route):
        request = route.request
        path = urlparse(request.url).path
        self.requests.append((request.method, path))
        data = None
        if path == "/intake/me":
            data = {"tenant_id": "company-a-steel", "tenant_name": "Company A — Steel",
                    "review_threshold": .85, "document_types": [{"id": "electricity_bill", "label": LABEL}],
                    "ai": {"enabled": False}}
        elif path.endswith("/manifest.json"):
            data = [{"file": "electricity.xml", "title": LABEL}]
        elif path == "/intake/documents":
            data = self.result if request.method == "POST" else {"documents": [self.result["document"]]}
        elif path.endswith("/review"):
            self.result["document"].update(status="reviewed", reviewed_by="alice", reviewed_at="2026-09-30T09:00:00Z")
            field = self.result["fields"][0]
            new_value = request.post_data_json["values"]["consumption_kwh"]
            self.result["reviews"] = [{"name": field["name"], "old_value": field["value"],
                                       "new_value": new_value, "reviewed_by": "alice",
                                       "reviewed_at": "2026-09-30T09:00:00Z"}]
            field.update(value=new_value, needs_review=False, confidence=1)
            data = self.result
        elif path == f"/intake/documents/{DOC['id']}":
            data = self.result
        elif path.endswith("/file"):
            route.fulfill(content_type="image/png", body=base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII="))
            return
        elif path == "/v1/graphql":
            data = {"data": {"core_facility": [{"name": "Hai Phong Steel", "kind": "factory"}]}}
        elif path == "/workflow/tasks":
            data = {"tasks": self.tasks}
        elif path.endswith("/complete"):
            self.tasks = []
            data = {"process_finished": True}
        elif path == "/ledger/activities":
            data = {"activities": [], "can_approve": True, "can_close": True, "workflow": True}
        elif path == "/ledger/summary":
            data = {"scope1_kg": 0, "scope2_kg": 128572.8, "entries": [ENTRY], "periods": [self.period]}
        elif path == "/ledger/trend":
            data = {"by_period": [{"period": "2026-09", "scope": 2, "co2e_kg": 128572.8}],
                    "by_facility": [{"facility": "Hai Phong Steel", "co2e_kg": 128572.8}]}
        elif path == "/ledger/stream":
            route.fulfill(content_type="text/event-stream", body=": ready\n\n")
            return
        elif path == "/purchase/requests":
            data = {"requests": []}
        elif path.endswith("/close"):
            self.period.update(status="closed", entry_count=1, leaf_index=0, tree_size=1,
                               root_hash="a" * 64, closed_by="an.tran")
            data = {}
        elif path.endswith("/verify"):
            data = {"valid": True, "changed": [], "removed": [], "added": [], "entry_count": 1,
                    "leaf_index": 0, "tree_size": 1, "root_hash": "a" * 64}
        elif path.endswith("/lineage"):
            data = {"document": self.result["document"], "corrections": [], "entry": {
                **ENTRY, "factor_value": .681, "factor_unit": "kgCO2e/kWh", "factor_version": "fixture-v1",
                "factor_source": "Fixture only", "factor_status": "provisional"},
                "activity": {**ENTRY, "source_name": "Electricity", "facility_code": "HP",
                             "decided_by": "an.tran", "decided_at": "2026-09-30T09:00:00Z"}, "period": self.period}
        elif path == "/ledger/report":
            route.fulfill(content_type="text/csv", body="period,co2e_kg\n2026-09,128572.8\n")
            return
        else:
            relative = "index.html" if path == "/" else path.lstrip("/")
            file = (STATIC / relative).resolve()
            if file.is_relative_to(STATIC.resolve()) and file.is_file():
                content_type = "text/javascript" if file.suffix == ".js" else mimetypes.guess_type(file.name)[0]
                route.fulfill(content_type=content_type or "application/octet-stream", body=file.read_bytes())
            elif path.startswith("/samples/"):
                route.fulfill(content_type="application/xml", body="<fixture/>")
            else:
                route.fulfill(status=404, body="Unexpected fixture request: " + path)
            return
        if not self.modules and path.startswith(("/ledger/", "/purchase/")):
            route.fulfill(status=403, json={"detail": "Module disabled"})
        else:
            route.fulfill(json=data)


def open_console(browser, fixture):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.route("https://fonts.googleapis.com/**", lambda route: route.abort())
    page.route("http://console.test/**", fixture.route)
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + 3600,
                                                 "preferred_username": "alice"}).encode()).decode().rstrip("=")
    token = json.dumps({"access_token": f"fixture.{payload}.fixture"})
    page.add_init_script(f"sessionStorage.setItem('tokens', {json.dumps(token)});")
    page.goto("http://console.test/")
    expect(page.locator("#app-view")).to_be_visible()
    expect(page.locator("#approvals-count")).to_have_text("1")
    return page


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        fixture = Fixture()
        page = open_console(browser, fixture)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        SHOTS.mkdir(parents=True, exist_ok=True)

        # Exercise the real file-picker handler and review controls after the layout change.
        page.locator("#file-input").set_input_files({"name": "electricity.xml", "mimeType": "application/xml", "buffer": b"<fixture/>"})
        expect(page.locator("#result-card")).to_be_visible()
        expect(page.locator("#fields-body tr.review")).to_have_count(1)
        page.locator("#review-start").click()
        page.locator(".field-input").fill("188801")
        page.locator("#review-save").click()
        expect(page.locator("#review-history")).to_be_visible()
        page.locator("#view-original").click()
        expect(page.locator("#viewer")).to_be_visible()
        page.locator("#viewer-close").click()

        for width in (360, 375, 600, 768, 1024, 1440):
            page.set_viewport_size({"width": width, "height": 1000})
            for screen in ("upload", "approvals", "ledger", "purchases", "documents", "facilities"):
                page.locator(f'[data-screen-link="{screen}"]').click()
                expect(page.locator("#app-view")).to_have_attribute("data-active-screen", screen)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, screen, "horizontal overflow")
                assert page.locator("h1:visible").count() == 1
                assert page.locator("button:visible").evaluate_all(
                    "buttons => buttons.every(b => b.getBoundingClientRect().height >= 44)"), (width, screen, "small button")
                if width in (360, 1440) and screen in ("upload", "ledger"):
                    page.screenshot(path=SHOTS / f"{screen}-{width}.png", full_page=True)

        page.locator('[data-screen-link="documents"]').click()
        page.locator("#documents-body tr.clickable").click()
        expect(page.locator("#result-card")).to_be_visible()
        expect(page.locator("#app-view")).to_have_attribute("data-active-screen", "upload")
        page.locator('[data-screen-link="approvals"]').click()
        page.locator("#inbox-list button.primary").click()
        expect(page.locator("#approvals-count")).to_have_text("0")
        page.locator('[data-screen-link="ledger"]').click()
        page.locator('[data-lang="en"]').click()
        expect(page.locator("html")).to_have_attribute("lang", "en")
        expect(page.locator("#screen-title")).to_have_text(page.locator('[data-screen-link="ledger"] [data-i18n]').inner_text())
        page.locator("#ledger-period").select_option("2026-09")
        expect(page.locator("#seal-panel")).to_be_visible()
        page.on("dialog", lambda dialog: dialog.accept())
        page.locator("#seal-close").click()
        expect(page.locator("#seal-verify")).to_be_visible()
        page.locator("#seal-verify").click()
        expect(page.locator("#verify-result.ok")).to_be_visible()
        page.locator("#entries-body tr.clickable").click()
        expect(page.locator("#lineage")).to_be_visible()
        expect(page.locator("#lineage-body")).to_contain_text("188,800 kWh × 0.681")
        page.locator("#lineage-close").click()
        with page.expect_download():
            page.locator("#export-csv").click()
        page.reload()
        expect(page.locator("#app-view")).to_have_attribute("data-active-screen", "ledger")
        assert page.evaluate("scrollY == 0"), "deep-link reload must keep the header and menu in view"
        page.locator('[data-screen-link="facilities"]').click()
        page.go_back()
        expect(page.locator("#app-view")).to_have_attribute("data-active-screen", "ledger")
        assert not errors, errors

        restricted = open_console(browser, Fixture(modules=False))
        expect(restricted.locator('[data-screen-link="purchases"]')).to_be_hidden()
        expect(restricted.locator('[data-screen-link="ledger"]')).to_be_hidden()
        restricted.goto("http://console.test/#ledger")
        expect(restricted.locator("#app-view")).to_have_attribute("data-active-screen", "upload")
        browser.close()

    print("PASS console navigation, upload/review, module visibility, exports, seal and lineage")
    print("PASS no page overflow and 44px buttons: six screens at six viewport widths")
    print(f"Fixture screenshots: {SHOTS}")


if __name__ == "__main__":
    main()
