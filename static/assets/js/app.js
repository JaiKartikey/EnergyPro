'use strict';

/* EnergyPro dashboard – plain JavaScript, talks to the Python (Flask) API in /api/ over HTTP (JSON).
 * The browser polls api/status every 2 s; the ESP32 independently syncs with
 * api/device/sync. MySQL sits in the middle, so the page and the node never talk directly. */

const POLL_MS = 2000;
const HISTORY_LIMIT = 50;

const PAGES = {
  dashboard: ['Energy Dashboard', 'Real-time monitoring'],
  account:   ['Account', 'Registered RFID cards and prepaid balances'],
  control:   ['Control', 'Relay switching and session control'],
  settings:  ['Settings', 'Tariff and protection limits'],
  reports:   ['Reports & Analytics', `Live energy consumption charts (last ${HISTORY_LIMIT} readings)`],
  help:      ['Help', 'How the system works'],
};

const EVENT_TAGS = {
  rfid_login: 'ok', rfid_logout: 'info', rfid_denied: 'bad', rfid_no_balance: 'bad',
  remote_on: 'ok', remote_off: 'info', remote_logout: 'info', button_on: 'ok', button_off: 'info',
  cutoff: 'bad', fault: 'bad', fault_cutoff: 'bad', theft: 'bad', low_balance: 'bad',
  fault_cleared: 'ok', theft_cleared: 'ok', recharge: 'ok',
};

const state = { page: 'dashboard', status: null, users: [], charts: null, pollTimer: null };

/* ---------- helpers ---------- */
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function fmt(n, digits) {
  return n === null || n === undefined || Number.isNaN(Number(n)) ? '--' : Number(n).toFixed(digits);
}
function timeOf(dt) { return dt ? String(dt).slice(11, 19) : '--'; }

async function api(path, body) {
  const opts = body === undefined
    ? { cache: 'no-store' }
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const res = await fetch('api/' + path, opts);
  if (res.status === 401 && path !== 'login') {      // dashboard password is on and we're not logged in
    showLogin(true);
    throw new Error('Please log in');
  }
  let data;
  try { data = await res.json(); } catch {
    throw new Error(`Server returned HTTP ${res.status} without JSON. Is the Python server (app.py) running?`);
  }
  if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function toast(msg, kind = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function setDot(id, cls) {
  const el = document.getElementById(id);
  if (el) el.className = 'dot ' + (cls || '');
}

/* ---------- routing ---------- */
function route() {
  const name = location.hash.slice(1);
  const page = PAGES[name] ? name : 'dashboard';
  state.page = page;
  $$('.page').forEach(s => { s.hidden = s.dataset.page !== page; });
  $$('.nav a').forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + page));
  $('#pageTitle').textContent = PAGES[page][0];
  $('#pageSub').textContent = PAGES[page][1];
  refreshPage();
}

function refreshPage() {
  const jobs = {
    account: loadUsers,
    control: loadEvents,
    settings: loadSettings,
    reports: loadHistory,
  };
  if (jobs[state.page]) jobs[state.page]().catch(err => console.warn(err));
}

/* ---------- live status (all pages) ---------- */
async function poll() {
  clearTimeout(state.pollTimer);
  if (state.needLogin) { state.pollTimer = setTimeout(poll, POLL_MS); return; }
  try {
    const s = await api('status');
    state.status = s;
    renderStatus(s);
    // pages with live content refresh alongside the status poll (settings form is left alone)
    if (state.page === 'reports') await loadHistory();
    if (state.page === 'control') await loadEvents();
    if (state.page === 'account') await loadUsers();
  } catch (err) {
    if (!state.needLogin) renderServerDown(err.message);
  } finally {
    state.pollTimer = setTimeout(poll, POLL_MS);
  }
}

/* ---------- optional dashboard login (only when ADMIN_PASSWORD is set on the server) ---------- */
function showLogin(show) {
  state.needLogin = show;
  $('#loginOverlay').hidden = !show;
  if (show) $('#loginForm [name=password]').focus();
}

