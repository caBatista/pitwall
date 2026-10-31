export const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

/** 1:42.754 or 42.754 */
export function lapTime(s) {
  if (s == null || !(s > 0)) return '–';
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return m > 0 ? `${m}:${r.toFixed(3).padStart(6, '0')}` : r.toFixed(3);
}

/** "+1.23", "+12.4", "+1:02.3", "+2L" */
export function gapText(sec, laps, signed = true) {
  if (laps > 0) return `${signed ? '+' : ''}${laps}L`;
  if (sec == null) return '–';
  const sg = signed ? '+' : '';
  if (sec >= 60) {
    const m = Math.floor(sec / 60);
    return `${sg}${m}:${(sec - m * 60).toFixed(1).padStart(4, '0')}`;
  }
  return sg + (sec < 10 ? sec.toFixed(2) : sec.toFixed(1));
}

export function clock(sec) {
  if (sec == null || !isFinite(sec)) return '--:--:--';
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function tod(sec) {
  if (sec == null) return '--:--';
  sec = Math.floor(sec) % 86400;
  return `${String(Math.floor(sec / 3600)).padStart(2, '0')}:${String(Math.floor((sec % 3600) / 60)).padStart(2, '0')}`;
}

// ---- flags & car makes ----------------------------------------------------
// iRacing gives the flair as an English country name ("Czechia", "England");
// build name -> ISO code from the browser's own region names.
const FLAG_CDN = 'https://cdn.jsdelivr.net/npm/flag-icons@7.2.3/flags/4x3/';
const ICON_CDN = 'https://cdn.jsdelivr.net/npm/simple-icons@13.0.0/icons/';
const norm = (s) => String(s).toLowerCase().replace(/&/g, 'and').replace(/[^a-z]/g, '');
// deprecated/aliased codes the browser still names ("DD" is also "Germany")
const OLD_CODES = new Set(['BU', 'CS', 'DD', 'FX', 'NT', 'QO', 'SU', 'TP', 'UK', 'YU', 'ZR', 'EU', 'EZ', 'UN']);
const ISO = (() => {
  // iRacing names that differ from the browser's region names ("Hong Kong" vs "Hong Kong SAR China")
  const map = { england: 'gb-eng', scotland: 'gb-sct', wales: 'gb-wls', northernireland: 'gb-nir', usa: 'us', russia: 'ru', turkey: 'tr',
    hongkong: 'hk', macau: 'mo', macao: 'mo', unitedstatesofamerica: 'us', greatbritain: 'gb', czechrepublic: 'cz',
    southkorea: 'kr', korea: 'kr', taiwan: 'tw', vietnam: 'vn', ivorycoast: 'ci', palestine: 'ps', bosnia: 'ba' };
  try {
    const dn = new Intl.DisplayNames(['en'], { type: 'region' });
    for (let a = 65; a <= 90; a++) {
      for (let b = 65; b <= 90; b++) {
        const code = String.fromCharCode(a, b);
        if (OLD_CODES.has(code)) continue;
        const name = dn.of(code);
        if (name && name !== code && !(norm(name) in map)) map[norm(name)] = code.toLowerCase();
      }
    }
  } catch { /* no Intl: no flags */ }
  return map;
})();

export function flagHtml(country) {
  const iso = ISO[norm(country || '')];
  return iso ? `<i class="flag-i" title="${esc(country)}" style="background-image:url(${FLAG_CDN}${iso}.svg)"></i>` : '<i class="flag-i none"></i>';
}

// Your own logos win: drop web/img/makes/<make>.png (porsche.png, bmw.png, ...).
// Each make is probed once; until it answers (or if missing) the simple-icons glyph is used.
// ?v= sidesteps 404s a browser remembered from before the file existed
const localSrc = (make) => `/img/makes/${make}.png?v=2`;
const LOCAL = new Map();   // make -> false | data: URL of the prepared logo

// Logo packs are made for white pages, at 18 px they need help:
//  - keep only the emblem: split the art into horizontal bands at empty rows and keep the
//    heaviest band, which drops a "PORSCHE" / "Mercedes-Benz" wordmark above or below it;
//  - trim the transparent margin so the emblem fills the box;
//  - a mostly-black logo (Mercedes star) is painted off-white to read on the dark card.
function prepare(im) {
  const W = im.naturalWidth, H = im.naturalHeight, k = Math.min(1, 512 / Math.max(W, H));
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(W * k)); c.height = Math.max(1, Math.round(H * k));
  const x = c.getContext('2d', { willReadFrequently: true });
  x.drawImage(im, 0, 0, c.width, c.height);
  const d = x.getImageData(0, 0, c.width, c.height), p = d.data, cw = c.width;
  const solid = (q) => p[q * 4 + 3] >= 24;
  const rows = new Array(c.height).fill(0);
  for (let q = 0; q < cw * c.height; q++) if (solid(q)) rows[(q / cw) | 0]++;
  // bands of rows with ink, split by a gap of >= 2% of the height
  const gap = Math.max(2, Math.round(c.height * 0.02)), bands = [];
  let start = -1, mass = 0, empty = 0;
  rows.forEach((r, y) => {
    if (r) { if (start < 0) { start = y; mass = 0; } mass += r; empty = 0; }
    else if (start >= 0 && ++empty >= gap) { bands.push([start, y - empty, mass]); start = -1; }
  });
  if (start >= 0) bands.push([start, c.height - 1 - empty, mass]);
  if (!bands.length) return im.src;
  let [by0, by1] = bands.reduce((a, b) => (b[2] > a[2] ? b : a));
  // a flat band is a wordmark cutting through a thin emblem (Nissan): keep the whole art
  const span = (y0b, y1b) => { let a = cw, b = -1; for (let y = y0b; y <= y1b; y++) for (let px = 0; px < cw; px++) if (solid(y * cw + px)) { if (px < a) a = px; if (px > b) b = px; } return b - a + 1; };
  if (bands.length > 1 && span(by0, by1) > 4 * (by1 - by0 + 1)) { by0 = bands[0][0]; by1 = bands[bands.length - 1][1]; }
  let x0 = cw, y0 = by1, x1 = -1, y1 = by0, val = 0, n = 0;
  for (let y = by0; y <= by1; y++) {
    for (let px = 0; px < cw; px++) {
      const q = y * cw + px;
      if (!solid(q)) continue;
      if (px < x0) x0 = px; if (px > x1) x1 = px; if (y < y0) y0 = y; if (y > y1) y1 = y;
      val += Math.max(p[q * 4], p[q * 4 + 1], p[q * 4 + 2]); n++;
    }
  }
  if (val / n < 70) {   // dark logo on a dark card (by brightest channel, so red stays red)
    for (let i = 0; i < p.length; i += 4) { p[i] = 244; p[i + 1] = 242; p[i + 2] = 236; }
    x.putImageData(d, 0, 0);
  }
  const w = x1 - x0 + 1, h = y1 - y0 + 1, S = 64, s = S / Math.max(w, h);
  const o = document.createElement('canvas'); o.width = S; o.height = S;
  o.getContext('2d').drawImage(c, x0, y0, w, h, (S - w * s) / 2, (S - h * s) / 2, w * s, h * s);
  return o.toDataURL('image/png');
}

