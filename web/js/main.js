import { prefs, savePrefs, clock, fx } from './util.js';
import { standings } from './standings.js';
import { relative } from './relative.js';
import { trackmap } from './map.js';
import { fuel } from './fuel.js';
import { weather } from './weather.js';
import { laplog } from './laplog.js';
import { events } from './events.js';

const params = new URLSearchParams(location.search);
if (params.get('bg') === 'transparent') document.body.classList.add('transparent');

// ---- shared store -----------------------------------------------------------
const S = {
  st: null,            // latest state frame
  raw: '',             // ... as it came, to spot a repeated frame
  drivers: {},         // carIdx -> driver
  events: [], eventsVer: 0,   // Race Events, the whole session; S.eventsVer changes with the list
  classes: [], classMap: new Map(),
  meta: {},
  track: null,         // {key, status, ver, points}
  wxHist: [],
  connected: false,
  ws: null,
  send(obj) { if (S.ws && S.ws.readyState === 1) S.ws.send(JSON.stringify(obj)); },
  invalidate,
};

// ---- widgets -----------------------------------------------------------------
const ALL = { standings, relative, map: trackmap, fuel, weather, laplog, events };
const want = (params.get('w') || 'standings,relative,map,fuel,weather').split(',').map((s) => s.trim()).filter((k) => ALL[k]);
const board = document.getElementById('board');
const mk = (w) => {
  const el = document.createElement('section');
  el.className = 'card'; el.id = w.id;
  return el;
};
const widgets = [];
if (params.get('w')) {
  board.classList.add('solo');
  if (want.length > 1) board.style.gridTemplateRows = `repeat(${want.length}, minmax(0, auto))`;
  for (const k of want) { const el = mk(ALL[k]); board.appendChild(el); widgets.push([ALL[k], el]); }
} else {
  const bottom = document.createElement('div'); bottom.className = 'col-bottom';
  for (const k of ['standings', 'laplog', 'relative', 'map', 'events']) { const el = mk(ALL[k]); board.appendChild(el); widgets.push([ALL[k], el]); }
  for (const k of ['fuel', 'weather']) { const el = mk(ALL[k]); bottom.appendChild(el); widgets.push([ALL[k], el]); }
  board.appendChild(bottom);
}
for (const [w, el] of widgets) w.mount(el, S);

// out of the car the map's place takes turns with Fuel and Weather: arrows on hover (see app.css)
const SLOTS = ['map', 'fuel', 'weather'];
function showSlot(k) {
  if (k === 'map') delete document.body.dataset.slot; else document.body.dataset.slot = k;
}
if (!params.get('w')) {
  showSlot(SLOTS.includes(prefs.outSlot) ? prefs.outSlot : 'map');
  for (const k of SLOTS) {
    ALL[k].root ??= document.getElementById(ALL[k].id);
    document.getElementById(ALL[k].id).insertAdjacentHTML('beforeend',
      '<div class="slot-nav"><button data-step="-1" title="Previous">\u2039</button><button data-step="1" title="Next">\u203A</button></div>');
  }
  board.addEventListener('click', (e) => {
    const step = Number(e.target.closest('[data-step]')?.dataset.step);
    if (!step) return;
    const now = SLOTS.indexOf(document.body.dataset.slot ?? 'map');
    prefs.outSlot = SLOTS[(now + step + SLOTS.length) % SLOTS.length];
    savePrefs();
    showSlot(prefs.outSlot);
  });
}

// ---- render scheduling: one frame per change, nothing in between (see "render loop" below)
let dirty = false, queued = false;
function invalidate() {
  dirty = true;
  if (!queued) { queued = true; requestAnimationFrame(frame); }
}
addEventListener('click', invalidate);   // a mode changed: show it even with the sim paused
addEventListener('input', invalidate);
// ---- UI scale: ?zoom=1.2 for this screen, or +/- keys (saved), 0 resets ----------------
function setZoom(z) {
  z = Math.round(Math.min(2, Math.max(0.7, z)) * 100) / 100;
  document.documentElement.style.setProperty('--zoom', z);
  if (on.has(trackmap)) { trackmap.fitVer = -1; trackmap.size(); }
  invalidate();
  return z;
}
const on = new Set(widgets.map(([w]) => w));
setZoom(Number(params.get('zoom')) || prefs.zoom);
addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey || e.target.closest?.('input')) return;
  // desktop app (pywebview): the native window doesn't reload on its own
  if (e.key === 'F5' && window.pywebview?.api) { e.preventDefault(); location.reload(); return; }
  // desktop app (pywebview): F11 toggles full screen of the native window
  if (e.key === 'F11' && window.pywebview?.api) { e.preventDefault(); window.pywebview.api.fullscreen(); return; }
  const step = { '+': 0.05, '=': 0.05, '-': -0.05 }[e.key];
  if (step) prefs.zoom = setZoom(prefs.zoom + step);
  else if (e.key === '0') prefs.zoom = setZoom(1.1);
  else return;
  savePrefs();
});

// ---- desktop app: hidden full-screen toggle in the top-right corner (only inside pywebview)
addEventListener('pywebviewready', () => {
  document.body.classList.add('desktop');
  $('fs-btn').addEventListener('click', () => window.pywebview.api.fullscreen());
});

// ---- header ---------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const el = {
  name: $('trk-name'), sub: $('trk-sub'), series: $('series'), sof: $('sof'),
  clk: $('clock-main'), clkSub: $('clock-sub'),
  conn: $('conn'), ov: $('overlay'), ovT: $('ov-title'), ovP: $('ov-text'),
};