function renderServerDown(msg) {
  $('#nodePillText').textContent = 'Server unreachable';
  $('#nodePill .dot').className = 'dot bad';
  showBanner('bad', 'Cannot reach the server: ' + msg);
}

function showBanner(kind, html) {
  const b = $('#banner');
  if (!kind) { b.hidden = true; return; }
  b.className = 'banner ' + kind;
  b.innerHTML = html;
  b.hidden = false;
}

function renderStatus(s) {
  const d = s.device, u = s.user, r = s.reading;

  // tiles
  $('#tBalance').textContent = u ? fmt(u.balance, 4) : '--';
  $('#tBalanceSub').textContent = u ? `Available credit · ${u.name}` : 'No student logged in';
  $('#tVoltage').textContent = r ? fmt(r.voltage, 1) : '--';
  $('#tCurrent').textContent = r ? fmt(r.current, 3) : '--';
  $('#tPower').textContent = r ? fmt(r.power, 1) : '--';
  $$('[data-page="dashboard"] .tile').forEach(t => t.classList.toggle('stale', !d.online));

  // system status
  $('#sPower').textContent = d.relay ? 'ON' : 'OFF';
  setDot('sPowerDot', d.relay ? 'ok' : 'bad');
  const sensorFault = d.fault && (!r || r.voltage === null);
  $('#sFault').textContent = d.fault ? (sensorFault ? 'SENSOR' : 'FAULT') : 'OK';
  setDot('sFaultDot', d.fault ? 'bad' : 'ok');
  $('#sTheft').textContent = d.theft ? 'ALERT' : 'OK';
  setDot('sTheftDot', d.theft ? 'bad' : 'ok');
  $('#sEnergy').textContent = fmt(d.total_energy_wh, 2) + ' Wh';
  $('#sUser').textContent = u ? `${u.name}${u.room ? ' (' + u.room + ')' : ''}` : 'None';
  setDot('sUserDot', u ? 'ok' : '');
  $('#sNode').textContent = d.online ? 'Online' : (d.last_seen ? 'Offline since ' + timeOf(d.last_seen) : 'Never connected');
  setDot('sNodeDot', d.online ? 'ok' : 'bad');

  // sidebar + header + footer
  $('#nodePillText').textContent = `${d.name} · ${d.online ? 'online' : 'offline'}`;
  $('#nodePill .dot').className = 'dot ' + (d.online ? 'ok' : 'bad');
  const stamp = r ? timeOf(r.time) : '--';
  $('#lastUpdated').textContent = 'Last updated: ' + stamp;
  $('#footerUpdate').textContent = 'Last Update: ' + stamp;

  // banner: most important problem first
  if (d.theft) showBanner('bad', '<b>Theft alert:</b> current is flowing while the supply is OFF. Check the room wiring for a bypass.');
  else if (d.fault) showBanner('bad', sensorFault
    ? '<b>Sensor fault:</b> the PZEM-004T energy meter is not responding.'
    : '<b>Voltage fault:</b> line voltage is outside the safe range, so the supply was cut.');
  else if (!d.online) showBanner('warn', d.last_seen
    ? `<b>IoT node offline</b> since ${esc(d.last_seen)}. Values shown are the last ones received.`
    : '<b>IoT node has not connected yet.</b> Power on the ESP32, or run tools/simulate.mjs to test without hardware.');
  else if (s.low_balance) showBanner('warn', `<b>Low balance:</b> ${esc(u.name)} has ₹${fmt(u.balance, 2)} left. <a href="#account">Recharge</a>`);
  else if (s.unknown_card) showBanner('info', `Unknown card <b>${esc(s.unknown_card.rfid_uid)}</b> was scanned at ${timeOf(s.unknown_card.created_at)}. <a href="#account">Register it</a>`);
  else showBanner(null);

  // unknown card -> prefill the register form if it's empty
  const uidInput = $('#newUid');
  if (s.unknown_card && uidInput && !uidInput.value && document.activeElement !== uidInput) {
    uidInput.value = s.unknown_card.rfid_uid;
  }

  renderControl(s);
  renderSession(s);
}

