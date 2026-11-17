# SPDX-FileCopyrightText: 2026 EcoTrace contributors
# SPDX-License-Identifier: Apache-2.0
"""Check the real landing page, locale parity, links and responsive behavior.

Run: python tools/site-check.py
Requires the pinned Playwright/Chromium setup used by the console checks.
"""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
import tempfile
from urllib.parse import unquote, urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SHOTS = Path(os.environ.get("SCREENSHOT_DIR", Path(tempfile.gettempdir()) / "ecotrace-site-layout"))
BASE = "http://site.test/greendx/"
SCREENS = (360, 375, 600, 768, 1024, 1440)


def static_route(route):
    relative = unquote(urlsplit(route.request.url).path).removeprefix("/greendx/") or "index.html"
    file = (SITE / relative).resolve()
    if not file.is_relative_to(SITE.resolve()) or not file.is_file():
        route.fulfill(status=404, body="Unknown static asset")
        return
    mime = "text/javascript" if file.suffix == ".js" else mimetypes.guess_type(file.name)[0]
    route.fulfill(content_type=mime or "application/octet-stream", body=file.read_bytes())


def main():
    dictionaries = {language: json.loads((SITE / f"i18n/{language}.json").read_text(encoding="utf-8"))
                    for language in ("vi", "en")}
    assert dictionaries["vi"].keys() == dictionaries["en"].keys(), "locale keys differ"
    assert all(isinstance(value, str) and value.strip() for dictionary in dictionaries.values()
               for value in dictionary.values()), "empty locale message"
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("https://fonts.googleapis.com/**", lambda route: route.abort())
        page.route(BASE + "**", static_route)
        page.goto(BASE)
        expect(page.locator('[data-lang="en"]')).to_be_enabled()
        used_keys = page.locator("[data-i18n], [data-i18n-aria]").evaluate_all(
            "elements => elements.flatMap(e => [e.dataset.i18n, e.dataset.i18nAria].filter(Boolean))")
        assert not (set(used_keys) - dictionaries["vi"].keys()), "untranslated message key"
        assert page.locator("h1").count() == 1
        assert page.locator(".steps li").count() == 6
        assert page.locator("main > section").evaluate_all("sections => sections.map(s => s.id)") == [
            "", "problem", "how", "traceability", "roles", "architecture", "faq", "run"]
        for href in page.locator('a[href^="#"]').evaluate_all("links => links.map(a => a.getAttribute('href'))"):
            assert page.locator(href).count() == 1, f"missing anchor {href}"
        hrefs = page.locator("a[href]").evaluate_all("links => links.map(a => a.getAttribute('href'))")
        assert "api/" in hrefs
        for document in ("docs/install.md", "docs/licenses.md"):
            assert any(href.endswith(document) for href in hrefs), document

        SHOTS.mkdir(parents=True, exist_ok=True)
        for language in ("vi", "en"):
            page.locator(f'[data-lang="{language}"]').click()
            expect(page.locator("html")).to_have_attribute("lang", language)
            expect(page.locator("h1")).to_have_text(dictionaries[language]["hero.title"])
            expect(page.locator('[data-number="188800"]')).to_have_text(
                "188.800 kWh" if language == "vi" else "188,800 kWh")
            for width in SCREENS:
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (language, width)
                assert page.locator("button").evaluate_all(
                    "buttons => buttons.every(b => b.getBoundingClientRect().height >= 44)")
                for table in page.locator(".table-scroll").all():
                    assert table.evaluate("e => e.clientWidth <= innerWidth"), (language, width)
                if width in (360, 1440):
                    page.screenshot(path=SHOTS / f"landing-{language}-{width}.png", full_page=True)

        page.locator("summary").first.focus()
        page.keyboard.press("Enter")
        expect(page.locator("details").first).to_have_attribute("open", "")
        page.reload()
        expect(page.locator("html")).to_have_attribute("lang", "en")
        # A missing locale must not blank or partially translate the document.
        page.route(BASE + "i18n/vi.json", lambda route: route.fulfill(status=503))
        page.locator('[data-lang="vi"]').click()
        page.wait_for_timeout(200)
        expect(page.locator("html")).to_have_attribute("lang", "en")
        assert page.locator('[data-lang="en"]').get_attribute("aria-pressed") == "true"
        assert not errors, errors

        offline = browser.new_page(java_script_enabled=False, viewport={"width": 360, "height": 1000})
        offline.route("https://fonts.googleapis.com/**", lambda route: route.abort())
        offline.route(BASE + "**", static_route)
        offline.goto(BASE)
        expect(offline.locator("h1")).to_have_text(dictionaries["vi"]["hero.title"])
        expect(offline.locator('[data-lang="en"]')).to_be_disabled()
        assert offline.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()
    print("PASS locale parity, numeric formatting, section order, project links and keyboard FAQ")
    print("PASS both languages at six viewport widths; usable without JavaScript or hosted fonts")
    print(f"Screenshots: {SHOTS}")


if __name__ == "__main__":
    main()
