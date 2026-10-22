// EcoTrace demo console: Keycloak login (Authorization Code + PKCE), document upload and results.
// Every API call goes through the gateway on the same origin and carries the access token.

const KEYCLOAK = `${location.protocol}//${location.hostname}:8080/realms/ecotrace/protocol/openid-connect`;
const CLIENT_ID = 'ecotrace-portal';
const REDIRECT_URI = `${location.origin}/`;
const STEPS = ['gateway', 'scan', 'store', 'classify', 'extract', 'persist', 'publish'];

const $ = (id) => document.getElementById(id);
let dict = {};
let lang = 'vi';
let tokens = null;
let me = null;
let current = null; // document shown in the result card
let editing = false; // review mode of the result card
let ledger = null; // { activities, can_approve, summary }

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
    const err = new Error(body.detail || `HTTP ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
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
  const byName = {};
  for (const s of steps || []) {
    // A step can run more than once (one event per stage): keep the worst status and all details.
    const prev = byName[s.step];
    byName[s.step] = prev ? { ...s, status: prev.status === 'ok' ? s.status : prev.status, detail: `${prev.detail} · ${s.detail}` } : s;
  }
  const items = STEPS.map((name, i) => {
    const s = byName[name];
    let state = s ? s.status : 'pending';
    if (running) state = i === 0 ? 'ok' : i <= 3 ? 'running' : 'pending';
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
  const reviewable = doc.document_type_label && doc.status !== 'reviewed';
  $('review-start').hidden = !reviewable || editing;
  $('review-actions').hidden = !editing;
  $('result-reviewed').hidden = !doc.reviewed_by;
  $('result-reviewed').textContent = doc.reviewed_by
    ? t('review.by', { user: doc.reviewed_by, time: new Date(doc.reviewed_at).toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-GB') }) : '';
  $('fields-body').replaceChildren(...fields.map((f) => h('tr', { class: f.needs_review ? 'review' : '' },
    h('td', {}, label(f.label)),
    h('td', {}, editing
      ? [h('input', { class: 'field-input', 'data-field': f.name, value: f.value ?? '', inputmode: f.type === 'number' ? 'decimal' : 'text' }), f.unit ? ` ${f.unit}` : '']
      : f.value === null ? h('span', { class: 'muted' }, t('fields.missing')) : [h('strong', {}, formatValue(f)), f.unit ? ` ${f.unit}` : '']),
    h('td', {},
      h('div', { class: 'meter' }, h('span', { style: `width:${pct(f.confidence)}` })),
      h('small', {}, pct(f.confidence)),
      f.needs_review ? h('span', { class: 'flag' }, t('fields.review')) : ''),
  )));
  $('result-notes').hidden = !doc.notes;
  $('result-notes').textContent = doc.notes || '';
  const reviews = current.reviews || [];
  $('review-history').hidden = !reviews.length;
  $('review-history-list').replaceChildren(...reviews.map((r) => {
    const field = fields.find((f) => f.name === r.name);
    return h('li', {}, h('strong', {}, field ? label(field.label) : r.name), ': ',
      h('del', {}, r.old_value ?? '—'), ' → ', h('ins', {}, r.new_value ?? '—'),
      h('small', { class: 'muted' }, ` · ${r.reviewed_by}, ${new Date(r.reviewed_at).toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-GB')}`));
  }));
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
    body: JSON.stringify({ query: '{ core_facility(order_by: {name: asc}) { name kind } }' }),
  });
  const { data } = await res.json();
  $('facilities').replaceChildren(...(data?.core_facility || []).map((f) => h('li', {}, h('strong', {}, f.name), h('span', { class: 'muted' }, f.kind))));
}

function renderAll() {
  renderSession();
  renderConfig();
  renderSamples();
  renderPipeline(current?.pipeline || null);
  renderResult();
  renderDocuments().catch(() => {});
  renderLedger();
}

// --- Carbon Ledger ------------------------------------------------------------------------------

const tonnes = (kg) => new Intl.NumberFormat(lang === 'vi' ? 'vi-VN' : 'en-US', { maximumFractionDigits: 2 }).format((kg || 0) / 1000);
const qty = (v, unit) => `${numberFormat().format(Number(v))} ${unit}`;

async function loadLedger() {
  try {
    const activities = await (await api('/ledger/activities')).json();
    const period = $('ledger-period').value || '';
    const summary = await (await api(`/ledger/summary${period ? `?period=${period}` : ''}`)).json();
    ledger = { ...activities, summary };
  } catch (err) {
    ledger = null; // module disabled for this tenant, or not reachable
  }
  renderLedger();
}

