// EcoTrace demo console: Keycloak login (Authorization Code + PKCE), document upload and results.
// Every API call goes through the gateway on the same origin and carries the access token.

const KEYCLOAK = `${location.protocol}//${location.hostname}:8080/realms/ecotrace/protocol/openid-connect`;
const CLIENT_ID = 'ecotrace-portal';
const REDIRECT_URI = `${location.origin}/`;
const STEPS = ['gateway', 'store', 'classify', 'extract', 'persist'];

const $ = (id) => document.getElementById(id);
let dict = {};
let lang = 'vi';
let tokens = null;
let me = null;
let current = null; // document shown in the result card

// --- i18n ---------------------------------------------------------------------------------------

function t(key, vars = {}) {
  return (dict[key] ?? key).replace(/\{(\w+)\}/g, (_, name) => vars[name] ?? '');
}

const label = (labels) => (labels ? labels[lang] ?? labels.en ?? '' : '');

async function setLanguage(next) {
  lang = next;
  try { localStorage.setItem('lang', next); } catch { /* private mode */ }
  dict = await (await fetch(`i18n/${next}.json`)).json();
  document.documentElement.lang = next;
  document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll('[data-lang]').forEach((b) => b.classList.toggle('active', b.dataset.lang === next));
  if (me) renderAll();
}

// --- DOM helper ---------------------------------------------------------------------------------

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v);
  }
  for (const c of children.flat()) el.append(c instanceof Node ? c : document.createTextNode(String(c ?? '')));
  return el;
}

function toast(message) {
  const el = $('toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.hidden = true; }, 6000);
}

// --- Auth (OIDC Authorization Code + PKCE) ------------------------------------------------------

const b64url = (bytes) => btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

function claimsOf(jwt) {
  const part = jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
  const json = decodeURIComponent(atob(part).split('').map((c) => `%${c.charCodeAt(0).toString(16).padStart(2, '0')}`).join(''));
  return JSON.parse(json);
}

async function login() {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
  const challenge = b64url(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))));
  const state = b64url(crypto.getRandomValues(new Uint8Array(16)));
  sessionStorage.setItem('pkce', JSON.stringify({ verifier, state }));
  location.assign(`${KEYCLOAK}/auth?${new URLSearchParams({
    client_id: CLIENT_ID, response_type: 'code', scope: 'openid', redirect_uri: REDIRECT_URI,
    code_challenge: challenge, code_challenge_method: 'S256', state,
  })}`);
}

