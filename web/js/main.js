import { prefs, savePrefs, clock, fmt, esc } from './util.js';
import { standings } from './standings.js';
import { relative } from './relative.js';
import { trackmap } from './map.js';
import { fuel } from './fuel.js';
import { weather } from './weather.js';

const params = new URLSearchParams(location.search);
if (params.get('bg') === 'transparent') document.body.classList.add('transparent');

// ---- shared store -----------------------------------------------------------
const S = {
  st: null,            // latest state frame
  drivers: {},         // carIdx -> driver
  classes: [], classMap: new Map(),
  meta: {},
  track: null,         // {key, status, ver, points}
  wxHist: [],
  sel: null,           // selected carIdx (click a row)
  connected: false,
  ws: null,
  send(obj) { if (S.ws && S.ws.readyState === 1) S.ws.send(JSON.stringify(obj)); },
};

// ---- widgets -----------------------------------------------------------------
const ALL = { standings, relative, map: trackmap, fuel, weather };
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
  for (const k of ['standings', 'relative', 'map']) { const el = mk(ALL[k]); board.appendChild(el); widgets.push([ALL[k], el]); }
  for (const k of ['fuel', 'weather']) { const el = mk(ALL[k]); bottom.appendChild(el); widgets.push([ALL[k], el]); }
  board.appendChild(bottom);
}
for (const [w, el] of widgets) w.mount(el, S);

let dirty = false;
// ---- UI scale: ?zoom=1.2 for this screen, or +/- keys (saved), 0 resets ----------------
function setZoom(z) {
  z = Math.round(Math.min(2, Math.max(0.7, z)) * 100) / 100;
  document.documentElement.style.setProperty('--zoom', z);
  if (on.has(trackmap)) { trackmap.fitVer = -1; trackmap.size(); }
  dirty = true;
  return z;
}
const on = new Set(widgets.map(([w]) => w));
setZoom(Number(params.get('zoom')) || prefs.zoom);
addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey || e.target.closest?.('input')) return;
  const step = { '+': 0.05, '=': 0.05, '-': -0.05 }[e.key];
  if (step) prefs.zoom = setZoom(prefs.zoom + step);
  else if (e.key === '0') prefs.zoom = setZoom(1.1);
  else return;
  savePrefs();
});

// ---- header ---------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const el = {
  name: $('trk-name'), sub: $('trk-sub'), type: $('sess-type'), flag: $('flag'),
  clk: $('clock-main'), clkSub: $('clock-sub'), mini: $('mini'), units: $('units-btn'),
  conn: $('conn'), ov: $('overlay'), ovT: $('ov-title'), ovP: $('ov-text'),
};
el.units.textContent = prefs.units.toUpperCase();
el.units.addEventListener('click', () => {
  prefs.units = prefs.units === 'metric' ? 'imperial' : 'metric';
  el.units.textContent = prefs.units.toUpperCase(); savePrefs(); dirty = true; slow = 0;
});

const FLAGS = { green: 'Green', yellow: 'Yellow', caution: 'Caution', red: 'Red', white: 'White', blue: 'Blue', black: 'Black', checkered: 'Finish' };
let hdrKey = '';
function header() {
  const st = S.st, m = S.meta;
  if (m.track) {
    el.name.textContent = m.track;
    const bits = [m.config, m.lengthKm ? (prefs.units === 'imperial' ? (m.lengthKm * 0.621371).toFixed(2) + ' mi' : m.lengthKm.toFixed(2) + ' km') : '', m.turns ? m.turns + ' turns' : ''].filter(Boolean);
    el.sub.textContent = bits.join(' · ');
  }
  if (!st || !st.session) return;
  const s = st.session;
  el.type.textContent = s.name || s.type;
  const f = (s.flag || 'none').toLowerCase();
  const fk = f === 'caution' ? 'yellow' : f;
  el.flag.className = 'flag ' + (FLAGS[f] ? fk : 'none');
  el.flag.textContent = FLAGS[f] || '';
  const rem = s.timeRemain;
  el.clk.textContent = clock(rem != null ? rem : st.t);
  const laps = s.lapsTotal && st.me.lap != null ? `Lap ${st.me.lap}/${s.lapsTotal}` : st.me.lap != null ? `Lap ${st.me.lap}` : '';
  el.clkSub.textContent = [rem != null ? 'Remaining' : 'Elapsed', laps].filter(Boolean).join(' · ');
  const sp = fmt.speed(st.me.speed), gear = st.me.gear;
  const mini = `<span class="chip">Speed <b>${sp == null ? '–' : sp.toFixed(0)}</b>${fmt.speedU()}</span>` +
    `<span class="chip">Gear <b>${gear == null ? '–' : gear < 0 ? 'R' : gear === 0 ? 'N' : gear}</b></span>`;
  if (mini !== hdrKey) { el.mini.innerHTML = mini; hdrKey = mini; }
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
  ws.onclose = () => { S.wsUp = false; S.connected = false; status(); setTimeout(connect, 1000); };
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    switch (m.type) {
      case 'hello': S.source = m.source; break;
      case 'drivers':
        S.drivers = m.drivers; S.meta = m.meta || {}; S.classes = m.classes || [];
        S.classMap = new Map(S.classes.map((c) => [c.id, c]));
        hdrKey = ''; slow = 0; dirty = true; break;
      case 'track': S.track = m.points ? m : null; if (!m.points && S.st) S.track = null; break;
      case 'wx': S.wxHist = m.hist || []; break;
      case 'state':
        S.connected = m.connected !== false;
        if (m.connected === false) { S.st = null; status(); return; }
        S.st = m; dirty = true; break;
    }
  };
}
connect();

// ---- render loop (fast widgets every frame, slow ones twice a second) --------------
// only the mounted widgets: with ?w= the others never ran mount()
let slow = 0;
const fast = [standings, relative, trackmap].filter((w) => on.has(w));
const slowW = [fuel, weather].filter((w) => on.has(w));
function frame(now) {
  if (dirty && S.st) {
    dirty = false;
    try {
      for (const w of fast) w.update(S);
      if (now - slow > 400) { slow = now; header(); status(); for (const w of slowW) w.update(S); }
    } catch (err) { console.error(err); }
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
setInterval(status, 1000);
