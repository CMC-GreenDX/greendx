# Landing page

The static project page follows [the design guide](../docs/design.md). The Pages workflow copies this directory to the site root and adds the API reference at `api/`.

Text comes from `i18n/vi.json` and `i18n/en.json`. The HTML includes a Vietnamese fallback for readers without JavaScript. `app.js` switches text, accessible names, metadata and number formatting; a failed locale request keeps the current language.

The invoice preview uses Company A's fictional electricity bill, the rule-based extractor's 60% confidence and the tenant's 80% review threshold. The calculation uses the provisional factor in its config pack; it is not an official emissions report.

Run the browser checks with the same Playwright and Chromium setup as the console:

```sh
python tools/site-check.py
```

The check covers both languages at 360, 375, 600, 768, 1024 and 1440 px, scrolling tables, section order, anchor links, keyboard FAQ controls, numeric formatting, locale failures and the JavaScript-free fallback. Screenshots go to the system temporary directory under `ecotrace-site-layout`, or to `SCREENSHOT_DIR` when set.