function probe(make) {
  if (!make || LOCAL.has(make)) return;
  LOCAL.set(make, false);
  const im = new Image();
  im.onload = () => { try { LOCAL.set(make, prepare(im)); } catch { LOCAL.set(make, im.src); } };
  im.src = localSrc(make);
}

const NO_ICON = new Set(['corvette', 'lotus', 'ligier', 'dallara', 'oreca', 'radical', 'ginetta', '']);
export function makeHtml(make) {
  probe(make);
  if (LOCAL.get(make)) return `<img class="make-img" src="${LOCAL.get(make)}" alt="${esc(make)}">`;
  if (NO_ICON.has(make)) return `<i class="make-i txt">${esc((make || '').slice(0, 3).toUpperCase())}</i>`;
  return `<i class="make-i" title="${esc(make)}" style="--icon:url(${ICON_CDN}${make}.svg)"></i>`;
}

// ---- status tags (relative + standings) --------------------------------------
// small inline icons, coloured through CSS (currentColor)
const WATCH = '<svg viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6.8" r="4.2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M6 4.6v2.4l1.4 1M4.8 1.4h2.4" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>';
const MIC = '<svg viewBox="0 0 12 12" aria-hidden="true"><rect x="4.2" y="1" width="3.6" height="6.2" rx="1.8" fill="currentColor"/><path d="M2.6 5.6a3.4 3.4 0 0 0 6.8 0M6 9v2" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>';
// chequered flag, 6 x 4 squares, stretched to fill the whole chip
const CHECKER = '<svg viewBox="0 0 12 8" preserveAspectRatio="none" aria-hidden="true" shape-rendering="crispEdges"><rect width="12" height="8" fill="#fff"/><path d="M0 0h2v2h-2zM4 0h2v2h-2zM8 0h2v2h-2zM2 2h2v2h-2zM6 2h2v2h-2zM10 2h2v2h-2zM0 4h2v2h-2zM4 4h2v2h-2zM8 4h2v2h-2zM2 6h2v2h-2zM6 6h2v2h-2zM10 6h2v2h-2z" fill="#000"/></svg>';
// the most serious flag wins: DQ > black > meatball > slow down (furled) [> PIT > class fastest]
export const ST = {
  dq: '<span class="st dq">DQ</span>',
  black: '<span class="st black" title="Black flag"><i></i></span>',
  repair: '<span class="st repair" title="Meatball (repair)"><i></i></span>',
  warn: `<span class="st warn" title="Slow down"><i>${WATCH}</i></span>`,
  pit: '<span class="st pit">PIT</span>',
  fast: `<span class="st fast" title="Fastest lap in class">${WATCH}</span>`,
  fin: `<span class="st fin" title="Finished">${CHECKER}</span>`,
};
// relative: flags only; standings: flags, then PIT, then the class fastest lap
export const stHtml = (c, full = false) => ST[c.fl] || (full ? (c.pit ? ST.pit : c.cb ? ST.fast : '') : '');
// on the radio: strong green, pulsing (computed per frame: rows are re-rendered all the time)
export const talkHtml = (on) => {
  if (!on) return '';
  const k = (Math.sin(performance.now() / 160) + 1) / 2;
  return `<span class="st talk" title="On the radio" style="transform:scale(${(1 + 0.14 * k).toFixed(3)});box-shadow:0 0 ${(4 + 8 * k).toFixed(1)}px ${(1 + 2 * k).toFixed(1)}px rgba(0,214,90,${(0.35 + 0.4 * k).toFixed(2)})">${MIC}</span>`;
};
// iRating chip, with the estimated gain/loss of this race next to it (green up / red down,
// white dash for 0). Fixed-width parts so every chip is the same size: rating | arrow | gain,
// the gain right-aligned. withGain: the race shows the gain part on every row, even without one.
export function irHtml(ir, gain, withGain = gain != null) {
  if (!ir) return '';
  const v = (ir / 1000).toFixed(1) + 'k';   // always in k: 720 -> 0.7k
  const g = !withGain ? '' : gain ? `<em class="${gain > 0 ? 'up' : 'down'}"><i>${gain > 0 ? '▲' : '▼'}</i>${Math.abs(gain)}</em>` : '<em><i>–</i>0</em>';
  return `<b><span>${v}</span>${g}</b>`;
}
// every iRating chip as wide as the widest one of the session - no room kept for a 10k+ or a
// 3-digit gain nobody has. Measured once per set of values (key), set as --irv / --irg.
let irKey = '';
export function fitIr(root, key) {
  if (key === irKey) return;
  const st = document.body.style;
  st.removeProperty('--irv'); st.removeProperty('--irg');
  let v = 0, g = 0;
  for (const el of root.querySelectorAll('.irb b span')) v = Math.max(v, el.offsetWidth);
  for (const el of root.querySelectorAll('.irb em')) g = Math.max(g, el.offsetWidth);
  if (!v) return;   // nothing laid out (hidden panel): measure again next frame
  irKey = key;
  st.setProperty('--irv', v + 'px');
  if (g) st.setProperty('--irg', g + 'px');
}
export const irKeyOf = (S, cars) => Object.values(S.drivers).map((d) => d.ir).join() + '|' + cars.map((c) => Math.abs(c.irg || 0)).reduce((m, x) => Math.max(m, String(x).length), 0) + '|' + cars.some((c) => c.irg != null);

