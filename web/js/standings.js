import { esc, lapTime, gapText, prefs, savePrefs, flagHtml, makeHtml, stHtml, talkHtml, tyreHtml, HELMET, OUT, flagFx, irHtml, pitHtml, ST, fitIr, irKeyOf, INV, patchRows } from './util.js';

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
      const row = e.target.closest('.srow[data-i]');
      if (row) { const i = Number(row.dataset.i); S.sel = S.sel === i ? null : i; }
    });
    this.lastCtl = '';
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
    // (* = one of the two laps was invalidated / had an incident)
    const delta = (c, k) => {
      if (c.i === st.me.i || c.lh?.[k] == null || myLaps[k] == null) return ['dl', ''];
      const v = Math.round((c.lh[k] - myLaps[k]) * 10) / 10;
      const x = c.lx?.[k] || myCar.lx?.[k];
      return [`dl ${v > 0 ? 'slower' : v < 0 ? 'faster' : ''}`, `${v > 0 ? '+' : ''}${v.toFixed(1)}${x ? INV : ''}`];
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
      return { key: c.i, i: c.i, cls: `rrow srow ${over ? 'over' : ''} ${me ? 'me' : ''} ${S.sel === c.i ? 'sel' : ''} ${!over && (off || c.pit) ? 'pitrow' : ''}`, cells };
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
    patchRows(this.body, rows);
    fitIr(this.body, irKeyOf(S, st.cars));

    // "you" summary bar
    const m = st.me, mc = st.cars.find((c) => c.i === m.i);
    if (mc) {
      // incidents: current / next penalty / DQ; yellow 8x before the next limit, red 4x before
      const inc = m.inc ?? null;
      let pen = m.incPen;
      if (pen && inc != null && inc >= pen && m.incPenNext) pen += Math.ceil((inc - pen + 1) / m.incPenNext) * m.incPenNext;
      const limits = [pen, m.incDq].filter((x) => x && inc != null && x > inc);
      const toGo = limits.length ? Math.min(...limits) - inc : null;
      const incCls = toGo == null ? '' : toGo <= 4 ? 'neg' : toGo <= 8 ? 'warn' : '';
      const incTxt = inc == null ? '–' : [inc, pen, m.incDq].filter((x) => x != null).map((x) => x + 'x').join('/');
      const g = m.irGain;
      const bar = `
        <div class="kv"><small>Position</small><b>${mc.p != null ? `P${mc.p}` : '–'}${multi && mc.p != null ? ` · C${mc.cp}` : ''}</b></div>
        <div class="kv"><small>Lap</small><b>${m.lap ?? '–'}${isRace && !over && st.session.raceLaps ? `<span class="of">/${st.session.raceLaps}${st.session.raceLapsEst ? '*' : ''}</span>` : ''}</b></div>
        ${over ? '' : `<div class="kv"><small>Last</small><b>${lapTime(m.last)}${m.lastx && m.last ? INV : ''}</b></div>`}
        <div class="kv"><small>Best</small><b>${lapTime(m.best)}</b></div>
` + (st.session?.kind === 'practice' ? '' : `
        <div class="kv"><small>iRating</small><b class="${g == null ? '' : g >= 0 ? 'pos' : 'neg'}">${g == null ? '–' : (g > 0 ? '+' : '') + g}</b></div>
        <div class="kv"><small>Incidents</small><b class="${incCls}">${incTxt}</b></div>`);   // practice: nothing at stake
      if (bar !== this.lastBar) { this.meBar.innerHTML = bar; this.lastBar = bar; }
    }
  },
};