function renderControl(s) {
  const d = s.device;
  const el = $('#relayState');
  el.textContent = d.relay ? 'ON' : 'OFF';
  el.className = 'relay-state ' + (d.relay ? 'on' : 'off');
  $('#relayNote').textContent = d.online
    ? `Commands reach the ESP32 on its next sync (every ${(s.settings.poll_ms / 1000).toFixed(1)} s).`
    : 'Node is offline. Commands will apply when it reconnects.';
  const rows = [
    ['Room / node', d.name],
    ['Status', d.online ? 'Online' : 'Offline'],
    ['Last seen', d.last_seen || 'never'],
    ['Node IP', d.ip || '--'],
    ['Wi-Fi signal', d.rssi !== null ? d.rssi + ' dBm' : '--'],
    ['Frequency', s.reading && s.reading.frequency !== null ? fmt(s.reading.frequency, 1) + ' Hz' : '--'],
    ['Power factor', s.reading && s.reading.pf !== null ? fmt(s.reading.pf, 2) : '--'],
    ['Tariff', '₹' + fmt(s.settings.tariff_per_kwh, 2) + ' / kWh'],
  ];
  $('#nodeDetails').innerHTML = rows.map(([k, v]) => `<li><span>${esc(k)}</span><b>${esc(v)}</b></li>`).join('');
}

function renderSession(s) {
  const u = s.user;
  $('#sessionBox').innerHTML = u
    ? `<div class="big">${esc(u.name)}</div>
       <div>Room <b>${esc(u.room || '--')}</b> · Roll <b>${esc(u.roll_no || '--')}</b> · Card <b>${esc(u.rfid_uid)}</b></div>
       <div>Balance <b>₹${fmt(u.balance, 4)}</b> · Supply <b>${s.device.relay ? 'ON' : 'OFF'}</b></div>
       <div class="actions"><button class="btn btn-ghost" data-control="logout">End session</button></div>`
    : 'No student logged in. Tap a registered RFID card on the reader.';
}

/* ---------- account ---------- */
async function loadUsers() {
  const data = await api('users');
  state.users = data.users;
  const tbody = $('#usersBody');
  $('#userCount').textContent = `${data.users.length} card${data.users.length === 1 ? '' : 's'}`;
  tbody.innerHTML = data.users.length ? data.users.map(u => `
    <tr class="${u.id === data.active_user_id ? 'is-active' : ''}">
      <td>${esc(u.name)}${u.id === data.active_user_id ? ' <span class="tag info">logged in</span>' : ''}</td>
      <td>${esc(u.roll_no || '--')}</td>
      <td>${esc(u.room || '--')}</td>
      <td><code>${esc(u.rfid_uid)}</code></td>
      <td class="num">${fmt(u.balance, 2)}</td>
      <td>${u.active ? '<span class="tag ok">Active</span>' : '<span class="tag bad">Blocked</span>'}</td>
      <td>
        <button class="btn btn-link" data-user-action="recharge" data-id="${u.id}">Recharge</button>
        <button class="btn btn-link" data-user-action="toggle" data-id="${u.id}">${u.active ? 'Block' : 'Unblock'}</button>
        <button class="btn btn-link danger" data-user-action="delete" data-id="${u.id}">Delete</button>
      </td>
    </tr>`).join('') : '<tr><td colspan="7" class="muted">No cards registered yet.</td></tr>';

  // keep the recharge dropdown in sync without losing the current choice
  const sel = $('#rechargeUser');
  if (document.activeElement !== sel) {
    const keep = sel.value || (data.active_user_id ? String(data.active_user_id) : '');
    sel.innerHTML = data.users.map(u => `<option value="${u.id}">${esc(u.name)} (₹${fmt(u.balance, 2)})</option>`).join('');
    if (keep && data.users.some(u => String(u.id) === keep)) sel.value = keep;
  }
}