export const OUT = '<span class="tag out">OUT</span>';

// last pit stop, RaceLab style: amber "L12" (lap of the stop) + time on pit road, outlined.
// The time blinks while the car is still in the pits (rows re-render every frame: computed, not CSS).
// PIT_ALL: true shows it in every session (testing); races only otherwise.
// invalidated lap (or one with my incidents): an asterisk after the time
export const INV = '<sup class="inv">*</sup>';

export const PIT_ALL = false;
export function pitHtml(c, kind) {
  if (!c || c.pl == null || (!PIT_ALL && kind !== 'race')) return '';
  const s = Math.max(0, Math.floor(c.pd || 0));
  // in the pits: only the time blinks, filled <-> outlined, once a second
  const fill = c.pip && Math.floor(performance.now() / 1000) % 2 === 0;
  const time = s >= 100 * 60 ? '∞' : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  return `<span class="pitl"><b>L${c.pl}</b><i${fill ? ' class="on"' : ''}>${time}</i></span>`;
}

// tyre in the RaceLab way: a little Michelin-style tyre, white sidewall marks dry, blue wet
export function tyreHtml(tc) {
  if (!tc) return '';
  return `<svg class="tyre ${tc}" viewBox="0 0 20 20" aria-label="${tc === 'wet' ? 'Wet' : 'Dry'} tyres"><circle cx="10" cy="10" r="9" fill="#0b0b0c" stroke="#3a3a3e" stroke-width="1.5"/><circle cx="10" cy="10" r="6" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="6.4 3"/><circle cx="10" cy="10" r="2.6" fill="#2a2a2d"/></svg>`;
}

