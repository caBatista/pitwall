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
  if (laps > 0) return `+${laps}L`;
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

// ---- preferences & units --------------------------------------------------
const KEY = 'pitwall.prefs.v1';
export const prefs = (() => {
  let p = {};
  try { p = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch { /* ignore */ }
  return Object.assign({ units: 'metric', standMode: 'class', classFilter: null, relRows: 4, reserve: 0.5, targetLaps: 10 }, p);
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