function renderLedger() {
  $('ledger-card').hidden = !ledger;
  if (!ledger) return;
  const { summary } = ledger;
  const select = $('ledger-period');
  const chosen = select.value;
  select.replaceChildren(h('option', { value: '' }, t('ledger.allPeriods')),
    ...summary.periods.map((p) => h('option', { value: p.period }, `${p.period}${p.status === 'closed' ? ' 🔒' : ''}`)));
  select.value = chosen;
  $('kpi-scope1').textContent = tonnes(summary.scope1_kg);
  $('kpi-scope2').textContent = tonnes(summary.scope2_kg);
  $('kpi-total').textContent = tonnes(summary.scope1_kg + summary.scope2_kg);
  renderSeal();

  const pending = ledger.activities.filter((a) => a.status !== 'approved');
  $('pending-body').replaceChildren(...(pending.length ? pending.map((a) => h('tr', {},
    h('td', {}, a.filename || a.document_id),
    h('td', {}, `${a.source_name} · ${t('ledger.scopeN', { n: a.scope })}`),
    h('td', {}, qty(a.quantity, a.unit), h('small', { class: 'muted' }, ` · ${a.period}`)),
    h('td', {}, h('span', { class: `badge badge-${a.status}` }, t(`ledger.status.${a.status}`))),
    h('td', {}, a.status === 'pending_approval' && ledger.can_approve
      ? [h('button', { class: 'primary small', onclick: () => decide(a.id, 'approve') }, t('ledger.approve')), ' ',
        h('button', { class: 'link', onclick: () => decide(a.id, 'reject') }, t('ledger.reject'))]
      : a.status === 'pending_approval' ? h('small', { class: 'muted' }, t('ledger.waitingApprover')) : (a.reject_reason || '')),
  )) : [h('tr', {}, h('td', { colspan: 5, class: 'muted' }, t('ledger.nonePending')))]));

  $('entries-body').replaceChildren(...(summary.entries.length ? summary.entries.map((e) => h('tr', { class: 'clickable', onclick: () => showLineage(e.id) },
    h('td', {}, e.period),
    h('td', {}, `${e.source_id} · ${t('ledger.scopeN', { n: e.scope })}`),
    h('td', {}, qty(e.quantity, e.unit)),
    h('td', {}, h('strong', {}, tonnes(e.co2e_kg)), ' tCO₂e'),
  )) : [h('tr', {}, h('td', { colspan: 4, class: 'muted' }, t('ledger.noEntries')))]));
}

function renderSeal() {
  const period = $('ledger-period').value;
  const info = ledger.summary.periods.find((p) => p.period === period);
  $('seal-panel').hidden = !info;
  if (!info) { $('verify-result').hidden = true; return; }
  const closed = info.status === 'closed';
  $('seal-title').textContent = closed ? t('seal.closed', { period }) : t('seal.open', { period });
  $('seal-detail').textContent = closed
    ? t('seal.detail', { count: info.entry_count, index: info.leaf_index, size: info.tree_size, root: (info.root_hash || '').slice(0, 16), user: info.closed_by })
    : t('seal.openHint');
  $('seal-close').hidden = closed || !ledger.can_approve;
  $('seal-verify').hidden = !closed;
}

async function closePeriod() {
  const period = $('ledger-period').value;
  if (!period || !confirm(t('seal.confirm', { period }))) return;
  try {
    await api(`/ledger/periods/${period}/close`, { method: 'POST' });
    toast(t('seal.sealed', { period }));
  } catch (err) {
    toast(err.message);
  }
  loadLedger();
}

async function verifyPeriod() {
  const period = $('ledger-period').value;
  const box = $('verify-result');
  try {
    const r = await (await api(`/ledger/periods/${period}/verify`)).json();
    const problems = [...r.changed.map((e) => [t('seal.changed'), e]), ...r.removed.map((e) => [t('seal.removed'), e]), ...r.added.map((e) => [t('seal.added'), e])];
    box.className = `verify-result ${r.valid ? 'ok' : 'bad'}`;
    box.replaceChildren(
      h('strong', {}, r.valid ? t('seal.valid', { count: r.entry_count }) : t('seal.invalid')),
      h('small', { class: 'muted' }, ` · ${t('seal.logInfo', { index: r.leaf_index, size: r.tree_size, root: r.root_hash.slice(0, 16) })}`),
      problems.length ? h('ul', {}, ...problems.map(([kind, e]) => h('li', {}, `${kind}: ${e.filename || e.entry_id} (${e.source_id || ''}${e.co2e_kg !== undefined ? `, ${tonnes(e.co2e_kg)} tCO₂e ${t('seal.now')}` : ''})`))) : '');
  } catch (err) {
    box.className = 'verify-result bad';
    box.textContent = err.message;
  }
  box.hidden = false;
}

