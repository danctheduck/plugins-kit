/* Task dashboard UI.
 *
 * Plain JavaScript, no framework and no build step. It talks only to the
 * server that served it: every request is a relative /api/v1/ path carrying the
 * per-instance token that arrived in the URL fragment. The only state-changing
 * calls are Queue, Retry and Re-check, sent by send(), each carrying the
 * expected_revision the page last saw. The actions the server does not back yet
 * (Cancel run, Defer, Queue all, New task, Add item, Pause worker, the run
 * option controls) are drawn disabled through laterButton(), so they are
 * visible and cannot be clicked. Queue and Retry also stay disabled, with the
 * server's reason, whenever the server reports autonomous runs unavailable.
 *
 * One flat task list across projects: a row per open task (priority, title,
 * <repo>:<task>, item count, age) with a needs-you marker and an in-flight
 * marker; clicking a row opens its stage map (one at a time). The side panel
 * exists only while an item, task or run is selected.
 *
 * The page is served under a CSP that forbids inline styles and scripts, so no
 * markup carries a style attribute: dynamic values travel as data-* attributes
 * and are applied through the CSSOM after each render (applyDynamic).
 */
(function () {
'use strict';

var TOKEN = (location.hash || '').replace(/^#/, '');
var VISIBLE_POLL_MS = 2000;
var HIDDEN_POLL_MS = 15000;

var S = {
  snap: null,          // last dashboard payload
  project: '',         // project (repository) filter (id)
  sort: 'priority',    // one of SORTS; exactly one is active
  openTask: null,      // the one expanded task key "checkout|task"
  q: '',               // text filter
  sel: null,           // selected item key  "checkout|task|item"
  selTask: null,       // selected task key  "checkout|task"
  mode: 'none',        // none | item | task | run  (none: no side panel)
  selRun: null,        // selected run id
  runLog: {},          // run id -> { text, cursor }
  notice: null,        // { kind, title, text } shown with the banners after an action
  detail: {},          // item key -> detail payload
  open: {},            // <details> open state by data-open key (all start closed)
  resolve: {},         // keys whose command box is expanded
  conn: 'connecting',  // connecting | ok | offline | auth
  connDetail: '',
  panelOpen: false,
  renderedRev: null,
  polling: false,
  refreshNext: false,
  timer: null
};

/* ================= helpers ================= */
var SVG = {
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  play: '<path d="M8 5.5v13l11-6.5z"/>',
  pause: '<path d="M9 6v12M15 6v12"/>',
  alert: '<path d="M12 6.5v7M12 17.5h.01"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/>',
  term: '<path d="M4 6l6 6-6 6M12 19h8"/>',
  retry: '<path d="M20 12a8 8 0 1 1-2.4-5.7M20 4v5h-5"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="1.5"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  tri: '<path d="M12 4l9.5 16.5h-19z"/><path d="M12 10v4.5M12 17.5h.01"/>',
  spin: '<path d="M12 3a9 9 0 1 0 9 9"/>',
  eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/>'
};
function ic(name, cls) {
  return '<svg class="ic ' + (cls || '') + '" viewBox="0 0 24 24" aria-hidden="true">' + SVG[name] + '</svg>';
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}
function $(id) { return document.getElementById(id); }
function pad(n) { return (n < 10 ? '0' : '') + n; }
function parseWhen(ts) {
  if (!ts) return null;
  var m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(ts);
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 12), +(m[5] || 0)).getTime();
}
function ago(ts) {
  var t = parseWhen(ts);
  if (t == null) return 'no activity';
  var m = Math.floor((Date.now() - t) / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return m + ' min ago';
  var h = Math.floor(m / 60);
  if (h < 48) return h + 'h ago';
  return Math.floor(h / 24) + 'd ago';
}
/* Same age-dimming rule as the static review page. */
function brightness(ts) {
  var t = parseWhen(ts);
  if (t == null) return 0.33;
  var hrs = (Date.now() - t) / 3600000;
  if (hrs <= 4) return 1;
  if (hrs >= 120) return 0.33;
  return 1 - ((hrs - 4) / 116) * 0.67;
}
/* A task is addressed by the checkout it is read from (two checkouts of one
 * repository may each hold a task with the same path). The repository is the
 * project; the task is SHOWN as <repo>:<stub>, the full path stays the id. */
function ikey(task, item) { return task.checkout + '|' + task.id + '|' + item.id; }
function tkey(task) { return task.checkout + '|' + task.id; }
function identOf(repo, taskPath) { return repo + ':' + String(taskPath).split('/').pop(); }
function identHtml(repo, taskPath) {
  return '<span class="ident mono" title="' + esc(taskPath) + '"><span class="repo">' + esc(repo) + '</span>:' +
    esc(String(taskPath).split('/').pop()) + '</span>';
}
function findTask(key) {
  var tasks = (S.snap && S.snap.tasks) || [];
  for (var i = 0; i < tasks.length; i++) if (tkey(tasks[i]) === key) return tasks[i];
  return null;
}
function splitIKey(k) { var p = k.split('|'); return { project: p[0], task: p[1], item: p[2] }; }
function findItem(k) {
  var parts = splitIKey(k), task = findTask(parts.project + '|' + parts.task);
  if (!task) return null;
  for (var i = 0; i < task.items.length; i++) if (task.items[i].id === parts.item) return { task: task, item: task.items[i] };
  return null;
}

/* Actions that change shared state. They are drawn, disabled, with a title that
 * says when they arrive. The id after data-later names the action. */
var LATER_NOTE = ' arrives in a later increment';
function laterButton(label, cls, icon, id) {
  return '<button type="button" class="btn ' + cls + '" disabled aria-disabled="true" data-later="' + id + '" title="' +
    esc(label + LATER_NOTE) + '">' + (icon ? ic(icon) : '') + esc(label) + '</button>';
}
function laterPill(label, id) {
  return '<button type="button" class="pill" disabled aria-disabled="true" data-later="' + id + '" title="' +
    esc(label + LATER_NOTE) + '">' + esc(label) + '</button>';
}

function caps() { return (S.snap && S.snap.capabilities) || {}; }
function runCap() { return caps().run || { available: false, reason: '' }; }
function canDo(action) {
  var m = caps().mutations || {};
  return !!(m.available && (m.actions || []).indexOf(action) >= 0);
}
function liveButton(label, cls, icon, action, key) {
  return '<button type="button" class="btn ' + cls + '" data-action="' + action + '" data-key="' + esc(key) + '">' +
    (icon ? ic(icon) : '') + esc(label) + '</button>';
}
/* Queue and Retry start unattended work, so they need the llm-kit edge too. */
function runButton(label, cls, icon, action, key) {
  if (canDo(action) && runCap().available) return liveButton(label, cls, icon, action, key);
  var why = runCap().available ? '' : runCap().reason;
  return '<button type="button" class="btn ' + cls + '" disabled aria-disabled="true" data-later="' + action + '" title="' +
    esc(why || (label + LATER_NOTE)) + '">' + (icon ? ic(icon) : '') + esc(label) + '</button>';
}
function runPill(label, action, key) {
  if (canDo(action) && runCap().available) {
    return '<button type="button" class="pill" data-action="' + action + '" data-key="' + esc(key) + '">' + esc(label) + '</button>';
  }
  return '<button type="button" class="pill" disabled aria-disabled="true" data-later="' + action + '" title="' +
    esc(runCap().reason || (label + LATER_NOTE)) + '">' + esc(label) + '</button>';
}

var RUN_LABEL = {
  queued: 'Queued', starting: 'Starting', running: 'Running', accepted: 'Accepted', blocked: 'Blocked',
  failed: 'Failed', timeout: 'Timed out', crashed: 'Crashed', skipped: 'Dropped'
};

var STATE_LABEL = {
  'available': 'Available', 'in-flight': 'In flight', 'blocked': 'Needs you',
  'deferred': 'Deferred', 'unknown': 'Unknown state'
};
var STATE_COLOR = {
  'available': 'var(--accent)', 'in-flight': 'var(--run)', 'blocked': 'var(--warn)',
  'deferred': 'var(--muted)', 'unknown': 'var(--bad)'
};
var NEED_KIND = { 'task-blocked': 'Task blocked', 'item-blocked': 'Needs decision', 'invalid': 'Cannot start' };

/* ================= data ================= */
function query() {
  var parts = [];
  if (S.project) parts.push('project=' + encodeURIComponent(S.project));
  if (S.q) parts.push('q=' + encodeURIComponent(S.q));
  if (S.refreshNext) parts.push('refresh=1');
  return parts.length ? '?' + parts.join('&') : '';
}
function api(path) {
  return fetch(path, { headers: { 'X-Task-Kit-Token': TOKEN }, cache: 'no-store' }).then(function (res) {
    if (res.status === 401) { var e = new Error('auth'); e.auth = true; throw e; }
    if (!res.ok) {
      return res.json().then(function (b) {
        throw new Error((b && b.error && b.error.message) || ('HTTP ' + res.status));
      }, function () { throw new Error('HTTP ' + res.status); });
    }
    return res.json();
  });
}
function send(path, body) {
  return fetch(path, {
    method: 'POST',
    headers: { 'X-Task-Kit-Token': TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store'
  }).then(function (res) {
    return res.json().then(function (b) { return { status: res.status, body: b }; },
      function () { return { status: res.status, body: {} }; });
  });
}
function fetchRunLog(id) {
  var cur = (S.runLog[id] || { cursor: 0 }).cursor;
  return api('/api/v1/runs/' + encodeURIComponent(id) + '/log?after=' + cur).then(function (r) {
    var old = S.runLog[id] ? S.runLog[id].text : '';
    S.runLog[id] = { text: (old + r.text).slice(-20000), cursor: r.cursor };
    if (S.mode === 'run' && S.selRun === id) renderPanel();
  }, function (e) { S.runLog[id] = { text: '(log unavailable: ' + e.message + ')', cursor: 0 }; });
}
function fetchDetail(k) {
  var p = splitIKey(k);
  return api('/api/v1/items/' + encodeURIComponent(p.project) + '/' + encodeURIComponent(p.task) + '/' + encodeURIComponent(p.item))
    .then(function (d) { S.detail[k] = d; renderPanel(); }, function (e) {
      S.detail[k] = { error: e.message };
      renderPanel();
    });
}
function poll() {
  if (S.polling) return Promise.resolve();
  S.polling = true;
  var url = '/api/v1/dashboard' + query();
  S.refreshNext = false;
  return api(url).then(function (snap) {
    var changed = !S.snap || snap.revision !== S.renderedRev || S.conn !== 'ok' ||
      JSON.stringify(snap.filters) !== JSON.stringify((S.snap || {}).filters);
    S.snap = snap; S.conn = 'ok'; S.connDetail = '';
    if (changed) {
      S.renderedRev = snap.revision;
      render();
      if (S.mode === 'item' && S.sel) fetchDetail(S.sel);
    } else {
      renderStatus();
    }
    if (S.mode === 'run' && S.selRun) fetchRunLog(S.selRun);
  }, function (e) {
    S.conn = e.auth ? 'auth' : 'offline'; S.connDetail = e.message;
    renderBanners(); renderStatus();
  }).then(function () { S.polling = false; schedule(); });
}
function schedule() {
  if (S.timer) clearTimeout(S.timer);
  S.timer = setTimeout(poll, document.visibilityState === 'hidden' ? HIDDEN_POLL_MS : VISIBLE_POLL_MS);
}
function pollNow() {
  if (S.timer) clearTimeout(S.timer);
  poll();
}

/* ================= rendering ================= */
function renderBanners() {
  var h = '';
  if (S.snap && runCap().available) {
    h += '<div class="callout info"><strong>Autonomous runs are on</strong><p>Queue starts one unattended Claude run for one item; ' +
      'a blocked run marks its task as needing you. Cancel run, Defer, Queue all, New task, Add item and Pause worker ' +
      'are shown disabled: they arrive in a later increment. &ldquo;Resolve in Claude Code&rdquo; only shows commands to copy.</p></div>';
  } else if (S.snap) {
    h += '<div class="callout info"><strong>Autonomous runs are unavailable</strong><p>' + esc(runCap().reason || 'This server cannot start runs.') +
      ' Viewing tasks, Re-check and &ldquo;Resolve in Claude Code&rdquo; still work.</p></div>';
  }
  if (S.notice) {
    h += '<div class="callout ' + esc(S.notice.kind) + '"><strong>' + esc(S.notice.title) + '</strong><p>' + esc(S.notice.text) + '</p></div>';
  }
  if (S.conn === 'auth') {
    h += '<div class="callout bad"><strong>' + (TOKEN ? 'This page no longer matches the server' : 'This page has no access token') + '</strong><p>' +
      (TOKEN ? 'The dashboard server restarted, so this page\'s token is stale. ' : 'The token travels in the address after #. ') +
      'Run <span class="mono">task-kit</span> to open the dashboard.</p></div>';
  } else if (S.conn === 'offline') {
    h += '<div class="callout bad"><strong>Cannot reach the dashboard server</strong><p>' + esc(S.connDetail) +
      ' Retrying. If it stopped, run <span class="mono">task-kit</span>.</p></div>';
  }
  var errs = (S.snap && S.snap.errors) || [];
  errs.forEach(function (e) {
    h += '<div class="callout bad"><strong>Discovery problem (' + esc(e.code) + ')</strong><p>' + esc(e.message) + '</p></div>';
  });
  $('banners').innerHTML = h;
}
function renderStatus() {
  var chip = $('serverChip');
  var label = { connecting: 'connecting', ok: 'online', offline: 'offline', auth: 'token mismatch' }[S.conn];
  chip.textContent = label;
  chip.className = 'chip' + (S.conn === 'ok' ? '' : ' badchip');
  if (!S.snap) { $('status').textContent = ''; return; }
  var t = S.snap.totals;
  $('status').innerHTML = '<b>' + t.projects + '</b> project(s) - <b>' + t.tasks + '</b> task(s) - <b>' + t.needs + '</b> need you';
}
function renderProjectSelect() {
  var sel = $('projectSelect'), ps = S.snap.projects;
  var sig = ps.map(function (p) { return p.id + ':' + p.name + ':' + p.counts.open + ':' + p.checkouts.join(','); }).join('|') + '#' + S.project;
  if (sel.getAttribute('data-sig') === sig) return;
  sel.setAttribute('data-sig', sig);
  var h = '<option value="">All projects</option>';
  ps.forEach(function (p) {
    h += '<option value="' + esc(p.id) + '"' + (p.id === S.project ? ' selected' : '') + ' title="Checkouts: ' + esc(p.checkouts.join(', ')) + '">' +
      esc(p.name) + ' (' + p.counts.open + ' open)</option>';
  });
  sel.innerHTML = h;
  sel.value = S.project;
}

/* ---- sorting: exactly one is active ---- */
function needN(t) { return (t.needs || []).length; }
function isRunning(it) { return it.ui_state === 'in-flight' || !!(it.run && (it.run.state === 'running' || it.run.state === 'starting')); }
function runN(t) { return t.items.filter(isRunning).length; }
function queN(t) { return t.items.filter(function (it) { return !isRunning(it) && it.run && it.run.state === 'queued'; }).length; }
function priOf(t) { return t.priority || 'P9'; }
function lastOf(t) { var w = parseWhen(t.last_activity); return w == null ? -1 : w; }
function priCmp(a, b) { return priOf(a) < priOf(b) ? -1 : priOf(a) > priOf(b) ? 1 : 0; }
function byLatest(a, b) { return lastOf(b) - lastOf(a); }
function byPriority(a, b) { return priCmp(a, b) || byLatest(a, b); }
function tieBreak(a, b) { return a.title.toLowerCase() < b.title.toLowerCase() ? -1 : a.title.toLowerCase() > b.title.toLowerCase() ? 1 : (tkey(a) < tkey(b) ? -1 : tkey(a) > tkey(b) ? 1 : 0); }
var SORTS = [
  { id: 'priority', label: 'Priority', desc: 'priority, then latest activity', cmp: byPriority },
  { id: 'needs', label: 'Needs you first', desc: 'tasks with items waiting on you first, then priority',
    cmp: function (a, b) { return ((needN(b) > 0) - (needN(a) > 0)) || byPriority(a, b); } },
  { id: 'progress', label: 'In progress first', desc: 'tasks with a job in flight first, then priority',
    cmp: function (a, b) { return ((runN(b) > 0) - (runN(a) > 0)) || byPriority(a, b); } },
  { id: 'latest', label: 'Latest activity', desc: 'most recently touched first', cmp: byLatest }
];
function activeSort() {
  for (var i = 0; i < SORTS.length; i++) if (SORTS[i].id === S.sort) return SORTS[i];
  return SORTS[0];
}
function sorted(tasks) {
  var cmp = activeSort().cmp;
  return tasks.slice().sort(function (a, b) { return cmp(a, b) || tieBreak(a, b); });
}
function renderSort() {
  $('sortSeg').innerHTML = SORTS.map(function (x) {
    return '<button type="button" data-action="sort" data-v="' + x.id + '" data-fk="sort:' + x.id + '" aria-pressed="' + (S.sort === x.id) + '">' + esc(x.label) + '</button>';
  }).join('');
}
function chipPri(p) { return p ? '<span class="pri ' + esc(p) + '">' + esc(p) + '</span>' : ''; }

function elapsed(ts) {
  var t = parseWhen(ts);
  if (t == null) return '';
  var m = Math.max(0, Math.floor((Date.now() - t) / 60000));
  return m < 1 ? 'under a minute' : m < 60 ? m + ' min' : Math.floor(m / 60) + 'h ' + (m % 60) + 'm';
}
function renderRuns() {
  var list = S.snap.runs || [];
  if (!list.length) return '';
  var h = '<div class="sec-title">Now running <span class="count">' + list.length +
    ' - one unattended run per checkout; queued runs wait their turn</span></div><div class="run-grid">';
  list.forEach(function (r) {
    h += '<div class="run-card"><div class="proj"><span>' + esc(identOf(r.project_name, r.task)) + '</span><span class="live">' +
      esc(RUN_LABEL[r.state] || r.state) + '</span></div><div class="ttl">' + esc(r.item_title) + '</div>' +
      '<div class="sub">' + esc(r.worker || '') + (r.entry ? ' (' + esc(r.entry) + ')' : '') +
      (r.started_at ? ' - running for ' + esc(elapsed(r.started_at)) : ' - waiting to start') + '</div>' +
      '<div class="row"><button type="button" class="btn sm" data-action="selectrun" data-key="' + esc(r.id) + '">' + ic('eye') + 'Log</button>' +
      laterButton('Cancel run', 'sm danger', 'stop', 'cancel') + '</div></div>';
  });
  return h + '</div>';
}
function renderRecent() {
  var rows = S.snap.recent_runs || [];
  if (!rows.length) return '';
  var h = '<div class="sec-title">Recent runs <span class="count">newest first; the run log keeps the details</span></div>' +
    '<table class="runs-table"><thead><tr><th>Ended</th><th>Item</th><th>Result</th><th></th></tr></thead><tbody>';
  rows.forEach(function (r) {
    h += '<tr class="click" data-action="selectrun" data-key="' + esc(r.id) + '"><td class="muted when">' + esc(ago(r.ended_at)) + '</td>' +
      '<td>' + esc(r.item_title) + '<div class="muted mono fs11">' + esc(identOf(r.project_name, r.task)) + '</div></td>' +
      '<td><span class="chip' + (r.state === 'accepted' ? '' : ' warnchip') + '">' + esc(RUN_LABEL[r.state] || r.state) + '</span> ' +
      '<span class="muted fs12">' + esc(r.code || '') + '</span></td><td></td></tr>';
  });
  return h + '</tbody></table>';
}

function needKey(n) { return n.item ? n.checkout + '|' + n.task + '|' + n.item : n.checkout + '|' + n.task; }
function needsHtml(task) {
  var list = task.needs || [];
  if (!list.length) return '';
  var h = '<div class="need-list">';
  list.forEach(function (n) {
    var k = needKey(n), action = n.item ? 'resolvesel' : 'resolvetask';
    h += '<div class="need-row"><div class="kind">' + ic('alert') + esc(NEED_KIND[n.kind] || n.kind) + '</div>' +
      '<div class="ttl">' + esc(n.title) + '</div>' +
      '<div class="why" title="' + esc(n.detail) + '">' + esc(n.detail) + '</div><div class="acts">' +
      '<button type="button" class="btn sm warn" data-action="' + action + '" data-key="' + esc(k) + '">' + ic('term') + 'Resolve in Claude Code</button>' +
      recheckButton(n, 'sm') + '</div></div>';
  });
  return h + '</div>';
}
function recheckButton(n, size) {
  var key = needKey(n);
  if (canDo('recheck')) return liveButton('Re-check', size, 'retry', 'recheck', key);
  return laterButton('Re-check', size, 'retry', 'recheck');
}

function iconFor(item) {
  switch (item.ui_state) {
    case 'in-flight': return ic('play', 'fill');
    case 'blocked': return ic('alert');
    case 'deferred': return ic('pause');
    case 'unknown': return ic('alert');
    default: return ic('play');
  }
}
function nodeHtml(task, item) {
  var k = ikey(task, item), sel = S.mode === 'item' && S.sel === k, sub = '';
  switch (item.ui_state) {
    case 'available':
      if (item.run && (item.run.state === 'queued' || item.run.state === 'starting' || item.run.state === 'running')) {
        sub = '<span class="t-run">' + esc((RUN_LABEL[item.run.state] || item.run.state).toLowerCase()) + '</span>';
      } else if (item.run && item.run.retryable) {
        sub = '<span class="t-warn">' + esc((RUN_LABEL[item.run.state] || item.run.state).toLowerCase()) + '</span>';
      } else {
        sub = runPill('Queue', 'queue', ikey(task, item));
      }
      break;
    case 'in-flight': sub = '<span class="t-run">in flight</span>'; break;
    case 'blocked': sub = '<span class="t-warn">needs you</span>'; break;
    case 'deferred': sub = 'deferred'; break;
    default: sub = '<span class="t-warn">' + esc(item.state) + '</span>';
  }
  var label = item.title + ' - ' + (STATE_LABEL[item.ui_state] || item.state);
  return '<div class="node st-' + esc(item.ui_state) + (sel ? ' sel' : '') + '">' +
    '<button type="button" class="bubble" data-action="select" data-key="' + esc(k) + '" aria-label="' + esc(label) +
    '" aria-pressed="' + sel + '" title="' + esc(label) + '">' + iconFor(item) + '</button>' +
    '<div class="nlabel" title="' + esc(item.title) + '">' + esc(item.title) + '</div><div class="nsub">' + sub + '</div></div>';
}
function findingsHtml(task) {
  var f = task.findings, all = f.errors.concat(f.warnings, f.item_errors);
  if (!all.length) return '';
  return '<details class="findings"><summary>' + all.length + ' validation finding(s)</summary><ul>' +
    all.map(function (m) { return '<li>' + esc(m) + '</li>'; }).join('') + '</ul></details>';
}
function markersHtml(task) {
  var need = needN(task), run = runN(task), q = queN(task), h = '';
  if (need) h += '<span class="mk need" title="Waiting on you: blocked items and blocked or invalid tasks">' + ic('tri') + need + (need === 1 ? ' needs you' : ' need you') + '</span>';
  if (run) h += '<span class="mk run" title="A job is running on this task">' + ic('spin', 'spin') + run + ' in flight</span>';
  if (q) h += '<span class="mk q" title="Waiting in the queue">' + q + ' queued</span>';
  return h;
}
function taskBody(task) {
  var avail = task.items.filter(function (i) { return i.ui_state === 'available'; }).length;
  var open = task.section === 'open';
  var nodes = task.items.map(function (it) { return nodeHtml(task, it); }).join('');
  if (open) {
    nodes += '<div class="node addnode"><button type="button" class="bubble" disabled aria-disabled="true" data-later="additem" title="Add item' + LATER_NOTE +
      '" aria-label="Add an item to ' + esc(task.title) + ' (' + 'arrives in a later increment)">' + ic('plus') + '</button><div class="nlabel muted">Add item</div><div class="nsub"></div></div>';
  }
  var empty = task.items.length ? '' :
    '<p class="muted fs12 mb0">' + (task.has_items_block ? 'No open items.' : 'No task_items block in plan.md (a pre-contract folder).') + '</p>';
  var ident = task.repo + ':' + task.stub;
  return '<div class="tbody"><div class="tmeta"><p class="tsum">' + (task.summary ? esc(task.summary) : '<span class="muted">No summary recorded.</span>') + '</p>' +
    '<dl class="idl"><dt>Identifier</dt><dd><button type="button" class="task-id-copy" data-action="copy" data-text="' + esc(ident) + '" title="Copy identifier">' + esc(ident) + '</button></dd>' +
    '<dt>Task path</dt><dd><button type="button" class="task-id-copy" data-action="copy" data-text="' + esc(task.id) + '" title="Copy task path">' + esc(task.id) + '</button></dd>' +
    '<dt>Working in</dt><dd class="mono">' + esc(task.working_root) + '</dd></dl>' +
    '<div class="tacts"><button type="button" class="btn sm" data-action="selecttask" data-key="' + esc(tkey(task)) + '">' + ic('eye') + 'Task details</button>' +
    (open && avail > 1 ? laterButton('Queue all available (' + avail + ')', 'sm', null, 'queueall') : '') + '</div></div>' +
    needsHtml(task) +
    (nodes ? '<div class="pipeline" role="list">' + nodes + '</div>' : '') +
    empty + findingsHtml(task) + '</div>';
}
function rowHtml(task) {
  var k = tkey(task), open = S.openTask === k, need = needN(task), run = runN(task);
  var cls = 'trow' + (open ? ' open' : '') + (need ? ' has-need' : run ? ' has-run' : '') + (task.section === 'deferred' ? ' deferred' : '');
  var state = task.section === 'open' ? '' : '<span class="chip' + (task.classification === 'invalid' ? ' badchip' : '') + '">' + esc(task.classification) + '</span>';
  var n = task.items.length;
  return '<div class="' + cls + '" data-row="' + esc(k) + '" data-age="' + brightness(task.last_activity).toFixed(2) + '">' +
    '<button type="button" class="row-main" data-action="toggletask" data-key="' + esc(k) + '" data-fk="row:' + esc(k) + '" aria-expanded="' + open + '" title="' + esc(task.summary || task.title) + '">' +
    '<span class="chev" aria-hidden="true"></span>' + (task.priority ? '<span class="pri ' + esc(task.priority) + '">' + esc(task.priority) + '</span>' : '<span class="pri">-</span>') +
    '<span class="c-title"><span class="ttl">' + esc(task.title) + '</span>' + identHtml(task.repo, task.id) + state + '</span>' +
    '<span class="c-marks">' + markersHtml(task) + '</span>' +
    '<span class="c-meta"><span>' + n + ' item' + (n === 1 ? '' : 's') + '</span><span>' + esc(ago(task.last_activity)) + '</span></span></button>' +
    (open ? taskBody(task) : '') + '</div>';
}
function foldSection(key, title, count, body, openByDefault, note) {
  var isOpen = S.open[key] === undefined ? !!openByDefault : S.open[key];
  return '<details class="sec" data-open="' + esc(key) + '"' + (isOpen ? ' open' : '') + '><summary>' + esc(title) +
    ' <span class="count">' + count + (note ? ' - ' + esc(note) : '') + '</span></summary><div class="sec-body">' + body + '</div></details>';
}
function rowList(tasks) { return '<div class="tlist">' + tasks.map(rowHtml).join('') + '</div>'; }
function renderTaskList() {
  var tasks = S.snap.tasks, srt = activeSort();
  var open = sorted(tasks.filter(function (t) { return t.section === 'open'; }));
  var def = sorted(tasks.filter(function (t) { return t.section === 'deferred'; }));
  var closed = tasks.filter(function (t) { return t.section === 'closed'; });  // newest activity first, as served
  var other = sorted(tasks.filter(function (t) { return t.section === 'other'; }));
  var legend = '<div class="listbar"><div class="legend">Markers:<span class="mk need">' + ic('tri') + 'needs you</span> blocked items or tasks' +
    '<span class="mk run">' + ic('spin', 'spin') + 'in flight</span> a job is running</div></div>';
  var h = foldSection('open', 'Open tasks', open.length, legend + (open.length ? rowList(open) :
    '<p class="nomatch">' + (tasks.length ? 'No open tasks match the current filter.' : 'No tasks match the current filter.') + '</p>'),
    true, 'sorted by ' + srt.label + ': ' + srt.desc);
  if (def.length) h += foldSection('deferred', 'Deferred tasks', def.length, rowList(def), false);
  if (closed.length) h += foldSection('closed', 'Closed tasks', closed.length, rowList(closed), false);
  if (other.length) h += foldSection('other', 'Other (invalid, remote, orphaned)', other.length, rowList(other), false);
  if (S.snap.hidden_closed_tasks) h += '<p class="hidden-note">' + S.snap.hidden_closed_tasks + ' older closed task(s) are not listed.</p>';
  return h;
}
function renderLog() {
  var rows = S.snap.activity;
  if (!rows.length) return '';
  var h = '<div class="sec-title">Task log <span class="count">newest log.md entries across the listed tasks</span></div>';
  h += '<table class="runs-table activity-table"><thead><tr><th>When</th><th>Task</th><th>Entry</th></tr></thead><tbody>';
  rows.forEach(function (r) {
    h += '<tr class="click" data-action="selecttask" data-key="' + esc(r.checkout + '|' + r.task) + '"><td class="muted when">' + esc(ago(r.timestamp)) + '</td>' +
      '<td>' + esc(r.task_title) + '<div class="muted mono fs11">' + esc(identOf(r.project_name, r.task)) + '</div></td>' +
      '<td>' + esc(r.detail) + '</td></tr>';
  });
  return h + '</tbody></table>';
}
function renderActivity() {
  var live = (S.snap.runs || []).length, recent = (S.snap.recent_runs || []).length, log = S.snap.activity.length;
  var counts = live + ' running, ' + recent + ' recent run(s), ' + log + ' log entr' + (log === 1 ? 'y' : 'ies');
  var body = renderRuns() + renderRecent() + renderLog();
  return '<details class="sec" data-open="activity"' + (S.open.activity ? ' open' : '') + '><summary>Recent activity <span class="count">' + counts +
    '</span></summary><div class="sec-body">' + (body || '<p class="empty">No runs or dated log entries yet.</p>') + '</div></details>';
}
function cmdBox(handoff) {
  var rows = handoff.commands.map(function (c, i) {
    return '<div class="cmdrow"><span class="n">' + (i + 1) + '</span><code>' + esc(c) + '</code>' +
      '<button type="button" class="btn sm" data-action="copy" data-text="' + esc(c) + '">' + ic('copy') + 'Copy</button></div>';
  }).join('');
  return '<div class="cmdbox">' + rows + '<div class="cmdcap">' + esc(handoff.caption) + '</div></div>';
}
function taskPanelBody(task) {
  var h = '';
  if (task.classification === 'blocked' || task.classification === 'invalid') {
    var rec = (task.needs || []).filter(function (n) { return !n.item; })[0];
    h += '<div class="callout"><strong>' + (task.classification === 'blocked' ? 'This task is blocked' : 'This task does not validate') + '</strong><p>' +
      esc(rec ? rec.detail : task.findings.errors[0] || '') + '</p></div>';
  }
  if (task.summary) h += '<div class="sec-title">Task summary</div><p class="fs13">' + esc(task.summary) + '</p>';
  var key = 'T:' + tkey(task);
  h += '<div class="acts"><button type="button" class="btn warn" data-action="resolve" data-key="' + esc(key) + '" aria-expanded="' + !!S.resolve[key] + '">' + ic('term') + 'Resolve in Claude Code</button></div>';
  if (S.resolve[key]) h += cmdBox(task.handoff);
  h += findingsHtml(task);
  h += '<div class="sec-title">Recent activity on this task</div>';
  h += task.updates.length ? task.updates.map(function (u) {
    return '<div class="mini-run"><span class="m">' + esc(u.date + (u.time ? ' ' + u.time : '')) + '</span><span class="t">' + esc(u.detail) + '</span></div>';
  }).join('') : '<p class="muted fs13">No dated log entries.</p>';
  return h;
}
function panelTask() {
  var task = findTask(S.selTask);
  if (!task) return '';
  var h = '<div class="p-head"><div class="crumbs"><button type="button" class="task-id-copy" data-action="copy" data-text="' + esc(task.id) + '" title="Copy task path">' + esc(task.repo + ':' + task.stub) + '</button></div>' +
    '<span class="grow"></span><button type="button" class="btn sm" data-action="closepanel" aria-label="Close panel">' + ic('close') + '</button></div>' +
    '<h2>' + esc(task.title) + '</h2><div class="badges"><span class="badge" data-color="' + (task.classification === 'blocked' ? 'warn' : 'accent') + '">' + esc(task.classification) + '</span>' + chipPri(task.priority) + '</div>';
  h += taskPanelBody(task);
  h += '<div class="sec-title">Items</div><ul class="item-list">' + (task.items.length ? task.items.map(function (it) {
    return '<li><span class="chip">' + esc(STATE_LABEL[it.ui_state] || it.state) + '</span><span class="t"><button type="button" class="linkbtn" data-action="select" data-key="' + esc(ikey(task, it)) + '">' + esc(it.title) + '</button></span></li>';
  }).join('') : '<li class="muted">No open items.</li>') + '</ul>';
  return h;
}
function planBlock(detail) {
  var ps = detail.plan_section;
  if (ps.error) return '<div class="callout bad"><strong>plan.md could not be read</strong><p>' + esc(ps.error) + '</p></div>';
  if (ps.status === 'found') {
    return '<div class="card"><div class="secbody">' + esc(ps.body) + (ps.truncated ? '\n[truncated]' : '') + '</div></div>' +
      '<p class="hint">' + esc(ps.heading) + ' in ' + esc(ps.source) + '</p>';
  }
  var why = { missing: 'No section for this item', empty: 'The section is empty', duplicate: 'More than one section matches this item' }[ps.status] || ps.status;
  return '<div class="callout"><strong>' + esc(why) + '</strong><p>An autonomous run needs exactly one non-empty section headed with the item id ' +
    '(for example <span class="mono">### ' + esc(detail.item.id) + ' -- title</span>) in ' + esc(ps.source) + '.</p></div>';
}
function panelItem() {
  var f = findItem(S.sel);
  if (!f) return '';
  var task = f.task, it = f.item, detail = S.detail[S.sel];
  var ui = it.ui_state, color = STATE_COLOR[ui] || 'var(--muted)';
  var h = '<div class="p-head"><div class="crumbs"><button type="button" class="task-id-copy" data-action="copy" data-text="' + esc(task.id) + '" title="Copy task path">' + esc(task.repo + ':' + task.stub) + '</button></div>' +
    '<span class="grow"></span><button type="button" class="btn sm" data-action="closepanel" aria-label="Close panel">' + ic('close') + '</button></div>' +
    '<h2>' + esc(it.title) + '</h2><div class="badges"><span class="badge" data-color="' + esc(ui) + '">' + esc(STATE_LABEL[ui] || it.state) + '</span>' +
    chipPri(it.priority) + '<span class="chip mono">' + esc(it.id) + '</span></div>';
  if (ui === 'blocked') {
    h += '<div class="callout"><strong>Waiting for you</strong><p>' + esc(it.note || 'The item is blocked on you; no note was recorded.') + '</p></div>';
  } else if (ui === 'in-flight') {
    h += '<div class="callout info"><strong>In flight</strong><p>' + esc(it.note || 'This item is being worked in Claude Code.') + '</p></div>';
  } else if (ui === 'deferred') {
    h += '<div class="callout"><strong>Deferred</strong><p>' + esc(it.note || 'Not eligible to run until it is made available again.') + '</p></div>';
  } else if (ui === 'unknown') {
    h += '<div class="callout bad"><strong>Unknown item state</strong><p>State ' + esc(it.state) + ' is not in the task vocabulary; <span class="mono">task validate</span> reports it.</p></div>';
  } else if (it.note) {
    h += '<p class="fs13">' + esc(it.note) + '</p>';
  }
  var key = S.sel;
  h += '<div class="acts">';
  h += '<button type="button" class="btn warn" data-action="resolve" data-key="' + esc(key) + '" aria-expanded="' + !!S.resolve[key] + '">' + ic('term') + 'Resolve in Claude Code</button>';
  var live = it.run && (it.run.state === 'queued' || it.run.state === 'starting' || it.run.state === 'running');
  if (ui === 'available' && !live) h += runButton('Queue', 'primary', 'play', 'queue', key) + laterButton('Defer', '', null, 'defer');
  if (ui === 'available' && live) h += '<span class="chip">' + esc(RUN_LABEL[it.run.state]) + '</span>';
  if (ui === 'available' && it.run && it.run.retryable) h += runButton('Retry', '', 'retry', 'retry', it.run.id + '|' + task.checkout + '|' + task.id);
  if (ui === 'deferred') h += laterButton('Undefer', 'primary', null, 'undefer');
  if (ui === 'blocked') h += recheckButton({ item: it.id, project: task.project, task: task.id }, '');
  h += '</div>';
  if (S.resolve[key]) {
    h += detail && detail.handoff ? cmdBox(detail.handoff) : (task.handoff ? cmdBox(task.handoff) : '');
  }
  h += '<div class="sec-title">Run controls</div><div class="card"><dl class="kv mb0">' +
    '<dt>Model</dt><dd><span class="seg" role="group" aria-label="Model"><button type="button" disabled aria-disabled="true" data-later="model">Claude</button><button type="button" disabled aria-disabled="true" data-later="model">Codex</button></span></dd>' +
    '<dt>Effort</dt><dd><select disabled aria-label="Effort" data-later="effort"><option>medium</option></select></dd>' +
    '<dt>Runs in</dt><dd class="mono fs12">' + esc(task.working_root) + '</dd></dl>' +
    '<div class="acts">' + laterButton('Cancel run', 'sm danger', 'stop', 'cancel') + '</div>' +
    '<p class="hint">Model, effort and run options arrive in a later increment: a run uses the machine defaults from ' +
    'task.local.yaml. Cancel run arrives with them; a run ends by itself or at its time limit.</p></div>';
  if (it.run) {
    h += '<div class="sec-title">Latest run</div><div class="card"><dl class="kv mb0"><dt>State</dt><dd>' + esc(RUN_LABEL[it.run.state] || it.run.state) +
      '</dd><dt>Result</dt><dd>' + esc(it.run.code || '') + (it.run.detail ? ' - ' + esc(it.run.detail) : '') + '</dd></dl>' +
      '<div class="acts"><button type="button" class="btn sm" data-action="selectrun" data-key="' + esc(it.run.id) + '">' + ic('eye') + 'Run log</button></div></div>';
  }
  h += '<div class="sec-title">plan.md section</div>';
  if (!detail) h += '<p class="muted fs13">Loading...</p>';
  else if (detail.error) h += '<div class="callout bad"><strong>Could not load the item</strong><p>' + esc(detail.error) + '</p></div>';
  else h += planBlock(detail);
  if (task.summary) h += '<div class="sec-title">Task summary</div><p class="fs13">' + esc(task.summary) + '</p>';
  h += '<div class="sec-title">Recent activity on this task</div>';
  h += task.updates.length ? task.updates.map(function (u) {
    return '<div class="mini-run"><span class="m">' + esc(u.date + (u.time ? ' ' + u.time : '')) + '</span><span class="t">' + esc(u.detail) + '</span></div>';
  }).join('') : '<p class="muted fs13">No dated log entries.</p>';
  return h;
}
function panelRun() {
  var run = null, rows = (S.snap.runs || []).concat(S.snap.recent_runs || []);
  rows.forEach(function (r) { if (r.id === S.selRun) run = r; });
  if (!run) return '';
  var log = S.runLog[run.id];
  var h = '<div class="p-head"><div class="crumbs"><span class="mono">' + esc(identOf(run.project_name, run.task)) + '</span></div>' +
    '<span class="grow"></span><button type="button" class="btn sm" data-action="closepanel" aria-label="Close panel">' + ic('close') + '</button></div>' +
    '<h2>' + esc(run.item_title) + '</h2><div class="badges"><span class="badge" data-color="' + (run.state === 'accepted' ? 'good' : run.state === 'running' ? 'run' : 'warn') + '">' +
    esc(RUN_LABEL[run.state] || run.state) + '</span><span class="chip mono">' + esc(run.id) + '</span></div>';
  if (run.code || run.detail) h += '<div class="callout"><strong>' + esc(run.code || run.state) + '</strong><p>' + esc(run.detail || '') + '</p></div>';
  h += '<div class="acts">';
  if (run.retryable) h += runButton('Retry', '', 'retry', 'retry', run.id + '|' + run.checkout + '|' + run.task);
  if (run.state === 'blocked' || run.state === 'crashed') h += '<span class="hint">Resolve it in Claude Code, then Re-check the item.</span>';
  if (run.state === 'queued' || run.state === 'starting' || run.state === 'running') h += laterButton('Cancel run', 'sm danger', 'stop', 'cancel');
  h += '</div><div class="sec-title">Run log</div><pre class="logtail">' + esc(log ? log.text : 'Loading...') + '</pre>';
  return h;
}
function panelHtml() {
  return S.mode === 'item' ? panelItem() : S.mode === 'task' ? panelTask() : S.mode === 'run' ? panelRun() : '';
}
function renderPanel() {
  var pn = $('panel');
  if (!S.snap) { pn.innerHTML = ''; return; }
  var scroll = pn.scrollTop, html = panelHtml(), has = html !== '';
  pn.innerHTML = html;
  pn.scrollTop = scroll;
  pn.classList.toggle('open', S.panelOpen && has);
  $('layout').classList.toggle('has-panel', has);
  $('scrim').classList.toggle('on', S.panelOpen && has);
  applyDynamic(pn);
}
function applyDynamic(root) {
  var nodes = root.querySelectorAll('[data-age]'), i;
  for (i = 0; i < nodes.length; i++) nodes[i].style.setProperty('--age', nodes[i].getAttribute('data-age'));
  nodes = root.querySelectorAll('.badge[data-color]');
  for (i = 0; i < nodes.length; i++) {
    var c = nodes[i].getAttribute('data-color');
    nodes[i].style.setProperty('--c', STATE_COLOR[c] || 'var(--' + c + ')');
  }
}
function render(opts) {
  if (!S.snap) return;
  var ae = document.activeElement, fk = ae && ae.getAttribute ? ae.getAttribute('data-fk') : null;
  renderBanners(); renderStatus(); renderProjectSelect(); renderSort();
  var main = $('main');
  main.innerHTML = renderTaskList() + renderActivity();
  applyDynamic(main);
  renderPanel();
  if (fk) {
    var again = document.querySelector('[data-fk="' + fk.replace(/"/g, '\\"') + '"]');
    if (again) again.focus({ preventScroll: true });
  }
  if (opts && opts.scrollTo) {
    var row = document.querySelector('[data-row="' + opts.scrollTo.replace(/"/g, '\\"') + '"]');
    if (row) row.scrollIntoView({ block: 'nearest' });
  }
}

/* ================= actions ================= */
function copyText(el) {
  var txt = el.getAttribute('data-text'), orig = el.innerHTML;
  function done(ok) { el.textContent = ok ? 'Copied' : 'Copy failed'; setTimeout(function () { el.innerHTML = orig; }, 1400); }
  function legacy() {
    var ta = document.createElement('textarea');
    ta.value = txt; ta.setAttribute('readonly', '');
    document.body.appendChild(ta); ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    ta.remove(); done(ok);
  }
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(txt).then(function () { done(true); }, legacy);
  else legacy();
}
function selectItem(k, withResolve) {
  var p = splitIKey(k);
  S.openTask = p.project + '|' + p.task;
  S.sel = k; S.mode = 'item'; S.panelOpen = true;
  if (withResolve) S.resolve[k] = true;
  render();
  fetchDetail(k);
}
function selectTask(k, withResolve) {
  S.selTask = k; S.mode = 'task'; S.panelOpen = true;
  if (withResolve) S.resolve['T:' + k] = true;
  render();
}
function actionResult(label, r) {
  if (r.status >= 200 && r.status < 300) {
    S.notice = null;
    return;
  }
  var e = (r.body && r.body.error) || {};
  var text = e.message || ('HTTP ' + r.status);
  S.notice = { kind: r.status === 409 ? 'info' : 'bad', title: label + ' was not done' + (e.blocked ? ' - the task is now blocked' : ''), text: text };
}
function doQueue(el) {
  var p = splitIKey(el.getAttribute('data-key')), f = findItem(el.getAttribute('data-key'));
  if (!f) return;
  send('/api/v1/items/' + encodeURIComponent(p.project) + '/' + encodeURIComponent(p.task) + '/' + encodeURIComponent(p.item) + '/queue',
    { expected_revision: f.task.revision }).then(function (r) { actionResult('Queue', r); pollNow(); });
}
function doRecheck(el) {
  var k = el.getAttribute('data-key'), p = splitIKey(k), task = findTask(p.project + '|' + p.task);
  if (!task) return;
  send('/api/v1/items/' + encodeURIComponent(p.project) + '/' + encodeURIComponent(p.task) + '/' + encodeURIComponent(p.item || '-') + '/recheck',
    { expected_revision: task.revision }).then(function (r) { actionResult('Re-check', r); pollNow(); });
}
function doRetry(el) {
  var parts = el.getAttribute('data-key').split('|'), task = findTask(parts[1] + '|' + parts[2]);
  if (!task) return;
  send('/api/v1/runs/' + encodeURIComponent(parts[0]) + '/retry', { expected_revision: task.revision })
    .then(function (r) { actionResult('Retry', r); pollNow(); });
}
function toggleTask(el) {
  var k = el.getAttribute('data-key'), was = S.openTask;
  S.openTask = was === k ? null : k;
  if (S.mode === 'item' && S.sel) {
    var p = splitIKey(S.sel);
    if (S.openTask !== p.project + '|' + p.task) { S.sel = null; S.mode = 'none'; S.panelOpen = false; }
  }
  render({ scrollTo: S.openTask });
}
function selectRun(id) {
  S.selRun = id; S.mode = 'run'; S.panelOpen = true;
  render();
  fetchRunLog(id);
}
var ACTIONS = {
  queue: doQueue,
  recheck: doRecheck,
  retry: doRetry,
  selectrun: function (el) { selectRun(el.getAttribute('data-key')); },
  select: function (el) { selectItem(el.getAttribute('data-key'), false); },
  selecttask: function (el) { selectTask(el.getAttribute('data-key'), false); },
  resolvesel: function (el) { selectItem(el.getAttribute('data-key'), true); },
  resolvetask: function (el) { selectTask(el.getAttribute('data-key'), true); },
  resolve: function (el) { var k = el.getAttribute('data-key'); S.resolve[k] = !S.resolve[k]; renderPanel(); },
  toggletask: toggleTask,
  sort: function (el) { S.sort = el.getAttribute('data-v'); render(); },
  closepanel: function () { S.sel = null; S.selTask = null; S.selRun = null; S.mode = 'none'; S.panelOpen = false; render(); },
  copy: function (el) { copyText(el); },
  refresh: function () { S.refreshNext = true; pollNow(); }
};
document.addEventListener('click', function (e) {
  var el = e.target.closest('[data-action]');
  if (!el || el.disabled) return;
  var fn = ACTIONS[el.getAttribute('data-action')];
  if (!fn) return;
  e.stopPropagation();
  fn(el);
});
document.addEventListener('toggle', function (e) {
  var k = e.target.getAttribute && e.target.getAttribute('data-open');
  if (k) S.open[k] = e.target.open;
}, true);
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape' && S.mode !== 'none') ACTIONS.closepanel();
});
document.addEventListener('visibilitychange', function () {
  if (document.visibilityState === 'visible') pollNow(); else schedule();
});
$('projectSelect').addEventListener('change', function (e) { S.project = e.target.value; pollNow(); });
var searchTimer = null;
$('search').addEventListener('input', function (e) {
  S.q = e.target.value.trim();
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(pollNow, 200);
});

renderStatus();
renderBanners();
renderSort();
if (!TOKEN) {
  S.conn = 'auth';
  renderBanners(); renderStatus();
} else {
  poll();
}
})();