async function userAction(action, id) {
  const u = state.users.find(x => x.id === id);
  if (!u) return;
  if (action === 'recharge') {
    $('#rechargeUser').value = String(id);
    $('#userRecharge [name=amount]').focus();
    return;
  }
  if (action === 'delete' && !confirm(`Delete ${u.name} and card ${u.rfid_uid}? Their balance is lost.`)) return;
  await api('users', { action, id });
  toast(action === 'delete' ? `${u.name} deleted` : `${u.name} ${u.active ? 'blocked' : 'unblocked'}`, 'ok');
  await loadUsers();
  poll();
}

/* ---------- control & events ---------- */
async function control(action) {
  const res = await api('control', { action });
  const text = { on: 'Power ON sent', off: 'Power OFF sent', logout: 'Session ended' }[action];
  toast(res.online ? text : text + ' (node offline, applies on reconnect)', 'ok');
  poll();
}

async function loadEvents() {
  const data = await api('events?limit=40');
  $('#eventsList').innerHTML = data.events.length ? data.events.map(e => `
    <li><time>${esc(e.created_at.slice(5))}</time>
        <span class="tag ${EVENT_TAGS[e.type] || 'info'}">${esc(e.type.replace(/_/g, ' '))}</span>
        <span>${esc(e.message)}</span></li>`).join('') : '<li class="muted">No activity yet.</li>';
}

/* ---------- settings ---------- */
async function loadSettings() {
  const data = await api('settings');
  const f = $('#settingsForm');
  f.device_name.value = data.device_name;
  for (const [k, v] of Object.entries(data.settings)) {
    if (!f.elements[k]) continue;
    if (f.elements[k].type === 'checkbox') f.elements[k].checked = !!v;
    else f.elements[k].value = v;
  }
}

/* ---------- reports ---------- */
function makeCharts() {
  if (state.charts) return state.charts;
  if (typeof Chart === 'undefined') { $('#chartNote').hidden = false; return null; }
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.font.size = 11;
  Chart.defaults.color = '#6b7280';
  const base = {
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { display: false } },
    scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } }, y: { grid: { color: '#eef1f6' } } },
    elements: { point: { radius: 2 }, line: { tension: 0.25, borderWidth: 2 } },
  };
  const clone = o => JSON.parse(JSON.stringify(o));

  const power = new Chart($('#powerChart'), {
    type: 'line',
    data: { labels: [], datasets: [{ label: 'Power (W)', data: [], borderColor: '#3b8fd6', backgroundColor: 'rgba(59,143,214,.12)', fill: true }] },
    options: Object.assign(clone(base), { scales: { ...clone(base.scales), y: { ...clone(base.scales.y), beginAtZero: true, title: { display: true, text: 'Watts' } } } }),
  });
  const balance = new Chart($('#balanceChart'), {
    type: 'line',
    data: { labels: [], datasets: [{ label: 'Balance (₹)', data: [], borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,.14)', fill: true, spanGaps: true }] },
    options: Object.assign(clone(base), { scales: { ...clone(base.scales), y: { ...clone(base.scales.y), title: { display: true, text: 'Rs' } } } }),
  });
  const vcOpts = clone(base);
  vcOpts.plugins.legend = { display: true, position: 'top' };
  vcOpts.scales = {
    x: clone(base.scales.x),
    y: { position: 'left', grid: { color: '#eef1f6' }, title: { display: true, text: 'Volts' } },
    y1: { position: 'right', beginAtZero: true, grid: { drawOnChartArea: false }, title: { display: true, text: 'Amps' } },
  };
  const vc = new Chart($('#vcChart'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'Voltage (V)', data: [], borderColor: '#f5c518', backgroundColor: '#f5c518', yAxisID: 'y' },
        { label: 'Current (A)', data: [], borderColor: '#e04646', backgroundColor: '#e04646', yAxisID: 'y1' },
      ],
    },
    options: vcOpts,
  });
  state.charts = { power, balance, vc };
  return state.charts;
}