// helmet for the class driver count
export const HELMET = '<svg class="helmet" viewBox="0 0 14 12" aria-hidden="true"><path d="M1 8.5C1 4.4 3.9 1.2 7.6 1.2c3 0 5.4 2.1 5.4 5.2v2.1H8.2l-.9 1.7H2.4C1.6 10.2 1 9.5 1 8.5Z" fill="currentColor"/><path d="M7.4 4.2h5.3v2.4H7.4z" fill="#111112"/></svg>';

// ---- change effects (rows are re-rendered every frame, so the fade is computed, not a CSS animation)
const FX = new Map();   // key -> {v: last value, t: when it changed}
const FX_FLAG = 1400;
// new flag on a car: the chip pops in (big, then settles)
export function flagFx(key, fl) {
  const now = performance.now(), f = FX.get('f' + key);
  if (!f || fl !== f.v) FX.set('f' + key, { v: fl, t: fl && f ? now : 0 });
  const g = FX.get('f' + key), k = 1 - (now - g.t) / FX_FLAG;
  return g.t && k > 0 ? `transform:scale(${(1 + 0.6 * k * k).toFixed(3)})` : '';
}

// ---- preferences & units --------------------------------------------------
const KEY = 'pitwall.prefs.v1';
export const prefs = (() => {
  let p = {};
  try { p = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch { /* ignore */ }
  return Object.assign({ units: 'metric', standMode: 'class', classFilter: null, relRows: 3, zoom: 1.1, reserve: 0.5, targetLaps: 10 }, p);
})();
export function savePrefs() {
  try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch { /* ignore */ }
}

const imp = () => prefs.units === 'imperial';
export const fmt = {
  temp: (c) => (c == null ? '–' : imp() ? (c * 9) / 5 + 32 : c),
  tempU: () => (imp() ? '°F' : '°C'),
  vol: (l) => (l == null ? null : imp() ? l * 0.264172 : l),
  volU: () => (imp() ? 'gal' : 'L'),
  speed: (ms) => (ms == null ? null : imp() ? ms * 2.23694 : ms * 3.6),
  speedU: () => (imp() ? 'mph' : 'km/h'),
  press: (pa) => (pa == null ? null : imp() ? pa * 0.0002953 : pa / 100),
  pressU: () => (imp() ? 'inHg' : 'hPa'),
};
