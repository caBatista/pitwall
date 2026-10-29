import { esc, lapTime, gapText, prefs, savePrefs } from './util.js';

/**
 * Standings. Multiclass-aware: by default cars are grouped per class (each with
 * its own class position and gaps to the class leader), or you can flip to a
 * single overall list. Lapped cars show "+1L" instead of a time gap.
 */
export const standings = {
  id: 'w-standings',
  mount(root, S) {
    root.innerHTML = `
      <div class="card-h">
        <div class="ttl"><i></i>Standings</div>
        <div class="ctl" id="st-ctl"></div>
      </div>
      <div class="s-head"><div>Pos</div><div></div><div>#</div><div>Driver</div><div>iRating</div>
        <div class="r">Best</div><div class="r">Last</div><div class="r">Gap</div><div class="r">Int</div><div></div></div>
      <div class="s-body" id="st-body"></div>
      <div class="me-bar" id="st-me"></div>`;
    this.ctl = root.querySelector('#st-ctl');
    this.body = root.querySelector('#st-body');
    this.meBar = root.querySelector('#st-me');
    root.addEventListener('click', (e) => {
      const seg = e.target.closest('[data-mode]');
      if (seg) { prefs.standMode = seg.dataset.mode; savePrefs(); this.last = ''; return; }
      const chip = e.target.closest('[data-cls]');
      if (chip) {
        const id = Number(chip.dataset.cls);
        prefs.classFilter = prefs.classFilter === id ? null : id;
        savePrefs(); this.last = ''; return;
      }
      const row = e.target.closest('.row');
      if (row) { const i = Number(row.dataset.i); S.sel = S.sel === i ? null : i; this.last = ''; }
    });
    this.last = '';
    this.lastCtl = '';
  },

  update(S) {
    const st = S.st;
    if (!st) return;
    const multi = S.classes.length > 1;
    const grouped = multi && prefs.standMode === 'class';
    const isRace = st.session.isRace;

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
      if (!byCls.has(d.cls)) byCls.set(d.cls, []);
      byCls.get(d.cls).push(c);
    }

    const rowHtml = (c, inGroup) => {
      const d = S.drivers[c.i];
      const cls = S.classMap.get(d.cls) || { color: '#8b95a7' };
      const me = c.i === st.me.i;
      const big = inGroup ? c.cp : c.p;
      const sub = multi ? (inGroup ? `P${c.p}` : `C${c.cp}`) : '';
      const gl = inGroup ? c.gl : c.go, ld = inGroup ? c.ld : c.lo;
      const gi = inGroup ? c.gi : c.gio, li = inGroup ? c.li : c.lio;
      const leader = big === 1;
      const gapTxt = leader ? (isRace ? 'Leader' : '') : gapText(gl, ld);
      const intTxt = leader ? '' : gapText(gi, li);
      const off = c.srf < 0;
      const state = c.pit ? '<span class="tag">PIT</span>' : off ? '<span class="tag off">OFF</span>' : '';
      return `<div class="row ${me ? 'me' : ''} ${S.sel === c.i ? 'sel' : ''} ${off ? 'dim' : ''}" data-i="${c.i}" style="--cc:${cls.color}">
        <div class="pos">${big}${sub ? `<small>${sub}</small>` : ''}</div>
        <div class="cbar"></div>
        <div class="num">#${esc(d.num)}</div>
        <div class="name">${esc(d.name)}${d.team && d.team !== d.name ? `<small>${esc(d.team)}</small>` : `<small>${esc(d.car)}</small>`}</div>
        <div class="ir">${d.lic ? `<span class="lic" style="--lc:${d.licColor}">${esc(d.lic.split(' ')[0] + ' ' + (d.lic.split(' ')[1] || '').slice(0, 3))}</span>` : ''}${d.ir || ''}</div>
        <div class="t ${c.cb ? 'cb' : ''}">${lapTime(c.best)}</div>
        <div class="t ${c.pb ? 'pb' : 'dim'}">${lapTime(c.last)}</div>
        <div class="t ${leader ? 'dim' : ''}">${gapTxt}</div>
        <div class="t dim">${intTxt}</div>
        <div class="st">${state}</div>
      </div>`;
    };

    let html = '';
    if (grouped) {
      for (const cl of S.classes) {
        const list = byCls.get(cl.id);
        if (!list || !list.length) continue;
        const bests = list.map((c) => c.best).filter(Boolean);
        html += `<div class="ghead" style="--cc:${cl.color}">${esc(cl.name)} <em>${list.length} cars</em><span class="gb">${bests.length ? 'Best ' + lapTime(Math.min(...bests)) : ''}</span></div>`;
        html += list.map((c) => rowHtml(c, true)).join('');
      }
    } else {
      const all = [...byCls.values()].flat().sort((a, b) => a.p - b.p);
      html = all.map((c) => rowHtml(c, false)).join('');
    }
    if (!html) html = '<div class="map-note"><b>No cars yet</b>Cars appear here as soon as they are on track.</div>';
    if (html !== this.last) {
      const keep = this.body.scrollTop;
      this.body.innerHTML = html;
      this.body.scrollTop = keep;
      this.last = html;
    }

    // "you" summary bar
    const m = st.me, mc = st.cars.find((c) => c.i === m.i);
    if (mc) {
      const d = m.deltaOk && m.delta != null ? m.delta : null;
      const inc = m.inc != null ? `${m.inc}${m.incLimit && m.incLimit !== 'unlimited' ? '/' + m.incLimit : ''}` : '–';
      const bar = `
        <div class="kv"><small>Position</small><b>P${mc.p}${multi ? ` · C${mc.cp}` : ''}</b></div>
        <div class="kv"><small>Lap</small><b>${m.lap ?? '–'}</b></div>
        <div class="kv"><small>Last</small><b>${lapTime(m.last)}</b></div>
        <div class="kv"><small>Best</small><b>${lapTime(m.best)}</b></div>
        <div class="kv"><small>Δ Best</small><b class="${d == null ? '' : d <= 0 ? 'pos' : 'neg'}">${d == null ? '–' : (d > 0 ? '+' : '') + d.toFixed(2)}</b></div>
        <div class="kv"><small>Incidents</small><b>${inc}x</b></div>`;
      if (bar !== this.lastBar) { this.meBar.innerHTML = bar; this.lastBar = bar; }
    }
  },
};
