// SPDX-FileCopyrightText: 2026 EcoTrace contributors
// SPDX-License-Identifier: Apache-2.0
// The static Vietnamese document remains usable if JavaScript or a locale request fails.
const supported = new Set(['vi', 'en']);
const buttons = [...document.querySelectorAll('[data-lang]')];
let latestRequest = 0;

async function setLanguage(language) {
  if (!supported.has(language)) language = 'vi';
  const request = ++latestRequest;
  try {
    const response = await fetch(`i18n/${language}.json`);
    if (!response.ok) throw new Error(`Locale response: ${response.status}`);
    const messages = await response.json();
    if (request !== latestRequest) return;
    document.querySelectorAll('[data-i18n]').forEach((element) => {
      const value = messages[element.dataset.i18n];
      if (typeof value === 'string') element.textContent = value;
    });
    document.querySelectorAll('[data-i18n-aria]').forEach((element) => {
      const value = messages[element.dataset.i18nAria];
      if (typeof value === 'string') element.setAttribute('aria-label', value);
    });
    document.querySelectorAll('[data-number]').forEach((element) => {
      const formatted = new Intl.NumberFormat(language === 'vi' ? 'vi-VN' : 'en-US', {
        maximumFractionDigits: Number(element.dataset.digits || 0),
      }).format(Number(element.dataset.number));
      element.textContent = formatted + (element.dataset.unit ? ` ${element.dataset.unit}` : '');
    });
    document.documentElement.lang = language;
    document.title = messages['meta.title'];
    document.querySelector('meta[name="description"]').content = messages['meta.description'];
    document.querySelector('meta[property="og:title"]').content = messages['meta.title'];
    document.querySelector('meta[property="og:description"]').content = messages['meta.description'];
    buttons.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.lang === language)));
    try { localStorage.setItem('ecotrace-site-language', language); } catch { /* private browsing */ }
  } catch {
    // Keep the previously rendered language rather than leaving a partial or empty page.
  }
}

buttons.forEach((button) => {
  button.disabled = false;
  button.addEventListener('click', () => setLanguage(button.dataset.lang));
});
let saved = 'vi';
try { saved = localStorage.getItem('ecotrace-site-language') || 'vi'; } catch { /* private browsing */ }
setLanguage(saved);
