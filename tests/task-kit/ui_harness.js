// Runs the dashboard's app.js against a fake DOM and canned API responses, and
// prints what it rendered as JSON. Used by test_dashboard_ui_contract.py.
// Usage: node ui_harness.js <app.js> <dashboard.json> <item-detail.json> <item-key> <task-key>
//        [<queue-item-key> <recheck-item-key> <retry-key>]
// <task-key> must be an open task; the harness derives a second open task from the payload to
// exercise the one-at-a-time expansion.
'use strict';
const fs = require('fs');
const vm = require('vm');
const [, , appPath, payloadPath, detailPath, itemKey, taskKey, queueKey, recheckKey, retryKey] = process.argv;
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
const detail = JSON.parse(fs.readFileSync(detailPath, 'utf8'));

function makeEl(id) {
  const el = {
    id, innerHTML: '', textContent: '', value: '', className: '', attrs: {}, scrollTop: 0,
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    classes: new Set(),
    classList: {
      toggle(name, on) { if (on === undefined ? !this.owner.classes.has(name) : on) this.owner.classes.add(name); else this.owner.classes.delete(name); },
    },
    addEventListener() {},
    querySelectorAll() { return []; },
    style: { setProperty() {} },
  };
  el.classList.owner = el;
  return el;
}
const els = {};
['serverChip', 'status', 'banners', 'projectSelect', 'main', 'panel', 'scrim', 'search', 'sortSeg', 'layout']
  .forEach((id) => { els[id] = makeEl(id); });
const docListeners = {};
const document = {
  getElementById: (id) => els[id],
  querySelector: () => null,
  addEventListener: (t, f) => { (docListeners[t] = docListeners[t] || []).push(f); },
  visibilityState: 'visible',
  createElement: () => makeEl('x'),
  body: { appendChild() {} },
  execCommand: () => true,
};
const requests = [];
function fakeFetch(url, opts) {
  requests.push({ url, headers: opts.headers, method: opts.method || 'GET', body: opts.body || null });
  if (opts.method === 'POST') {
    return Promise.resolve({ status: 202, ok: true, json: () => Promise.resolve({}) });
  }
  const body = url.indexOf('/log') > 0 ? { text: 'log line\n', cursor: 9 } :
    url.indexOf('/api/v1/items/') === 0 ? detail : payload;
  return Promise.resolve({ status: 200, ok: true, json: () => Promise.resolve(body) });
}
const timers = [];
const context = {
  document, location: { hash: '#test-token' }, fetch: fakeFetch,
  setTimeout: (f, ms) => { timers.push({ f, ms }); return timers.length; },
  clearTimeout() {}, navigator: {}, console,
};
const flush = () => new Promise((r) => setImmediate(r));
function click(attrs) {
  const target = makeEl('target');
  target.attrs = attrs;
  target.closest = () => target;
  (docListeners.click || []).forEach((f) => f({ target, stopPropagation() {} }));
}

(async () => {
  vm.runInNewContext(fs.readFileSync(appPath, 'utf8'), context);
  await flush();
  const report = { requests, pollDelays: timers.map((t) => t.ms) };
  report.main = els.main.innerHTML;
  report.banners = els.banners.innerHTML;
  report.status = els.status.innerHTML;
  report.select = els.projectSelect.innerHTML;
  report.sortBar = els.sortSeg.innerHTML;
  report.panelInitial = els.panel.innerHTML;
  report.layoutInitial = [...els.layout.classes];
  report.sorted = {};
  for (const id of ['priority', 'needs', 'progress', 'latest']) {
    click({ 'data-action': 'sort', 'data-v': id });
    report.sorted[id] = { main: els.main.innerHTML, bar: els.sortSeg.innerHTML };
  }
  click({ 'data-action': 'sort', 'data-v': 'priority' });
  const other = payload.tasks.filter((t) => t.section === 'open' && t.key !== taskKey)[0].key;
  click({ 'data-action': 'toggletask', 'data-key': taskKey });
  report.mainOpen = els.main.innerHTML;
  click({ 'data-action': 'toggletask', 'data-key': other });
  report.mainSwitched = els.main.innerHTML;
  report.otherKey = other;
  click({ 'data-action': 'toggletask', 'data-key': other });
  report.mainCollapsed = els.main.innerHTML;
  click({ 'data-action': 'toggletask', 'data-key': taskKey });
  click({ 'data-action': 'select', 'data-key': itemKey });
  await flush();
  report.itemPanel = els.panel.innerHTML;
  report.layoutSelected = [...els.layout.classes];
  report.mainSelected = els.main.innerHTML;
  click({ 'data-action': 'toggletask', 'data-key': other });
  report.layoutAfterSwitch = [...els.layout.classes];
  click({ 'data-action': 'select', 'data-key': itemKey });
  await flush();
  click({ 'data-action': 'resolve', 'data-key': itemKey });
  report.itemResolve = els.panel.innerHTML;
  click({ 'data-action': 'selecttask', 'data-key': taskKey });
  report.taskPanel = els.panel.innerHTML;
  click({ 'data-action': 'resolvetask', 'data-key': taskKey });
  report.taskResolve = els.panel.innerHTML;
  click({ 'data-action': 'closepanel' });
  report.afterClose = els.panel.innerHTML;
  report.layoutClosed = [...els.layout.classes];
  if (queueKey) {
    click({ 'data-action': 'queue', 'data-key': queueKey });
    await flush();
    click({ 'data-action': 'recheck', 'data-key': recheckKey });
    await flush();
    click({ 'data-action': 'retry', 'data-key': retryKey });
    await flush();
    click({ 'data-action': 'selectrun', 'data-key': retryKey.split('|')[0] });
    await flush();
    report.runPanel = els.panel.innerHTML;
  }
  report.posts = requests.filter((r) => r.method === 'POST');
  console.log(JSON.stringify(report));
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
