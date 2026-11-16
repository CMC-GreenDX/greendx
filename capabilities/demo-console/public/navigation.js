// SPDX-FileCopyrightText: 2026 EcoTrace contributors
// SPDX-License-Identifier: Apache-2.0
// Presentation only: the existing app owns authentication, API calls and rendering.
const app = document.getElementById('app-view');
const title = document.getElementById('screen-title');
const links = [...document.querySelectorAll('[data-screen-link]')];
const screens = [...document.querySelectorAll('[data-screen]')];
const names = new Set(links.map((link) => link.dataset.screenLink));

function activate(name, focus = false) {
  const link = links.find((item) => item.dataset.screenLink === name && !item.hidden);
  if (!link) name = 'upload';
  const active = links.find((item) => item.dataset.screenLink === name);
  app.dataset.activeScreen = name;
  screens.forEach((screen) => { screen.hidden = !screen.dataset.screen.split(' ').includes(name); });
  links.forEach((item) => {
    if (item === active) item.setAttribute('aria-current', 'page');
    else item.removeAttribute('aria-current');
  });
  const label = active.querySelector('[data-i18n]');
  title.dataset.i18n = label.dataset.i18n;
  title.textContent = label.textContent;
  if (focus) title.focus({ preventScroll: true });
}

function fromHash() {
  const name = location.hash.slice(1);
  activate(names.has(name) ? name : 'upload');
}

links.forEach((link) => link.addEventListener('click', (event) => {
  event.preventDefault();
  history.pushState(null, '', link.getAttribute('href'));
  activate(link.dataset.screenLink, true);
  window.scrollTo({ top: 0 });
}));
window.addEventListener('hashchange', fromHash);
window.addEventListener('popstate', fromHash);

// Opening a document elsewhere still exposes the app's extraction result.
document.getElementById('documents-body').addEventListener('click', (event) => {
  if (event.target.closest('tr.clickable')) activate('upload');
});
document.getElementById('inbox-list').addEventListener('click', (event) => {
  const button = event.target.closest('button.link');
  // The other link button is Reject; only the first link opens the document.
  if (button && button === button.closest('.result-actions').firstElementChild) activate('upload');
});

const count = document.getElementById('approvals-count');
const inbox = document.getElementById('inbox-list');
new MutationObserver(() => {
  count.textContent = String(inbox.querySelectorAll('li:not(.muted)').length);
}).observe(inbox, { childList: true });

// Follow module availability and language changes without extra API calls.
for (const [id, name] of [['ledger-card', 'ledger'], ['purchase-card', 'purchases']]) {
  const card = document.getElementById(id);
  const link = links.find((item) => item.dataset.screenLink === name);
  const sync = () => {
    link.hidden = card.hidden;
    if (link.hidden && app.dataset.activeScreen === name) activate('upload');
    else if (!link.hidden && location.hash === `#${name}`) activate(name);
  };
  new MutationObserver(sync).observe(card, { attributes: true, attributeFilter: ['hidden'] });
  sync();
}
new MutationObserver(() => activate(app.dataset.activeScreen || 'upload'))
  .observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
new MutationObserver(() => { if (!app.hidden) fromHash(); })
  .observe(app, { attributes: true, attributeFilter: ['hidden'] });
fromHash();
