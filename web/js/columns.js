/**
 * What the user can arrange: the Standings columns, its class header and footer, the app's header.
 * Pure on purpose: tests/js runs it under node, the pop-up and the board share it.
 *
 * Every list has the same shape: { order: keys, hide: { key: sessions where it is hidden }, opt: { key: { option: value } } }.
 * A table says what each entry is: label, fixed (can't be turned off), opts (the options behind its arrow:
 * { k, label, type: 'seg' | 'select' | 'bool' | 'multi', values: [[value, name]], d: default }).
 * child: belongs to that entry, listed right under it and moving with it.
 * In the Standings table also w: width (name takes what is left), inline: lives inside the driver's cell,
 * lead: goes under the class name when at the start of the row, a: alignment of the title.
 */
export const viewSession = (kind, over, out) => (over ? 'over' : out ? 'out' : kind);

const DEC = (d) => ({ k: 'dec', label: 'Decimals', type: 'seg', values: [[0, '0'], [1, '1'], [2, '2'], [3, '3']], d });
const AUTO_DEC = { k: 'dec', label: 'Decimals', type: 'seg', values: [['auto', 'Auto'], [0, '0'], [1, '1'], [2, '2'], [3, '3']], d: 'auto' };

// how a name can be written, shown with the user's own example
const NAME_FORMATS = [['full', 'Caio Araujo Batista'], ['first-last', 'Caio Batista'], ['FIRST-LAST', 'CAIO BATISTA'], ['f-last', 'C. Batista'],
  ['first-l', 'Caio B.'], ['f-LAST', 'C. BATISTA'], ['FIRST-l', 'CAIO B.'], ['first-m-last', 'Caio A Batista']];

/** A driver's name in one of the formats above. iRacing adds a number to tell two drivers with the same name apart. */
export function driverName(name, format, keepNumber = false) {
  const clean = keepNumber ? String(name ?? '') : String(name ?? '').replace(/\d+$/, '');
  const parts = clean.trim().split(/\s+/);
  if (format === 'full' || parts.length < 2) return format.toUpperCase() === format && format !== 'full' ? clean.trim().toUpperCase() : clean.trim();
  const first = parts[0], last = parts[parts.length - 1], mid = parts.slice(1, -1);
  const initial = (w) => w.charAt(0).toUpperCase();
  switch (format) {
    case 'first-last': return `${first} ${last}`;
    case 'FIRST-LAST': return `${first} ${last}`.toUpperCase();
    case 'f-last': return `${initial(first)}. ${last}`;
    case 'first-l': return `${first} ${initial(last)}.`;
    case 'f-LAST': return `${initial(first)}. ${last.toUpperCase()}`;
    case 'FIRST-l': return `${first.toUpperCase()} ${initial(last)}.`;
    case 'first-m-last': return [first, ...mid.map(initial), last].join(' ');
    default: return clean.trim();
  }
}

export const STAND = {
  pos: { label: 'Position', w: '34px', title: 'Pos', a: 'c', lead: true },
  num: { label: 'Car number', w: '46px', title: 'No', a: 'c', lead: true },
  pg: { label: 'Positions gained', w: '22px', title: '', a: 'c', lead: true },
  make: { label: 'Car brand', w: '40px', title: '', a: 'c', lead: true },
  flag: { label: 'Country', w: '22px', title: '', a: 'c', lead: true },
  name: { label: 'Driver name', w: 'minmax(110px, 1fr)', title: 'Driver', a: '', lead: true, fixed: true, opts: [
    { k: 'format', label: 'Write the name as', type: 'select', values: NAME_FORMATS, d: 'full' },
    { k: 'number', label: 'Keep the number iRacing adds after the name', type: 'bool', d: false },
  ] },
  out: { label: 'OUT tag', inline: true, child: 'name' },
  pit: { label: 'Last pit tag', inline: true, child: 'name', note: 'Races only' },
  sr: { label: 'Safety rating', w: '52px', title: 'SR', a: 'c', lead: true },
  ir: { label: 'iRating', w: '84px', title: 'iR', a: 'c', lead: true, opts: [
    { k: 'gain', label: 'Show the iRating gain', type: 'bool', d: true },
    { k: 'fmt', label: 'Format', type: 'seg', values: [['k', '2.1k'], ['full', '2100']], d: 'k' },
  ] },
  tyre: { label: 'Tyre', w: '26px', title: 'Tyre', a: 'c', opts: [
    { k: 'show', label: 'Show as', type: 'seg', values: [['icon', 'Icon'], ['text', 'DRY / WET']], d: 'icon' },
  ] },
  int: { label: 'Interval', w: '58px', title: 'Int', a: 'r', opts: [AUTO_DEC] },
  gap: { label: 'Gap', w: '58px', title: 'Gap', a: 'r', opts: [AUTO_DEC] },
  last: { label: 'Last lap', w: '70px', title: 'Last', a: 'r', opts: [DEC(3)] },
  best: { label: 'Fastest lap', w: '70px', title: 'Fastest', a: 'r', opts: [DEC(3)] },
  delta: { label: 'Lap delta', w: '38px', title: 'Delta', a: 'c', opts: [
    { k: 'laps', label: 'Laps compared', type: 'seg', values: [[1, '1'], [2, '2'], [3, '3'], [4, '4'], [5, '5']], d: 3 },
    { k: 'dec', label: 'Decimals', type: 'seg', values: [[1, '1'], [2, '2'], [3, '3']], d: 1 },
  ] },
  status: { label: 'Flag', w: '54px', title: 'Flag', a: 'c', opts: [
    { k: 'off', label: 'Leave out', type: 'multi', values: [['fast', 'Fastest lap'], ['pen', 'Penalties'], ['pit', 'Pit'], ['fin', 'Checkered']], d: [] },
  ] },
};
// race over is the results, nothing live: what the board always showed there
const OVER_HIDE = ['out', 'pit', 'tyre', 'int', 'gap', 'last', 'delta'];
const OVER_W = { best: '80px' };
export const standDefault = () => ({ v: 2, order: Object.keys(STAND), hide: Object.fromEntries(OVER_HIDE.map((k) => [k, ['over']])), opt: {} });

