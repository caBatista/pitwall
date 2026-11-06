import { esc, fmt, lapTime, gapText, prefs, savePrefs, flagHtml, makeHtml, talkHtml, tyreHtml, HELMET, OUT, flagFx, irHtml, pitHtml, ST, fitIr, irKeyOf, INV, patchRows } from './util.js';
import { driverActions } from './drivers.js';
import { CLASS_HEAD, FOOT, STAND, colName, driverName, footFit, optOf, shownIn, standCols, standFit, standGrid, standHead, standNeed, viewSession } from './columns.js';

const ROW = 30, ME = 30;   // .rrow / .rrow.me with its margins, px in the panel's scale

/**
 * The list scrolls a whole row at a time, so nobody is ever cut in half. Which rows show: the class
 * headers, the class leaders and the reference driver with the 3 cars either side are always there,
 * in their place, and the rest of the panel is a window over the other rows. If it is too short for
 * all of that, the least important go.
 */
function visibleRows(rows, ref, drivers, room, from) {
  if (!room) return { list: rows, start: 0, max: 0, slots: rows.length, free: rows.length };
  const at = rows.findIndex((r) => r.i === ref);
  const near = (n) => {
    const out = at < 0 ? [] : [at];
    for (let j = at - 1; at >= 0 && j >= 0 && j >= at - n && rows[j].i != null; j--) out.push(j);
    for (let j = at + 1; at >= 0 && j < rows.length && j <= at + n && rows[j].i != null; j++) out.push(j);
    return out;
  };
  const heads = [], leaders = [], seen = new Set();
  rows.forEach((r, k) => {
    if (r.i == null) { if (r.key !== 'none') heads.push(k); return; }
    const cls = drivers[r.i]?.cls;
    if (!seen.has(cls)) { seen.add(cls); leaders.push(k); }
  });
  const height = (list) => [...list].reduce((sum, k) => sum + (rows[k].i === ref ? ME : ROW), 0);
  let pins = new Set();
  for (const tier of [[...heads, ...leaders, ...near(3)], [...heads, ...near(3)], [...heads, ...near(1)]]) {
    const set = new Set(tier);
    if (height(set) <= room - 2 * ROW) { pins = set; break; }   // always leave something to scroll
  }
  const others = rows.filter((r, k) => !pins.has(k));
  const slots = Math.floor((room - height(pins)) / ROW);
  const max = Math.max(0, others.length - slots);
  const start = Math.min(from, max);
  const shown = new Set(others.slice(start, start + slots));
  const list = rows.filter((r, k) => pins.has(k) || shown.has(r));
  // a class header with none of its drivers in view would just look like an empty class
  return { list: list.filter((r, k) => r.i != null || r.key === 'none' || list[k + 1]?.i != null), start, max, slots, free: others.length };
}

