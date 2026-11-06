import { prefs, savePrefs, clock, fx } from './util.js';
import { standings } from './standings.js';
import { relative } from './relative.js';
import { trackmap } from './map.js';
import { fuel } from './fuel.js';
import { weather } from './weather.js';
import { laplog } from './laplog.js';
import { events } from './events.js';
import { WIDGETS, boardLayout, gridArea, gridOf, sessionKey, shapeOf, fixedAnchor, rowTracks } from './layout.js';
import { HEADER, hiddenIn, optOf, orderOf, viewSession } from './columns.js';
import { camera } from './camera.js';

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
const ALL = { standings, relative, map: trackmap, fuel, weather, laplog, events, camera };
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
  for (const k of ['standings', 'laplog', 'relative', 'map', 'events', 'camera']) { const el = mk(ALL[k]); board.appendChild(el); widgets.push([ALL[k], el]); }
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

// ---- the user's layout for this session (Settings > Layout); nothing saved: the board's own CSS.
// A finished race in the replay keeps its own screen. Inline styles, so nothing in app.css has to
// know: leaving it just clears them.
const narrow = matchMedia('(max-width: 799px), (max-width: 1180px) and (orientation: landscape)');   // a phone, a small window: one column
const portrait = matchMedia('(orientation: portrait)');
let layoutKey = '';
function applyLayout() {
  const s = S.st?.session;
  if (!s || params.get('w')) return;
  const session = sessionKey(s.kind, s.over, !s.inCar);
  try { if (localStorage.getItem('pitwall.session') !== session) localStorage.setItem('pitwall.session', session); } catch { /* ignore */ }
  const b = document.body.dataset;
  const shape = shapeOf(innerWidth, innerHeight), g = gridOf(shape);
  const list = 'static' in b || narrow.matches ? null : boardLayout(prefs.layout, session, shape);
  const key = shape + JSON.stringify(list);
  if (key === layoutKey) return;
  layoutKey = key;
  board.classList.toggle('lay', !!list);
  const cards = Object.keys(WIDGETS).map((k) => document.getElementById(ALL[k].id));
  const bottom = board.querySelector('.col-bottom');
  board.style.gridTemplateColumns = list ? `repeat(${g.cols}, minmax(0, 1fr))` : '';
  board.style.gridTemplateRows = list ? rowTracks(list, g) : '';
  board.style.gridTemplateAreas = list ? 'none' : '';
  bottom.style.display = list ? 'contents' : '';
  for (const el of cards) {
    const i = list?.find((o) => ALL[o.id].id === el.id);
    el.style.gridArea = i ? gridArea(i) : '';
    el.style.minHeight = list ? '0' : '';
    el.style.maxHeight = list ? 'none' : '';
    el.style.display = !list ? '' : i ? 'flex' : 'none';
    el.style.visibility = list ? 'visible' : '';   // the map's place taking turns (data-slot) is the default screen's
    const end = i && WIDGETS[i.id].px && fixedAnchor(i, g);   // a fixed size inside its cells: see app.css
    el.style.justifySelf = end ? (end.right ? 'end' : 'start') : '';
    el.style.alignSelf = end ? (end.bottom ? 'end' : 'start') : '';
  }
}
for (const q of [narrow, portrait]) q.addEventListener('change', applyLayout);
addEventListener('prefs', applyLayout);

// ---- the app's header (Settings > Header): order through flex, so the elements stay where main.js finds them
const HEAD_EL = () => ({ brand: document.querySelector('.brand'), series: el.series, track: document.querySelector('.trk'), clock: document.querySelector('.clock'), gap: document.querySelector('.spacer'), sof: el.sof.parentElement, conn: el.conn });
let headKey = '';
function applyHeader() {
  const s = S.st?.session;
  if (!s) return;
  const session = viewSession(s.kind, s.over, !s.inCar), cfg = prefs.header;
  const key = session + JSON.stringify(cfg);
  if (key === headKey) return;
  headKey = key;
  const els = HEAD_EL();
  orderOf(cfg, HEADER).forEach((k, n) => {
    els[k].style.order = n * 2 + 1;
    els[k].classList.toggle('off', hiddenIn(cfg, HEADER, k, session));
    if (k === 'clock') document.getElementById('mock-seg').style.order = n * 2 + 2;
  });
  document.getElementById('set-btn').style.order = 99;
  els.brand.querySelector('b').hidden = !optOf(cfg, HEADER, 'brand', 'text');
  el.sub.hidden = !optOf(cfg, HEADER, 'track', 'sub');
  el.clkSub.hidden = !optOf(cfg, HEADER, 'clock', 'sub');
}
addEventListener('prefs', applyHeader);

// ---- render scheduling: one frame per change, nothing in between (see "render loop" below)
let dirty = false, queued = false;
function invalidate() {
  dirty = true;
  if (!queued) { queued = true; requestAnimationFrame(frame); }
}
addEventListener('click', invalidate);   // a mode changed: show it even with the sim paused
addEventListener('input', invalidate);
addEventListener('prefs', invalidate);   // changed in the settings pop-up
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
  if (e.key === 's' || e.key === 'S') { openSettings(); return; }
  const step = { '+': 0.05, '=': 0.05, '-': -0.05 }[e.key];
  if (step) prefs.zoom = setZoom(prefs.zoom + step);
  else if (e.key === '0') prefs.zoom = setZoom(1.1);
  else return;
  savePrefs();
});

// a window of its own: in the app a native pop-up, in a browser (tablet, --lan) a browser one
function openSettings() {
  if (window.pywebview?.api) window.pywebview.api.settings();
  else window.open('/settings.html', 'pitwall-settings', 'width=980,height=680')?.focus();
}
document.getElementById('set-btn').addEventListener('click', openSettings);

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
  if (S.source === 'simulator') mockSession();
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
  const rem = s.timeRemain;
  el.clk.textContent = clock(rem != null ? rem : st.t);
  const lap = (st.user ?? st.me).lap;   // the user's, whoever is on camera
  const laps = s.lapsTotal && lap != null ? `Lap ${lap}/${s.lapsTotal}` : lap != null ? `Lap ${lap}` : '';
  el.clkSub.textContent = [s.name || s.type, rem != null ? 'Remaining' : 'Elapsed', laps].filter(Boolean).join(' · ');
}

// simulator only: which session it is pretending, and asking for another one
const mockSeg = document.getElementById('mock-seg');
mockSeg.addEventListener('click', (e) => {
  const b = e.target.closest('[data-mock]');
  if (b) S.send({ cmd: 'mock_session', kind: b.dataset.mock });
});
function mockSession() {
  const s = S.st?.session;
  const now = s && sessionKey(s.kind, s.over, !s.inCar);
  if (now === mockSeg.dataset.now) return;
  mockSeg.dataset.now = now;
  for (const b of mockSeg.children) b.classList.toggle('on', b.dataset.mock === now);
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
      case 'hello': S.source = m.source; mockSeg.hidden = m.source !== 'simulator'; break;
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
        applyLayout();
        applyHeader();
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
const fast = [camera, standings, relative, trackmap].filter((w) => on.has(w));
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