// iRacing only gives the series id: names come from web/series.json ({"228": "GT Sprint Series"})
let SERIES = {};
fetch('/series.json').then((r) => (r.ok ? r.json() : {})).then((j) => { SERIES = j || {}; }).catch(() => {});

function header() {
  const st = S.st, m = S.meta;
  if (m.track) {
    el.name.textContent = m.track;
    const bits = [m.config, m.lengthKm ? (prefs.units === 'imperial' ? (m.lengthKm * 0.621371).toFixed(2) + ' mi' : m.lengthKm.toFixed(2) + ' km') : '', m.turns ? m.turns + ' turns' : ''].filter(Boolean);
    el.sub.textContent = bits.join(' · ');
  }
  const series = SERIES[m.seriesId] || '';
  if (el.series.textContent !== series) el.series.textContent = series;
  el.series.hidden = !series;
  el.sof.textContent = m.sof || '–';
  if (!st || !st.session) return;
  const s = st.session;
  el.sof.parentElement.hidden = s.kind === 'test';   // no field to rate in a test session
  const rem = s.timeRemain;
  el.clk.textContent = clock(rem != null ? rem : st.t);
  const laps = s.lapsTotal && st.me.lap != null ? `Lap ${st.me.lap}/${s.lapsTotal}` : st.me.lap != null ? `Lap ${st.me.lap}` : '';
  el.clkSub.textContent = [s.name || s.type, rem != null ? 'Remaining' : 'Elapsed', laps].filter(Boolean).join(' · ');
}

function status() {
  const live = S.connected && S.st && S.st.connected !== false && S.st.session;
  el.conn.classList.toggle('on', !!live);
  el.conn.querySelector('em').textContent = live ? (S.source === 'simulator' ? 'simulator' : 'live') : S.wsUp ? 'waiting' : 'offline';
  el.ov.classList.toggle('show', !live && !params.get('quiet'));
  if (!S.wsUp) { el.ovT.textContent = 'Server offline'; el.ovP.textContent = 'Reconnecting to the Pitwall server…'; }
  else if (!live) { el.ovT.textContent = 'Waiting for iRacing'; el.ovP.textContent = 'Start iRacing and load into a session. The dashboard connects on its own.'; }
}

// ---- websocket -----------------------------------------------------------------

function connect() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  S.ws = ws;
  ws.onopen = () => { S.wsUp = true; status(); };
  ws.onclose = () => { S.wsUp = false; S.connected = false; S.raw = ''; status(); setTimeout(connect, 1000); };
  ws.onmessage = (e) => {
    // sim paused / nothing new: the 20 Hz stream repeats itself. Skip it, unless an effect has to keep
    // running or the slow widgets haven't shown this frame yet
    if (e.data === S.raw && !fx.live && settled) return;
    const m = JSON.parse(e.data);
    switch (m.type) {
      case 'hello': S.source = m.source; break;
      case 'drivers':
        S.drivers = m.drivers; S.meta = m.meta || {}; S.classes = m.classes || [];
        S.classMap = new Map(S.classes.map((c) => [c.id, c]));
        slow = 0; invalidate(); break;
      case 'track': S.track = m.points ? m : null; if (!m.points && S.st) S.track = null; invalidate(); break;
      case 'wx': S.wxHist = m.hist || []; invalidate(); break;
      case 'events':
        S.events = m.all || [...S.events, ...m.add].slice(-6000);
        S.eventsVer++; slow = 0; invalidate(); break;
      case 'state':
        S.connected = m.connected !== false;
        if (m.connected === false) { S.st = null; S.raw = ''; status(); return; }
        S.st = m; S.raw = e.data; invalidate();
        // what the board shows depends on the session (see body[data-kind] in app.css)
        if (m.session && document.body.dataset.kind !== m.session.kind) document.body.dataset.kind = m.session.kind;
        // race over: the board becomes the results (standings only)
        if (m.session) document.body.toggleAttribute('data-over', !!m.session.over);
        // out of the car: standings, Race Events and the map
        if (m.session) document.body.toggleAttribute('data-out', !m.session.inCar);
        // a finished race in the replay: the result and Race Events, nothing else
        if (m.session) document.body.toggleAttribute('data-static', !!m.session.static);
        break;
    }
  };
}
connect();

// ---- render loop (fast widgets on every change, slow ones twice a second) --------------
// Not a free-running requestAnimationFrame: at 165 Hz that keeps the browser's frame pipeline awake
// for nothing, data arrives at 20 Hz. The next frame is requested by what needs one (invalidate).
// only the mounted widgets: with ?w= the others never ran mount()
let slow = 0;
const fast = [standings, relative, trackmap].filter((w) => on.has(w));
const slowW = [fuel, weather, laplog, events].filter((w) => on.has(w));
// ?hz=10 (desktop: --render-hz 10) caps the panels below the 20 updates/s that arrive; default: no cap
const minGap = 1000 / (Number(params.get('hz')) || Infinity);
let drawn = 0, later = 0, settled = false;
function frame(now) {
  queued = false;
  if (!dirty || !S.st) return;
  if (now - drawn < minGap - 8) {   // 8: a frame that comes a bit early still counts
    later ||= setTimeout(() => { later = 0; invalidate(); }, minGap - (now - drawn));
    return;
  }
  drawn = now;
  dirty = false;
  fx.live = false;
  try {
    for (const w of fast) w.update(S);
    settled = now - slow > 400;
    if (settled) { slow = now; header(); status(); for (const w of slowW) w.update(S); }
  } catch (err) { console.error(err); }
}
setInterval(status, 1000);