// one cell of a row; x: what the row already worked out, o: the options of each column (see options())
const delta = (c, k, x) => {   // their k-th latest lap minus my k-th latest: + they are slower, - they are faster
  if (x.me || c.lh?.[k] == null || x.myLaps[k] == null) return ['dl', ''];
  const k10 = 10 ** x.o.deltaDec, v = Math.round((c.lh[k] - x.myLaps[k]) * k10) / k10;
  return [`dl ${v > 0 ? 'slower' : v < 0 ? 'faster' : ''}`, `${v > 0 ? '+' : ''}${v.toFixed(x.o.deltaDec)}`];
};
const PENALTY = new Set(['dq', 'black', 'repair', 'warn']);
function statusHtml(c, off) {
  if (ST[c.fl] && !(PENALTY.has(c.fl) && off.has('pen'))) return ST[c.fl];
  if (c.pit && !off.has('pit')) return ST.pit;
  return c.cb && !off.has('fast') ? ST.fast : '';
}
const CELL = {
  pos: (c, x) => ['spos', `<span class="sp">${x.pos}</span>${x.o.posNum ? `<span class="sn">${esc(x.d.num)}</span>` : ''}`, `--cc:${x.color}`],
  pg: (c, x) => ['pgc', x.pg],
  make: (c, x) => ['mk', makeHtml(x.d.make)],
  flag: (c, x) => ['fc', flagHtml(x.d.country)],
  name: (c, x) => ['rname', `<span class="nm">${esc(x.o.name(x.d))}</span>${x.over ? '' : (c.out && x.o.out ? OUT : '') + (x.o.pit ? pitHtml(c, x.kind) : '')}`],
  sr: (c, x) => ['sr', x.lic ? `<b>${esc((x.sr || '').slice(0, 3))}</b><i>${esc(x.lic)}</i>` : '', `--lc:${x.d.licColor}`],
  ir: (c, x) => ['irb', irHtml(x.d.ir, c.irg, x.isRace && x.o.gain, x.o.irFmt)],
  tyre: (c, x) => ['c', tyreHtml(c.tc, x.o.tyreText)],
  int: (c, x) => ['t dim', x.int],
  gap: (c, x) => [`t ${x.leader ? 'dim' : ''}`, x.gap],
  last: (c, x) => [`t ${c.pb ? 'pb' : ''}`, c.last ? lapTime(c.last, x.o.lastDec) + (c.lastx ? INV : '') : x.o.lastNone],
  best: (c, x) => [`t ${c.cb ? 'cb' : ''}`, c.best ? lapTime(c.best, x.o.bestDec) : x.o.bestNone],
  d1: (c, x) => delta(c, 0, x),
  d2: (c, x) => delta(c, 1, x),
  d3: (c, x) => delta(c, 2, x),
  d4: (c, x) => delta(c, 3, x),
  d5: (c, x) => delta(c, 4, x),
  status: (c, x) => (x.over ? ['sflag', c.fin && !x.o.off.has('fin') ? ST.fin : '']
    : ['sflag', `${talkHtml(x.talk === c.i)}<span class="fxw" style="${flagFx('s' + c.i, c.fl)}">${statusHtml(c, x.o.off)}</span>`]),
};
const noTime = (dec) => `-:--${dec ? '.' + '-'.repeat(dec) : ''}`;

/** The choices of the user, looked up once, not for every row 20 times a second. */
function options(cfg, session) {
  const on = (k) => shownIn(cfg, STAND, session).includes(k), opt = (k, n) => optOf(cfg, STAND, k, n);
  const lastDec = opt('last', 'dec'), bestDec = opt('best', 'dec');
  const format = opt('name', 'format'), keep = opt('name', 'number'), names = new Map();   // written once for each driver
  const name = (d) => {
    if (!names.has(d.i)) names.set(d.i, driverName(keep ? d.user || d.name : d.name, format, keep));
    return names.get(d.i);
  };
  return {
    name,
    out: on('out'), pit: on('pit'), gain: opt('ir', 'gain'), irFmt: opt('ir', 'fmt'), tyreText: opt('tyre', 'show') === 'text',
    intDec: opt('int', 'dec'), gapDec: opt('gap', 'dec'), lastDec, bestDec, deltaDec: opt('delta', 'dec'),
    lastNone: noTime(lastDec), bestNone: noTime(bestDec), off: new Set(opt('status', 'off')),
  };
}

const kFmt = (v) => (v / 1000).toFixed(1) + 'k';

/**
 * Standings. Multiclass-aware: by default cars are grouped per class (each with
 * its own class position and gaps to the class leader), or you can flip to a
 * single overall list. Lapped cars show "+1L" instead of a time gap.
 * Rows share the relative's look (slanted pos / class # blocks, Montserrat, chips);
 * columns: pos | # make | country | name [OUT] | SR | iR | tyre | int | gap | last |
 * fastest | Δ1 Δ2 Δ3 (their latest laps minus mine, newest first) | flag.
 * Which ones and in what order is the user's choice (columns.js, Settings).
 */
