/**
 * Which widgets each session shows, where and how big: a grid, as iOS widgets. Pure on purpose:
 * tests/js runs it under node, the board and the settings pop-up share it.
 *
 * The screen's shape comes first: a landscape board is 24 x 12, a portrait one 12 x 24, each with its own
 * layouts. prefs.layout = { session: [...], 'session:portrait': [...] }, items { id, x, y, w, h } in cells.
 * A landscape session with nothing saved keeps the board's own CSS (app.css), so nobody who never edits
 * sees anything change; portrait has no such CSS and starts from DEFAULTS.
 */
export const shapeOf = (w, h) => (h > w ? 'portrait' : 'landscape');
export const gridOf = (shape) => (shape === 'portrait' ? { cols: 12, rows: 24 } : { cols: 24, rows: 12 });
const keyOf = (session, shape) => (shape === 'portrait' ? `${session}:portrait` : session);
/** The smallest size, in this grid's cells. */
const minOf = (id, shape) => (shape === 'portrait'
  ? { w: Math.ceil(WIDGETS[id].mw / 2), h: WIDGETS[id].mh + 1 } : { w: WIDGETS[id].mw, h: WIDGETS[id].mh });

// mw/mh: the smallest it can be; w/h: the size it comes with
export const WIDGETS = {
  standings: { name: 'Standings', mw: 8, mh: 3, w: 14, h: 12 },
  relative: { name: 'Relative', mw: 6, mh: 3, w: 10, h: 4 },
  map: { name: 'Track map', mw: 4, mh: 3, w: 10, h: 4 },
  fuel: { name: 'Fuel', mw: 4, mh: 3, w: 5, h: 4 },
  weather: { name: 'Weather', mw: 4, mh: 3, w: 5, h: 4 },
  laplog: { name: 'Lap times', mw: 8, mh: 3, w: 14, h: 12 },
  events: { name: 'Race events', mw: 6, mh: 3, w: 10, h: 4 },
};
export const SESSIONS = [['test', 'Test'], ['practice', 'Practice'], ['qualify', 'Qualify'], ['race', 'Race'], ['over', 'Race over'], ['out', 'In garage']];

const box = (id, x, y, w, h) => ({ id, x, y, w, h });
const RIGHT = [box('fuel', 14, 8, 5, 4), box('weather', 19, 8, 5, 4)];
const FULL = [box('standings', 0, 0, 14, 12), box('relative', 14, 0, 10, 4), box('map', 14, 4, 10, 4), ...RIGHT];
const NO_REL = [box('standings', 0, 0, 14, 12), box('map', 14, 0, 10, 8), ...RIGHT];
export const DEFAULTS = {
  race: FULL, practice: FULL, qualify: NO_REL,
  test: [box('laplog', 0, 0, 14, 12), box('map', 14, 0, 10, 8), ...RIGHT],
  over: [box('standings', 0, 0, 12, 12), box('map', 12, 0, 12, 12)],
  out: [box('standings', 0, 0, 14, 12), box('events', 14, 0, 10, 8), box('map', 14, 8, 10, 4)],
};

/** Out of the car comes first: in any session, and also when the race ended, that is the screen in use. */
// a screen standing up: the list across the top, the rest below it
const P_BOTTOM = [box('fuel', 6, 18, 3, 6), box('weather', 9, 18, 3, 6)];
export const DEFAULTS_PORTRAIT = {
  race: [box('standings', 0, 0, 12, 13), box('relative', 0, 13, 12, 5), box('map', 0, 18, 6, 6), ...P_BOTTOM],
  qualify: [box('standings', 0, 0, 12, 12), box('map', 0, 12, 12, 6), box('fuel', 0, 18, 6, 6), box('weather', 6, 18, 6, 6)],
  test: [box('laplog', 0, 0, 12, 12), box('map', 0, 12, 12, 6), box('fuel', 0, 18, 6, 6), box('weather', 6, 18, 6, 6)],
  over: [box('standings', 0, 0, 12, 15), box('map', 0, 15, 12, 9)],
  out: [box('standings', 0, 0, 12, 12), box('events', 0, 12, 12, 6), box('map', 0, 18, 12, 6)],
};
DEFAULTS_PORTRAIT.practice = DEFAULTS_PORTRAIT.race;