async function decide(id, action) {
  let body;
  if (action === 'reject') {
    const reason = prompt(t('ledger.rejectReason'));
    if (!reason) return;
    body = JSON.stringify({ reason });
  }
  try {
    await api(`/ledger/activities/${id}/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
    toast(t(action === 'approve' ? 'ledger.approved' : 'ledger.rejected'));
  } catch (err) {
    toast(err.message);
  }
  loadLedger();
}

async function showLineage(entryId) {
  const l = await (await api(`/ledger/entries/${entryId}/lineage`)).json();
  const when = (v) => (v ? new Date(v).toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-GB') : '');
  const steps = [
    [t('lineage.document'), `${l.document.filename}`, `${t('lineage.uploadedBy', { user: l.document.uploaded_by, time: when(l.document.created_at) })} · ${l.document.extractor} · SHA-256 ${l.document.sha256.slice(0, 12)}…`,
      h('button', { class: 'secondary small', onclick: () => viewOriginal(l.document) }, t('action.viewOriginal'))],
    [t('lineage.review'), l.document.reviewed_by ? t('review.by', { user: l.document.reviewed_by, time: when(l.document.reviewed_at) }) : t('lineage.autoAccepted'),
      l.corrections.length ? l.corrections.map((c) => `${c.name}: ${c.old_value ?? '—'} → ${c.new_value ?? '—'} (${c.reviewed_by})`).join('; ') : t('lineage.noCorrections')],
    [t('lineage.activity'), `${qty(l.activity.quantity, l.activity.unit)} · ${l.activity.source_name}`, `${t('ledger.scopeN', { n: l.activity.scope })} · ${l.activity.facility_code || ''} · ${t('ledger.period')} ${l.activity.period}`],
    [t('lineage.approval'), t('lineage.approvedBy', { user: l.activity.decided_by, time: when(l.activity.decided_at) }), ''],
    [t('lineage.factor'), `${l.entry.factor_value} ${l.entry.factor_unit} · ${l.entry.factor_version}`, l.entry.factor_source,
      l.entry.factor_status === 'provisional' ? h('small', { class: 'warn' }, t('lineage.provisional')) : ''],
    [t('lineage.entry'), `${tonnes(l.entry.co2e_kg)} tCO₂e`, `${qty(l.entry.quantity, l.entry.unit)} × ${l.entry.factor_value} = ${numberFormat().format(l.entry.co2e_kg)} kg`],
    [t('lineage.period'), `${l.period.period} · ${t(`ledger.periodStatus.${l.period.status}`)}`, l.period.closed_by ? `${l.period.closed_by}, ${when(l.period.closed_at)}` : ''],
  ];
  $('lineage-body').replaceChildren(...steps.map(([title, main, detail, extra]) => h('li', {}, h('small', {}, title), h('strong', {}, main), h('small', {}, detail || ''), extra || '')));
  $('lineage').showModal();
}

// --- Actions ------------------------------------------------------------------------------------

async function upload(file) {
  current = null;
  editing = false;
  renderResult();
  renderPipeline(null, true);
  const form = new FormData();
  form.append('file', file, file.name);
  try {
    current = await (await api('/intake/documents', { method: 'POST', body: form })).json();
    renderPipeline(current.pipeline);
    renderResult();
    renderDocuments();
    setTimeout(loadLedger, 2500); // the ledger consumes the event asynchronously
  } catch (err) {
    renderPipeline(null);
    if (err.status === 409 && err.body?.duplicate_of) {
      toast(t('duplicate.found', { file: err.body.filename, user: err.body.uploaded_by,
        time: new Date(err.body.created_at).toLocaleString(lang === 'vi' ? 'vi-VN' : 'en-GB') }));
      await showDocument(err.body.duplicate_of);
      return;
    }
    toast(t('error.upload', { message: err.message }));
  }
}

async function saveReview() {
  const values = {};
  document.querySelectorAll('.field-input').forEach((input) => { values[input.dataset.field] = input.value; });
  try {
    current = await (await api(`/intake/documents/${current.document.id}/review`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ values }),
    })).json();
    editing = false;
    renderResult();
    renderDocuments();
    toast(t('review.saved'));
    setTimeout(loadLedger, 2500);
  } catch (err) {
    toast(t('error.review', { message: err.message }));
  }
}

async function uploadSample(sample) {
  const blob = await (await fetch(`samples/${me.tenant_id}/${sample.file}`)).blob();
  await upload(new File([blob], sample.file, { type: blob.type }));
}

async function showDocument(id) {
  editing = false;
  current = await (await api(`/intake/documents/${id}`)).json();
  renderPipeline(null);
  renderResult();
  $('result-card').scrollIntoView({ behavior: 'smooth' });
}

async function viewOriginal(doc = current?.document) {
  if (!doc) return;
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
  $('view-original').addEventListener('click', () => viewOriginal());
  $('review-start').addEventListener('click', () => { editing = true; renderResult(); });
  $('review-cancel').addEventListener('click', () => { editing = false; renderResult(); });
  $('review-save').addEventListener('click', saveReview);
  $('ledger-period').addEventListener('change', () => { $('verify-result').hidden = true; loadLedger(); });
  $('seal-close').addEventListener('click', closePeriod);
  $('seal-verify').addEventListener('click', verifyPeriod);
  $('lineage-close').addEventListener('click', () => $('lineage').close());
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
  loadLedger();
}

start();