export const standings = {
  id: 'w-standings',
  mount(root, S) {
    root.innerHTML = `
      <div class="card-h">
        <div class="ttl"><i></i>Standings</div>
        <div class="ctl" id="st-ctl"></div>
      </div>
      <div class="s-body" id="st-body"></div>
      <div class="me-bar" id="st-me"></div>`;
    this.ctl = root.querySelector('#st-ctl');
    this.body = root.querySelector('#st-body');
    this.meBar = root.querySelector('#st-me');
    root.addEventListener('click', (e) => {
      const seg = e.target.closest('[data-mode]');
      if (seg) { prefs.standMode = seg.dataset.mode; savePrefs(); return; }
      const chip = e.target.closest('[data-cls]');
      if (chip) {
        const id = Number(chip.dataset.cls);
        prefs.classFilter = prefs.classFilter === id ? null : id;
        savePrefs(); return;
      }
    });
    driverActions(root, S);
    addEventListener('prefs', () => { this.layoutKey = ''; });
    this.lastCtl = '';
    // how many rows fit depends on the panel, not on the data: measured only when it resizes
    new ResizeObserver(() => { this.room = this.body.clientHeight; this.wide = this.body.clientWidth; S.invalidate(); }).observe(this.body);
    this.from = this.max = this.wheel = 0;
    const scroll = (n) => {
      const from = Math.max(0, Math.min(this.max, this.from + n));
      if (from !== this.from) { this.from = from; S.invalidate(); }
    };
    this.body.addEventListener('wheel', (e) => {
      this.wheel += e.deltaY;
      const n = Math.trunc(this.wheel / 40);
      if (n) { this.wheel -= n * 40; scroll(n); }
    }, { passive: true });
    let touch = 0;
    this.body.addEventListener('touchstart', (e) => { touch = e.touches[0].clientY; }, { passive: true });
    this.body.addEventListener('touchmove', (e) => {
      const n = Math.trunc((touch - e.touches[0].clientY) / ROW);
      if (n) { touch -= n * ROW; scroll(n); }
    }, { passive: true });
  },

  update(S) {
    const st = S.st;
    if (!st) return;
    const multi = S.classes.length > 1;
    const grouped = !multi || prefs.standMode === 'class';   // single class: one group, so its header (count, SOF) shows
    const isRace = st.session.isRace;
    const kind = st.session.kind;

    // controls
    const ctl = (multi
      ? `<div class="seg"><button data-mode="class" class="${grouped ? 'on' : ''}">Class</button><button data-mode="overall" class="${grouped ? '' : 'on'}">Overall</button></div>` +
        S.classes.map((c) => `<span class="cls-chip ${prefs.classFilter === c.id ? 'on' : ''}" data-cls="${c.id}" style="--cc:${c.color}">${esc(c.name)}</span>`).join('')
      : '');
    if (ctl !== this.lastCtl) { this.ctl.innerHTML = ctl; this.lastCtl = ctl; }

    const byCls = new Map();
    for (const c of st.cars) {
      const d = S.drivers[c.i];
      if (!d) continue;
      if (prefs.classFilter != null && d.cls !== prefs.classFilter) continue;
      if (kind === 'qualify' && !c.best) continue;   // qualifying: only drivers with a completed lap
      if (!byCls.has(d.cls)) byCls.set(d.cls, []);
      byCls.get(d.cls).push(c);
    }

    const myCar = st.cars.find((c) => c.i === st.me.i) || {};
    const myLaps = myCar.lh || [];

    // race over: the results, nothing live - no tags but the chequered flag (finished), no tyre / int / gap / last / delta
    const over = !!st.session?.over;
    const session = viewSession(kind, over, !st.session.inCar);
    // worked out when something changes (the session, the panel, a setting), not on every frame
    const layoutKey = `${session}|${this.wide}|${innerWidth < 800}`;
    if (layoutKey !== this.layoutKey) {
      this.layoutKey = layoutKey;
      const want = standCols(prefs.stand, session);
      const fit = standFit(want, prefs.stand, over, innerWidth < 800 ? 0 : this.wide);   // a phone scrolls sideways instead
      this.cols = fit.cols;
      this.o = options(prefs.stand, session);
      this.o.posNum = optOf(prefs.stand, STAND, 'pos', 'num');
      this.body.parentElement.style.setProperty('--scols', standGrid(fit.cols, prefs.stand, over));   // not on body: its style is rewritten below
      const { lead } = standHead(fit.cols);
      this.lead = lead;
      this.heads = '';   // the class header stays alone: Int and Gap are named in the leader's row
      this.classItems = shownIn(prefs.classHead, CLASS_HEAD, session);
      const foot = footFit(shownIn(prefs.standFoot, FOOT, session), this.meBar.clientWidth);
      this.foot = foot.items;
      this.lastBar = null;
      try {
        localStorage.setItem('pitwall.fit', JSON.stringify({ session, room: this.wide, need: standNeed(want, prefs.stand, over),
          cols: fit.dropped.map(colName), foot: foot.dropped.map((k) => FOOT[k].label) }));
      } catch { /* ignore */ }
    }
    const cols = this.cols, o = this.o;
    const rowHtml = (c, inGroup) => {
      const d = S.drivers[c.i];
      const cls = S.classMap.get(d.cls) || { color: '#8b95a7' };
      const me = c.i === st.me.i;
      const pos = (inGroup ? c.cp : c.p) ?? '–';
      const gl = inGroup ? c.gl : c.go, ld = inGroup ? c.ld : c.lo;
      const gi = inGroup ? c.gi : c.gio, li = inGroup ? c.li : c.lio;
      const leader = pos === 1;
      // always behind, so no '+': unsigned gaps
      const gapTxt = leader ? '<span class="hd">Gap</span>' : gapText(gl, ld, false, o.gapDec);
      const intTxt = leader ? '<span class="hd">Int</span>' : gapText(gi, li, false, o.intDec);
      const off = c.srf < 0;
      const [lic, sr] = (d.lic || '').split(' ');
      const gain = isRace ? (inGroup ? c.pgc : c.pg) : null;   // positions gained since the start
      const pg = gain ? `<span class="pg ${gain > 0 ? 'up' : 'down'}">${gain > 0 ? '▲' : '▼'}${Math.abs(gain)}</span>` : (isRace ? '<span class="pg"></span>' : '');
      const x = { d, color: cls.color, me, pos, pg, lic, sr, leader, gap: gapTxt, int: intTxt, over, kind, isRace, myLaps, talk: st.talk, o };
      const cells = cols.map((k) => CELL[k](c, x));
      return { key: c.i, i: c.i, cls: `rrow srow ${over ? 'over' : ''} ${me ? 'me' : ''} ${!over && (off || c.pit) ? 'pitrow' : ''}`, cells };
    };

    // class header = title row: class, drivers and SOF over pos..iR, then the column titles
    const headItem = (k, n, sof, laps) => {
      if (k === 'drivers') return `<span class="gn" title="Drivers">${optOf(prefs.classHead, CLASS_HEAD, k, 'show') === 'icon' ? HELMET + n : `${n} drivers`}</span>`;
      if (k === 'sof') return sof ? `<span class="gn">SOF ${optOf(prefs.classHead, CLASS_HEAD, k, 'fmt') === 'k' ? kFmt(sof) : sof}</span>` : '';
      return laps ? `<span class="gn">Lap ${laps}</span>` : '';
    };
    const head = (key, name, color, n, sof, laps) => ({ key, cls: `ghead srow${over ? ' over' : ''}`, style: `--cc:${color}`, html: `
        <div class="gl" style="grid-column:1 / span ${this.lead}">${esc(name)}${this.classItems.map((k) => headItem(k, n, sof, laps)).join('')}</div>
        ${this.heads}` });

    const rows = [];
    if (grouped) {
      for (const cl of S.classes) {
        const list = byCls.get(cl.id);
        if (!list || !list.length) continue;
        rows.push(head('h' + cl.id, cl.name, cl.color, cl.n, cl.sof, list[0].lap));
        for (const c of list) rows.push(rowHtml(c, true));
      }
    } else {
      const all = [...byCls.values()].flat().sort((a, b) => (a.p ?? 999) - (b.p ?? 999));
      rows.push(head('all', 'Overall', 'var(--accent)', all.length, null, all[0]?.lap));
      for (const c of all) rows.push(rowHtml(c, false));
    }
    if (!rows.length) rows.push({ key: 'none', cls: 'map-note', html: '<b>No cars yet</b>Cars appear here as soon as they are on track.' });
    // the chips are as wide as the widest in the whole field, hidden rows included: measure with them all
    const irKey = irKeyOf(S, st.cars);
    if (irKey + o.irFmt + o.gain !== this.irKey && cols.includes('ir')) {
      patchRows(this.body, rows);
      if (fitIr(this.body, irKey + o.irFmt + o.gain)) this.irKey = irKey + o.irFmt + o.gain;
    }
    const v = visibleRows(rows, st.me.i, S.drivers, this.room, this.from);
    this.from = v.start; this.max = v.max;
    patchRows(this.body, v.list);
    const thumb = v.max ? `--tt:${(100 * v.start / v.free).toFixed(1)}%;--th:${(100 * v.slots / v.free).toFixed(1)}%` : '';
    if (thumb !== this.thumb) { this.body.style.cssText = thumb; this.thumb = thumb; }

    // "you" summary bar
    // the footer is always the user, whoever the board follows
    const u = st.user ?? st.me, mc = st.cars.find((c) => c.i === u.i);
    if (mc) {
      const m = u.i === st.me.i ? st.me : { ...u, last: mc.last, lastx: mc.lastx, best: mc.best };
      // incidents: current / next penalty / DQ; by how far the next limit is: green, white at 12x, amber at 8x, red at 4x
      const inc = m.inc ?? null;
      let pen = m.incPen;
      if (pen && inc != null && inc >= pen && m.incPenNext) pen += Math.ceil((inc - pen + 1) / m.incPenNext) * m.incPenNext;
      const limits = [pen, m.incDq].filter((x) => x && inc != null && x > inc);
      const toGo = limits.length ? Math.min(...limits) - inc : null;
      const incCls = toGo == null ? '' : toGo <= 4 ? 'neg' : toGo <= 8 ? 'warn' : toGo <= 12 ? '' : 'pos';
      const incMax = [pen, m.incDq].filter((x) => x != null).map((x) => `/${x}x`).join('');   // the limits, smaller and never coloured
      const g = m.irGain, cf = prefs.standFoot, fo = (k, n) => optOf(cf, FOOT, k, n);
      const kv = (k, title, html) => `<div class="kv k-${k}"><small>${title}</small><b>${html}</b></div>`;
      const ITEM = {
        pos: () => kv('pos', 'Position', `${mc.cp != null ? `P${mc.cp}` : '–'}${multi && mc.p != null && fo('pos', 'overall') ? `<span class="of">P${mc.p}</span>` : ''}`),
        lap: () => kv('lap', 'Lap', `${m.lap ?? '–'}${isRace && !over && st.session.raceLaps && fo('lap', 'total') ? `<span class="of">/${st.session.raceLaps}${st.session.raceLapsEst ? '*' : ''}</span>` : ''}`),
        last: () => kv('last', 'Last', `${lapTime(m.last, fo('last', 'dec'))}${m.lastx && m.last ? INV : ''}`),
        best: () => kv('best', 'Best', lapTime(m.best, fo('best', 'dec'))),
        ir: () => `<div class="kv k-ir"><small>iRating</small><b class="${g == null ? '' : g >= 0 ? 'pos' : 'neg'}">${g == null ? '–' : (g > 0 ? '+' : '') + g}</b></div>`,
        inc: () => kv('inc', 'Incidents', `<span class="${incCls}">${inc == null ? '–' : inc + 'x'}</span>${inc != null && incMax && fo('inc', 'limits') ? `<span class="of">${incMax}</span>` : ''}`),
        cur: () => kv('cur', 'Current', lapTime(m.cur, fo('cur', 'dec'))),
        delta: () => `<div class="kv k-delta"><small>Delta</small><b class="${!m.deltaOk ? '' : m.delta <= 0 ? 'pos' : 'neg'}">${m.deltaOk ? (m.delta > 0 ? '+' : '') + m.delta.toFixed(2) : '–'}</b></div>`,
        fuel: () => kv('fuel', 'Fuel', st.fuel?.level != null ? `${fmt.vol(st.fuel.level).toFixed(1)}<span class="of">${fmt.volU()}</span>` : '–'),
        track: () => kv('track', 'Track', st.wx?.track != null ? `${fmt.temp(st.wx.track).toFixed(1)}<span class="of">${fmt.tempU()}</span>` : '–'),
        air: () => kv('air', 'Air', st.wx?.air != null ? `${fmt.temp(st.wx.air).toFixed(1)}<span class="of">${fmt.tempU()}</span>` : '–'),
      };
      const bar = this.foot.map((k) => ITEM[k]()).join('');
      if (bar !== this.lastBar) { this.meBar.innerHTML = bar; this.lastBar = bar; }
    }
  },
};