export const sessionKey = (kind, over, out) => (out ? 'out' : over ? 'over' : kind);

const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
const inside = (i, g) => i.x >= 0 && i.y >= 0 && i.x + i.w <= g.cols && i.y + i.h <= g.rows;

/** What was saved, if it still makes sense: known widgets, once each, inside the grid, not overlapping. */
export function savedLayout(saved, session, shape) {
  const list = saved?.[keyOf(session, shape)];
  if (!Array.isArray(list)) return null;
  const g = gridOf(shape), out = [];
  for (const i of list) {
    const m = WIDGETS[i?.id] && minOf(i.id, shape);
    const ok = m && [i.x, i.y, i.w, i.h].every(Number.isInteger) && i.w >= m.w && i.h >= m.h;
    if (ok && inside(i, g) && !out.some((o) => o.id === i.id || hit(o, i))) out.push(box(i.id, i.x, i.y, i.w, i.h));
  }
  return out;
}

const defaultOf = (session, shape) => (shape === 'portrait' ? DEFAULTS_PORTRAIT[session] ?? DEFAULTS_PORTRAIT.race : DEFAULTS[session] ?? FULL)
  .map((i) => ({ ...i }));
export const layoutFor = (saved, session, shape) => savedLayout(saved, session, shape) ?? defaultOf(session, shape);
export const saveLayout = (saved, session, shape, items) => { saved[keyOf(session, shape)] = items; };
export const clearLayout = (saved, session, shape) => { delete saved?.[keyOf(session, shape)]; };
/** What the board draws by itself: null leaves it to app.css. */
export const boardLayout = (saved, session, shape) => (shape === 'portrait' ? layoutFor(saved, session, shape) : savedLayout(saved, session, shape));

/** The nearest place where it fits, by the distance from where it is now. */
function nearest(item, taken, g) {
  let best = null, far = Infinity;
  for (let y = 0; y + item.h <= g.rows; y++) {
    for (let x = 0; x + item.w <= g.cols; x++) {
      const c = { ...item, x, y }, d = Math.abs(x - item.x) + Math.abs(y - item.y);
      if (d < far && !taken.some((t) => hit(c, t))) { best = c; far = d; }
    }
  }
  return best;
}

/** placed goes where it is; whoever was there moves to the nearest free place. null: there is no room. */
function settle(items, placed, g) {
  const others = items.filter((i) => i.id !== placed.id);
  const taken = [placed, ...others.filter((i) => !hit(i, placed))];
  const pushed = others.filter((i) => hit(i, placed));
  for (const i of pushed) {
    const p = nearest(i, taken, g);
    if (!p) return null;
    taken.push(p);
  }
  return items.map((i) => ({ ...taken.find((t) => t.id === i.id) }));
}

export function moveItem(items, id, x, y, shape) {
  const i = items.find((o) => o.id === id), g = gridOf(shape);
  return settle(items, { ...i, x: Math.max(0, Math.min(g.cols - i.w, x)), y: Math.max(0, Math.min(g.rows - i.h, y)) }, g);
}

export function resizeItem(items, id, w, h, shape) {
  const i = items.find((o) => o.id === id), m = minOf(id, shape), g = gridOf(shape);
  return settle(items, { ...i, w: Math.max(m.w, Math.min(g.cols - i.x, w)), h: Math.max(m.h, Math.min(g.rows - i.y, h)) }, g);
}

/** In the first place it fits: at its usual size, otherwise at the smallest. null: no room left. */
export function addItem(items, id, shape) {
  const m = minOf(id, shape), g = gridOf(shape);
  const usual = shape === 'portrait' ? box(id, 0, 0, Math.min(g.cols, WIDGETS[id].h * 2), Math.ceil(WIDGETS[id].w / 2)) : box(id, 0, 0, WIDGETS[id].w, WIDGETS[id].h);
  const p = nearest({ ...usual, h: Math.max(usual.h, m.h), w: Math.max(usual.w, m.w) }, items, g) ?? nearest(box(id, 0, 0, m.w, m.h), items, g);
  return p ? [...items, p] : null;
}

export const gridArea = (i) => `${i.y + 1} / ${i.x + 1} / span ${i.h} / span ${i.w}`;
