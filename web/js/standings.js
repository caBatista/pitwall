import { esc, lapTime, gapText, prefs, savePrefs, flagHtml, makeHtml, stHtml, talkHtml, tyreHtml, HELMET, OUT, flagFx, irHtml, pitHtml, ST, fitIr, irKeyOf, INV, patchRows } from './util.js';
import { driverActions } from './drivers.js';

const ROW = 30, ME = 44;   // .rrow / .rrow.me with its margins, px in the panel's scale

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
  return { list: rows.filter((r, k) => pins.has(k) || shown.has(r)), start, max, slots, free: others.length };
}

/**
 * Standings. Multiclass-aware: by default cars are grouped per class (each with
 * its own class position and gaps to the class leader), or you can flip to a
 * single overall list. Lapped cars show "+1L" instead of a time gap.
 * Rows share the relative's look (slanted pos / class # blocks, Montserrat, chips);
 * columns: pos | # make | country | name [OUT] | SR | iR | tyre | int | gap | last |
 * fastest | Δ1 Δ2 Δ3 (their latest laps minus mine, newest first) | flag.
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
    this.lastCtl = '';
    // how many rows fit depends on the panel, not on the data: measured only when it resizes
    new ResizeObserver(() => { this.room = this.body.clientHeight; S.invalidate(); }).observe(this.body);
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
    // their k-th latest lap minus my k-th latest: + they are slower, - they are faster
    const delta = (c, k) => {
      if (c.i === st.me.i || c.lh?.[k] == null || myLaps[k] == null) return ['dl', ''];
      const v = Math.round((c.lh[k] - myLaps[k]) * 10) / 10;
      return [`dl ${v > 0 ? 'slower' : v < 0 ? 'faster' : ''}`, `${v > 0 ? '+' : ''}${v.toFixed(1)}`];
    };

    // race over: the results, nothing live - no tags but the chequered flag (finished), no tyre / int / gap / last / delta
    const over = !!st.session?.over;
    const rowHtml = (c, inGroup) => {
      const d = S.drivers[c.i];
      const cls = S.classMap.get(d.cls) || { color: '#8b95a7' };
      const me = c.i === st.me.i;
      const pos = (inGroup ? c.cp : c.p) ?? '–';
      const gl = inGroup ? c.gl : c.go, ld = inGroup ? c.ld : c.lo;
      const gi = inGroup ? c.gi : c.gio, li = inGroup ? c.li : c.lio;
      const leader = pos === 1;
      // always behind, so no '+': unsigned gaps
      const gapTxt = leader ? (isRace ? 'Leader' : '') : gapText(gl, ld, false);
      const intTxt = leader ? '' : gapText(gi, li, false);
      const off = c.srf < 0;
      const [lic, sr] = (d.lic || '').split(' ');
      const gain = isRace ? (inGroup ? c.pgc : c.pg) : null;   // positions gained since the start
      const pg = gain ? `<span class="pg ${gain > 0 ? 'up' : 'down'}">${gain > 0 ? '▲' : '▼'}${Math.abs(gain)}</span>` : (isRace ? '<span class="pg"></span>' : '');
      const cells = [
        ['rpos', pos],
        ['rcar', `<span class="rn">${esc(d.num)}</span>${pg}<span class="mk">${makeHtml(d.make)}</span>`, `--cc:${cls.color}`],
        ['fc', flagHtml(d.country)],
        ['rname', `<span class="nm">${esc(d.name)}</span>${over ? '' : (c.out ? OUT : '') + pitHtml(c, st.session?.kind)}`],
        ['sr', lic ? `<b>${esc((sr || '').slice(0, 3))}</b><i>${esc(lic)}</i>` : '', `--lc:${d.licColor}`],
        ['irb', irHtml(d.ir, c.irg, isRace)],
      ];
      const best = [`t ${c.cb ? 'cb' : ''}`, c.best ? lapTime(c.best) : '-:--.---'];
      if (over) cells.push(best, ['sflag', c.fin ? ST.fin : '']);
      else cells.push(
        ['c', tyreHtml(c.tc)],
        ['t dim', intTxt],
        [`t ${leader ? 'dim' : ''}`, gapTxt],
        [`t ${c.pb ? 'pb' : ''}`, c.last ? lapTime(c.last) + (c.lastx ? INV : '') : '-:--.---'],
        best,
        delta(c, 0), delta(c, 1), delta(c, 2),
        ['sflag', `${talkHtml(st.talk === c.i)}<span class="fxw" style="${flagFx('s' + c.i, c.fl)}">${stHtml(c, true)}</span>`],
      );
      return { key: c.i, i: c.i, cls: `rrow srow ${over ? 'over' : ''} ${me ? 'me' : ''} ${!over && (off || c.pit) ? 'pitrow' : ''}`, cells };
    };

    // class header = title row: class, drivers and SOF over pos..iR, then the column titles
    const head = (key, name, color, n, sof) => ({ key, cls: `ghead srow${over ? ' over' : ''}`, style: `--cc:${color}`, html: `
        <div class="gl">${esc(name)}<span class="gn" title="Drivers">${HELMET}${n}</span>${sof ? `<span class="gn">SOF ${sof}</span>` : ''}</div>
        ${over ? '<div class="r">Fastest</div><div class="c">Flag</div>' : `<div class="c">Tyre</div><div class="r">Int</div><div class="r">Gap</div><div class="r">Last</div><div class="r">Fastest</div>
        <div class="c dhead">Delta</div><div class="c">Flag</div>`}` });

    const rows = [];
    if (grouped) {
      for (const cl of S.classes) {
        const list = byCls.get(cl.id);
        if (!list || !list.length) continue;
        rows.push(head('h' + cl.id, cl.name, cl.color, cl.n, cl.sof));
        for (const c of list) rows.push(rowHtml(c, true));
      }
    } else {
      const all = [...byCls.values()].flat().sort((a, b) => (a.p ?? 999) - (b.p ?? 999));
      rows.push(head('all', 'Overall', 'var(--accent)', all.length, null));
      for (const c of all) rows.push(rowHtml(c, false));
    }
    if (!rows.length) rows.push({ key: 'none', cls: 'map-note', html: '<b>No cars yet</b>Cars appear here as soon as they are on track.' });
    // the chips are as wide as the widest in the whole field, hidden rows included: measure with them all
    const irKey = irKeyOf(S, st.cars);
    if (irKey !== this.irKey) {
      patchRows(this.body, rows);
      if (fitIr(this.body, irKey)) this.irKey = irKey;
    }
    const v = visibleRows(rows, st.me.i, S.drivers, this.room, this.from);
    this.from = v.start; this.max = v.max;
    patchRows(this.body, v.list);
    const thumb = v.max ? `--tt:${(100 * v.start / v.free).toFixed(1)}%;--th:${(100 * v.slots / v.free).toFixed(1)}%` : '';
    if (thumb !== this.thumb) { this.body.style.cssText = thumb; this.thumb = thumb; }

    // "you" summary bar
    const m = st.me, mc = st.cars.find((c) => c.i === m.i);
    if (mc) {
      // incidents: current / next penalty / DQ; by how far the next limit is: green, white at 12x, amber at 8x, red at 4x
      const inc = m.inc ?? null;
      let pen = m.incPen;
      if (pen && inc != null && inc >= pen && m.incPenNext) pen += Math.ceil((inc - pen + 1) / m.incPenNext) * m.incPenNext;
      const limits = [pen, m.incDq].filter((x) => x && inc != null && x > inc);
      const toGo = limits.length ? Math.min(...limits) - inc : null;
      const incCls = toGo == null ? '' : toGo <= 4 ? 'neg' : toGo <= 8 ? 'warn' : toGo <= 12 ? '' : 'pos';
      const incMax = [pen, m.incDq].filter((x) => x != null).map((x) => `/${x}x`).join('');   // the limits, smaller and never coloured
      const g = m.irGain;
      const bar = `
        <div class="kv"><small>Position</small><b>${mc.cp != null ? `P${mc.cp}` : '–'}${multi && mc.p != null ? `<span class="of">P${mc.p}</span>` : ''}</b></div>
        <div class="kv"><small>Lap</small><b>${m.lap ?? '–'}${isRace && !over && st.session.raceLaps ? `<span class="of">/${st.session.raceLaps}${st.session.raceLapsEst ? '*' : ''}</span>` : ''}</b></div>
        ${over ? '' : `<div class="kv"><small>Last</small><b>${lapTime(m.last)}${m.lastx && m.last ? INV : ''}</b></div>`}
        <div class="kv"><small>Best</small><b>${lapTime(m.best)}</b></div>
` + (st.session?.kind === 'practice' ? '' : `
        <div class="kv"><small>iRating</small><b class="${g == null ? '' : g >= 0 ? 'pos' : 'neg'}">${g == null ? '–' : (g > 0 ? '+' : '') + g}</b></div>
        <div class="kv"><small>Incidents</small><b><span class="${incCls}">${inc == null ? '–' : inc + 'x'}</span>${inc != null && incMax ? `<span class="of">${incMax}</span>` : ''}</b></div>`);   // practice: nothing at stake
      if (bar !== this.lastBar) { this.meBar.innerHTML = bar; this.lastBar = bar; }
    }
  },
};