/** The class header. The class name is always there. */
export const CLASS_HEAD = {
  drivers: { label: 'Drivers', opts: [{ k: 'show', label: 'Show as', type: 'seg', values: [['icon', 'Helmet'], ['text', 'Text']], d: 'icon' }] },
  sof: { label: 'SOF', opts: [{ k: 'fmt', label: 'Format', type: 'seg', values: [['full', '2100'], ['k', '2.1k']], d: 'full' }] },
  laps: { label: "Leader's laps" },
};
export const classDefault = () => ({ order: Object.keys(CLASS_HEAD), hide: { laps: ['test', 'practice', 'qualify', 'race', 'over', 'out'] }, opt: {} });

/** The footer of the Standings. */
const NO_STAKE = ['test', 'practice'];
export const FOOT = {
  pos: { label: 'Position', opts: [{ k: 'overall', label: 'Show the overall position', type: 'bool', d: true }] },
  lap: { label: 'Lap', opts: [{ k: 'total', label: 'Show the race length', type: 'bool', d: true }] },
  last: { label: 'Last lap', opts: [DEC(3)] },
  best: { label: 'Best lap', opts: [DEC(3)] },
  ir: { label: 'iRating change' },
  inc: { label: 'Incidents', opts: [{ k: 'limits', label: 'Show the limits', type: 'bool', d: true }] },
  cur: { label: 'Current lap', opts: [DEC(1)] },
  delta: { label: 'Delta to best' },
  fuel: { label: 'Fuel level' },
  track: { label: 'Track temp' },
  air: { label: 'Air temp' },
};
const FOOT_EXTRA = ['cur', 'delta', 'fuel', 'track', 'air'];
const ALL_SESSIONS = ['test', 'practice', 'qualify', 'race', 'over', 'out'];
export const footDefault = () => ({
  order: Object.keys(FOOT),
  hide: { ir: [...NO_STAKE], inc: [...NO_STAKE], last: ['over'], ...Object.fromEntries(FOOT_EXTRA.map((k) => [k, [...ALL_SESSIONS]])) },
  opt: {},
});

/** The app's header. gap is the empty space: what comes after it goes to the right. */
export const HEADER = {
  brand: { label: 'Logo', opts: [{ k: 'text', label: 'Show the name', type: 'bool', d: true }] },
  series: { label: 'Series' },
  track: { label: 'Track', opts: [{ k: 'sub', label: 'Show the layout, length and turns', type: 'bool', d: true }] },
  clock: { label: 'Session clock', opts: [{ k: 'sub', label: 'Show the session and lap', type: 'bool', d: true }] },
  gap: { label: 'Space', fixed: true, note: 'What comes after it goes to the right' },
  sof: { label: 'Strength of field' },
  conn: { label: 'Connection' },
};
export const headerDefault = () => ({ order: Object.keys(HEADER), hide: { sof: ['test'] }, opt: {} });

// ---- any list -------------------------------------------------------------------------------
/** The saved order, without what no longer exists and with what is new, so an old file still works. */
export function orderOf(cfg, table) {
  const known = (cfg?.order ?? []).filter((k, n, l) => table[k] && l.indexOf(k) === n);
  const all = [...known, ...Object.keys(table).filter((k) => !known.includes(k))];
  const kids = (p) => Object.keys(table).filter((k) => table[k].child === p);
  return all.filter((k) => !table[k].child).flatMap((k) => [k, ...kids(k)]);
}
export const hiddenIn = (cfg, table, k, session) => !table[k]?.fixed && !!cfg?.hide?.[k]?.includes(session);
export const shownIn = (cfg, table, session) => orderOf(cfg, table).filter((k) => !hiddenIn(cfg, table, k, session));
export function optOf(cfg, table, k, name) {
  const v = cfg?.opt?.[k]?.[name], o = table[k]?.opts?.find((x) => x.k === name);
  if (!o) return undefined;
  if (o.type === 'seg' || o.type === 'select') return o.values.some(([x]) => x === v) ? v : o.d;
  if (o.type === 'bool') return typeof v === 'boolean' ? v : o.d;
  return Array.isArray(v) ? v : o.d;
}