async function tokenRequest(params) {
  const res = await fetch(`${KEYCLOAK}/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ client_id: CLIENT_ID, ...params }),
  });
  if (!res.ok) throw new Error(`token endpoint ${res.status}`);
  tokens = await res.json();
  sessionStorage.setItem('tokens', JSON.stringify(tokens));
}

async function completeLogin() {
  const params = new URLSearchParams(location.search);
  if (!params.has('code')) return;
  const pkce = JSON.parse(sessionStorage.getItem('pkce') || '{}');
  history.replaceState({}, '', '/');
  if (params.get('state') !== pkce.state) throw new Error('state mismatch');
  await tokenRequest({ grant_type: 'authorization_code', code: params.get('code'), redirect_uri: REDIRECT_URI, code_verifier: pkce.verifier });
  sessionStorage.removeItem('pkce');
}

async function accessToken() {
  if (claimsOf(tokens.access_token).exp * 1000 - Date.now() < 60_000) {
    await tokenRequest({ grant_type: 'refresh_token', refresh_token: tokens.refresh_token });
  }
  return tokens.access_token;
}

function logout() {
  const idToken = tokens?.id_token;
  sessionStorage.clear();
  location.assign(`${KEYCLOAK}/logout?${new URLSearchParams({
    client_id: CLIENT_ID, post_logout_redirect_uri: REDIRECT_URI, ...(idToken ? { id_token_hint: idToken } : {}),
  })}`);
}

async function api(path, options = {}) {
  const res = await fetch(path, { ...options, headers: { ...options.headers, Authorization: `Bearer ${await accessToken()}` } });
  if (res.status === 401) {
    toast(t('error.session'));
    sessionStorage.clear();
    setTimeout(() => location.reload(), 2000);
    throw new Error('unauthorized');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res;
}

// --- Rendering ----------------------------------------------------------------------------------

const pct = (v) => `${Math.round((v ?? 0) * 100)}%`;
const numberFormat = () => new Intl.NumberFormat(lang === 'vi' ? 'vi-VN' : 'en-US', { maximumFractionDigits: 3 });
const formatValue = (f) => (f.type === 'number' && /^-?\d+(\.\d+)?$/.test(f.value) ? numberFormat().format(Number(f.value)) : f.value);

function renderSession() {
  const c = claimsOf(tokens.access_token);
  $('tenant-chip').textContent = me.tenant_name;
  $('user-chip').textContent = c.preferred_username;
  $('ai-chip').textContent = me.ai.enabled ? t('ai.model', { model: me.ai.model }) : t('ai.rules');
  $('ai-chip').classList.toggle('chip-warn', !me.ai.enabled);
}

function renderConfig() {
  $('config-strip').replaceChildren(
    h('span', {}, t('config.accepts', { count: me.document_types.length })),
    ...me.document_types.map((d) => h('span', { class: 'chip' }, label(d.label))),
    h('span', { class: 'muted' }, t('config.threshold', { value: pct(me.review_threshold) })),
  );
}

async function renderSamples() {
  const list = $('samples');
  let manifest = [];
  try {
    const res = await fetch(`samples/${me.tenant_id}/manifest.json`);
    if (res.ok) manifest = await res.json();
  } catch { /* no samples */ }
  if (!manifest.length) { list.replaceChildren(h('li', { class: 'muted' }, t('samples.empty'))); return; }
  list.replaceChildren(...manifest.map((s) => h('li', {},
    h('span', {}, label(s.title)),
    h('span', { class: 'sample-actions' },
      h('a', { href: `samples/${me.tenant_id}/${s.file}`, download: s.file }, t('action.download')),
      h('button', { class: 'secondary small', onclick: () => uploadSample(s) }, t('action.use'))),
  )));
}

function renderPipeline(steps = null, running = false) {
  const byName = Object.fromEntries((steps || []).map((s) => [s.step, s]));
  const items = STEPS.map((name, i) => {
    const s = byName[name];
    let state = s ? s.status : 'pending';
    if (running) state = i === 0 ? 'ok' : i <= 2 ? 'running' : 'pending';
    const detail = s ? [s.detail, s.ms !== undefined ? `${s.ms} ms` : null, s.extractor].filter(Boolean).join(' · ') : '';
    return h('li', { class: `step step-${state}` }, h('span', { class: 'dot' }), h('div', {}, h('strong', {}, t(`step.${name}`)), h('small', {}, detail)));
  });
  $('pipeline').replaceChildren(...items);
  if (!steps && !running) $('pipeline').append(h('li', { class: 'muted' }, t('pipeline.idle')));
}

function renderResult() {
  if (!current) { $('result-card').hidden = true; return; }
  const { document: doc, fields } = current;
  $('result-card').hidden = false;
  $('result-title').textContent = doc.document_type_label ? label(doc.document_type_label) : t('result.unknown');
  $('result-sub').textContent = t('result.sub', { file: doc.filename, confidence: pct(doc.type_confidence), extractor: doc.extractor });
  $('result-status').textContent = t(`status.${doc.status}`);
  $('result-status').className = `badge badge-${doc.status}`;
  $('fields-body').replaceChildren(...fields.map((f) => h('tr', { class: f.needs_review ? 'review' : '' },
    h('td', {}, label(f.label)),
    h('td', {}, f.value === null ? h('span', { class: 'muted' }, t('fields.missing')) : [h('strong', {}, formatValue(f)), f.unit ? ` ${f.unit}` : '']),
    h('td', {},
      h('div', { class: 'meter' }, h('span', { style: `width:${pct(f.confidence)}` })),
      h('small', {}, pct(f.confidence)),
      f.needs_review ? h('span', { class: 'flag' }, t('fields.review')) : ''),
  )));
  $('result-notes').hidden = !doc.notes;
  $('result-notes').textContent = doc.notes || '';
}

async function renderDocuments() {
  const { documents } = await (await api('/intake/documents')).json();
  const body = $('documents-body');
  if (!documents.length) { body.replaceChildren(h('tr', {}, h('td', { colspan: 4, class: 'muted' }, t('documents.empty')))); return; }
  const time = new Intl.DateTimeFormat(lang === 'vi' ? 'vi-VN' : 'en-GB', { dateStyle: 'short', timeStyle: 'short' });
  body.replaceChildren(...documents.map((d) => h('tr', { class: 'clickable', onclick: () => showDocument(d.id) },
    h('td', {}, time.format(new Date(d.created_at))),
    h('td', {}, d.filename),
    h('td', {}, d.document_type_label ? label(d.document_type_label) : '—'),
    h('td', {}, h('span', { class: `badge badge-${d.status}` }, t(`status.${d.status}`))),
  )));
}

async function renderFacilities() {
  const res = await api('/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: '{ demo_facility(order_by: {name: asc}) { name kind } }' }),
  });
  const { data } = await res.json();
  $('facilities').replaceChildren(...(data?.demo_facility || []).map((f) => h('li', {}, h('strong', {}, f.name), h('span', { class: 'muted' }, f.kind))));
}

function renderAll() {
  renderSession();
  renderConfig();
  renderSamples();
  renderPipeline(current?.pipeline || null);
  renderResult();
  renderDocuments().catch(() => {});
}

// --- Actions ------------------------------------------------------------------------------------

async function upload(file) {
  current = null;
  renderResult();
  renderPipeline(null, true);
  const form = new FormData();
  form.append('file', file, file.name);
  try {
    current = await (await api('/intake/documents', { method: 'POST', body: form })).json();
    renderPipeline(current.pipeline);
    renderResult();
    renderDocuments();
  } catch (err) {
    renderPipeline(null);
    toast(t('error.upload', { message: err.message }));
  }
}

async function uploadSample(sample) {
  const blob = await (await fetch(`samples/${me.tenant_id}/${sample.file}`)).blob();
  await upload(new File([blob], sample.file, { type: blob.type }));
}

async function showDocument(id) {
  current = await (await api(`/intake/documents/${id}`)).json();
  renderPipeline(null);
  renderResult();
  $('result-card').scrollIntoView({ behavior: 'smooth' });
}

async function viewOriginal() {
  if (!current) return;
  const { document: doc } = current;
  const url = URL.createObjectURL(await (await api(`/intake/documents/${doc.id}/file`)).blob());
  $('viewer-title').textContent = doc.filename;
  $('viewer-body').replaceChildren(doc.content_type === 'application/pdf'
    ? h('iframe', { src: url, title: doc.filename })
    : h('img', { src: url, alt: doc.filename }));
  $('viewer').showModal();
}

// --- Start --------------------------------------------------------------------------------------

function wireEvents() {
  document.querySelectorAll('[data-lang]').forEach((b) => b.addEventListener('click', () => setLanguage(b.dataset.lang)));
  $('login').addEventListener('click', login);
  $('logout').addEventListener('click', logout);
  $('file-input').addEventListener('change', (e) => e.target.files[0] && upload(e.target.files[0]));
  const zone = $('dropzone');
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', (e) => { e.preventDefault(); zone.classList.remove('over'); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
  $('view-original').addEventListener('click', viewOriginal);
  $('viewer-close').addEventListener('click', () => $('viewer').close());
}

async function start() {
  wireEvents();
  let saved = 'vi';
  try { saved = localStorage.getItem('lang') || 'vi'; } catch { /* private mode */ }
  await setLanguage(saved);
  try {
    await completeLogin();
    tokens = tokens || JSON.parse(sessionStorage.getItem('tokens') || 'null');
  } catch (err) {
    toast(err.message);
    tokens = null;
  }
  if (!tokens) { $('login-view').hidden = false; return; }
  try {
    me = await (await api('/intake/me')).json();
  } catch { return; }
  $('session').hidden = false;
  $('app-view').hidden = false;
  renderAll();
  renderFacilities().catch(() => {});
}

start();