async function loadHistory() {
  const data = await api(`history?limit=${HISTORY_LIMIT}`);
  const st = data.stats;
  $('#rPeak').textContent = fmt(st.peak_power, 1);
  $('#rAvg').textContent = fmt(st.avg_power, 1);
  $('#rEnergy').textContent = fmt(st.total_energy_wh, 2);
  $('#rSpent').textContent = fmt(st.total_spent, 4);

  const charts = makeCharts();
  if (!charts) return;
  const rows = data.readings;
  const labels = rows.map(r => r.t);
  charts.power.data.labels = labels;
  charts.power.data.datasets[0].data = rows.map(r => r.power);
  charts.balance.data.labels = labels;
  charts.balance.data.datasets[0].data = rows.map(r => r.balance);
  charts.vc.data.labels = labels;
  charts.vc.data.datasets[0].data = rows.map(r => r.voltage);
  charts.vc.data.datasets[1].data = rows.map(r => r.current);
  Object.values(charts).forEach(c => c.update('none'));
}

/* ---------- wiring ---------- */
async function withButton(btn, fn) {
  if (btn) btn.disabled = true;
  try { await fn(); } catch (err) { toast(err.message, 'bad'); } finally { if (btn) btn.disabled = false; }
}

document.addEventListener('click', e => {
  const c = e.target.closest('[data-control]');
  if (c) { withButton(c, () => control(c.dataset.control)); return; }
  const ua = e.target.closest('[data-user-action]');
  if (ua) withButton(ua, () => userAction(ua.dataset.userAction, Number(ua.dataset.id)));
});

$('#quickRecharge').addEventListener('submit', e => {
  e.preventDefault();
  const btn = e.submitter;
  withButton(btn, async () => {
    const res = await api('recharge', { amount: Number(e.target.amount.value) });
    toast(`Recharged ${res.name}: balance ₹${fmt(res.balance, 2)}`, 'ok');
    poll();
  });
});

$('#userRecharge').addEventListener('submit', e => {
  e.preventDefault();
  const f = e.target;
  withButton(e.submitter, async () => {
    const res = await api('recharge', { amount: Number(f.amount.value), user_id: Number(f.user_id.value) });
    toast(`Recharged ${res.name}: balance ₹${fmt(res.balance, 2)}`, 'ok');
    await loadUsers();
    poll();
  });
});

$('#addUser').addEventListener('submit', e => {
  e.preventDefault();
  const f = e.target;
  withButton(e.submitter, async () => {
    const name = f.elements.namedItem('name').value;
    await api('users', {
      action: 'add', name, roll_no: f.roll_no.value, room: f.room.value,
      rfid_uid: f.rfid_uid.value, balance: Number(f.balance.value || 0),
    });
    toast(`${name} registered`, 'ok');
    f.reset();
    f.balance.value = 100;
    await loadUsers();
  });
});

$('#settingsForm').addEventListener('submit', e => {
  e.preventDefault();
  const f = e.target;
  withButton(e.submitter, async () => {
    await api('settings', {
      device_name: f.device_name.value,
      tariff_per_kwh: Number(f.tariff_per_kwh.value),
      low_balance: Number(f.low_balance.value),
      volt_min: Number(f.volt_min.value),
      volt_max: Number(f.volt_max.value),
      theft_current: Number(f.theft_current.value),
      poll_ms: Number(f.poll_ms.value),
      auto_cutoff: f.auto_cutoff.checked,
    });
    toast('Settings saved', 'ok');
    await loadSettings();
    poll();
  });
});

$('#clearHistory').addEventListener('click', e => {
  if (!confirm('Clear the chart history? Balances and totals are kept.')) return;
  withButton(e.currentTarget, async () => {
    await api('clear', {});
    toast('Chart history cleared', 'ok');
    await loadHistory();
  });
});

$('#loginForm').addEventListener('submit', e => {
  e.preventDefault();
  withButton(e.submitter, async () => {
    await api('login', { password: e.target.password.value });
    e.target.reset();
    showLogin(false);
    route();
    poll();
  });
});

$('#logoutLink').addEventListener('click', async e => {
  e.preventDefault();
  await api('logout', {}).catch(() => {});
  showLogin(true);
});

async function start() {
  const me = await api('me').catch(() => null);
  if (me && me.login_required) {
    $('#logoutLink').hidden = false;
    if (!me.logged_in) showLogin(true);
  }
  window.addEventListener('hashchange', route);
  route();
  poll();
}
start();