// ---- standings --------------------------------------------------------------------------------
/** A file from before: the car column split in three, delta count as an option, race over a session. */
export function migrateStand(cfg) {
  if (!cfg) return standDefault();
  if (cfg.v >= 2) return cfg;
  const split = (l) => l.flatMap((k) => (k === 'car' ? ['num', 'pg', 'make'] : [k]));
  const out = { ...standDefault(), order: cfg.order ? split(cfg.order) : Object.keys(STAND), opt: {} };
  const name = (out.order.includes('name') ? out.order.indexOf('name') : 0) + 1;
  out.order = out.order.filter((k) => k !== 'out' && k !== 'pit');
  out.order.splice(name, 0, 'out', 'pit');
  for (const [k, s] of Object.entries(cfg.hide ?? {})) {
    for (const to of k === 'car' ? ['num', 'pg', 'make'] : [k]) out.hide[to] = [...new Set([...(out.hide[to] ?? []), ...s])];
  }
  if (cfg.deltas) out.opt.delta = { laps: cfg.deltas };
  return out;
}

const base = (k) => (/^d[1-5]$/.test(k) ? 'delta' : k);

/** The columns of this session, delta already split in d1 d2... The inline ones are not columns. */
export function standCols(cfg, session) {
  const n = optOf(cfg, STAND, 'delta', 'laps');
  return shownIn(cfg, STAND, session).filter((k) => !STAND[k].inline)
    .flatMap((k) => (k === 'delta' ? ['d1', 'd2', 'd3', 'd4', 'd5'].slice(0, n) : [k]));
}

function width(k, n, cols, cfg, over) {
  if (over && OVER_W[k]) return OVER_W[k];
  if (k === 'num' && cols[n - 1] === 'pos') return '32px';   // it tucks in under the position's cut, 14 px
  if (k === 'ir' && !optOf(cfg, STAND, 'ir', 'gain')) return '52px';
  if (k === 'tyre' && optOf(cfg, STAND, 'tyre', 'show') === 'text') return '30px';
  return STAND[base(k)].w;
}
export const standGrid = (cols, cfg, over) => cols.map((k, n) => width(k, n, cols, cfg, over)).join(' ');

const GAP = 6, PAD = 6;
/** Pixels the row needs at the least. */
export function standNeed(cols, cfg, over) {
  const sum = cols.reduce((all, k, n) => all + parseInt(width(k, n, cols, cfg, over).replace('minmax(', ''), 10), 0);
  return sum + GAP * Math.max(0, cols.length - 1) + PAD;
}
// what goes first when the panel is too narrow; pos and name always stay
const DROP = ['d5', 'd4', 'd3', 'd2', 'pg', 'flag', 'sr', 'tyre', 'd1', 'status', 'make', 'last', 'ir', 'int', 'best', 'gap', 'num'];
/** What fits in room px: nothing is ever cut in half, the least important go first. */
export function standFit(cols, cfg, over, room) {
  const out = [...cols], dropped = [];
  if (!room) return { cols: out, dropped };
  for (const k of DROP) {
    if (standNeed(out, cfg, over) <= room) break;
    const at = out.indexOf(k);
    if (at >= 0) { out.splice(at, 1); dropped.push(k); }
  }
  return { cols: out, dropped };
}
export const colName = (k) => (/^d[1-5]$/.test(k) ? `Delta ${k[1]}` : STAND[k].label);

/** The class header: the name over the first columns, then a title for each of the others. */
export function standHead(cols) {
  let lead = 0;
  while (lead < cols.length && STAND[base(cols[lead])].lead) lead++;
  lead = Math.max(1, lead);
  const titles = [];
  for (const k of cols.slice(lead)) {
    const b = base(k), prev = titles[titles.length - 1];
    if (prev?.b === b) prev.span++;
    else titles.push({ b, title: STAND[b].title, a: STAND[b].a, span: 1 });
  }
  return { lead, titles };
}

/** How many footer items fit: each needs about this much to read. */
export const FOOT_W = 96;
export const footFit = (items, room) => (room ? { items: items.slice(0, Math.max(1, Math.floor(room / FOOT_W))), dropped: items.slice(Math.max(1, Math.floor(room / FOOT_W))) } : { items, dropped: [] });
