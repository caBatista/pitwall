import { esc, prefs, savePrefs, lapTime, flagHtml, makeHtml } from './util.js';

// status chip after the name (and after OUT): the most serious flag wins
const ST = {
  dq: '<span class="st dq">DQ</span>',
  black: '<span class="st black" title="Black flag"><i></i></span>',
  repair: '<span class="st repair" title="Meatball (repair)"><i></i></span>',
  warn: '<span class="st warn" title="Warning"><i></i></span>',
  pit: '<span class="st pit">PIT</span>',
};
const stHtml = (c) => ST[c.fl] || (c.pit ? ST.pit : '');
const FAST = '<i class="fast" title="Fastest lap in class"></i>';
const OUT = '<span class="tag out">OUT</span>';

/**
 * Relative: everybody near you on track, ordered by track position, with the
 * real time between you (measured at the same point of the track, so it is
 * correct across classes). Colour tells you about laps, not about class:
 *   red  = a lap (or more) ahead of you, they will lap you
 *   blue = a lap (or more) behind you, you are lapping them
 * The class colour is the bar on the left.
 */
export const relative = {
  id: 'w-relative',
  mount(root, S) {
    root.innerHTML = `
      <div class="card-h">
        <div class="ttl"><i></i>Relative</div>
        <div class="ctl"><div class="seg" id="rl-rows">
          ${[3, 4, 5, 6].map((n) => `<button data-n="${n}">${n}</button>`).join('')}</div></div>
      </div>
      <div class="rel-body" id="rl-body"></div>`;
    this.body = root.querySelector('#rl-body');
    this.rows = root.querySelector('#rl-rows');
    this.last = '';
    root.addEventListener('click', (e) => {
      const b = e.target.closest('[data-n]');
      if (b) { prefs.relRows = Number(b.dataset.n); savePrefs(); this.last = ''; return; }
      const r = e.target.closest('.rrow[data-i]');
      if (r) { const i = Number(r.dataset.i); S.sel = S.sel === i ? null : i; this.last = ''; }
    });
  },

  update(S) {
    const st = S.st;
    if (!st) return;
    const n = prefs.relRows;
    this.rows.querySelectorAll('button').forEach((b) => b.classList.toggle('on', Number(b.dataset.n) === n));

    const cars = new Map(st.cars.map((c) => [c.i, c]));
    const ahead = st.rel.filter((r) => r.dt >= 0).slice(-n);   // nearest n ahead (list is far→near)
    const behind = st.rel.filter((r) => r.dt < 0).slice(0, n);

    // pos | # | make | flag | name [OUT][status] | SR | iRating | best lap | relative
    const cells = (i, d, extra) => {
      const c = cars.get(i) || {};
      const cls = S.classMap.get(d.cls) || { color: '#8b95a7' };
      const [lic, sr] = (d.lic || '').split(' ');
      // best lap (like RaceLab): the last one is -1 whenever iRacing invalidated it
      const best = c.best ? `<span class="t ${c.cb ? 'cb' : ''}">${lapTime(c.best)}</span>${c.cb ? FAST : ''}` : '<span class="t dim">-:--.---</span>';
      return `<div class="rpos">${c.cp || '–'}</div>
        <div class="rcar" style="--cc:${cls.color}"><span class="rn">${esc(d.num)}</span><span class="mk">${makeHtml(d.make)}</span></div>
        ${flagHtml(d.country)}
        <div class="rname"><span class="nm">${esc(d.name)}</span>${extra}</div>
        <div class="sr" style="--lc:${d.licColor}">${lic ? `<b>${esc((sr || '').slice(0, 3))}</b><i>${esc(lic)}</i>` : ''}</div>
        <div class="irb">${d.ir ? `<b>${d.ir >= 1000 ? (d.ir / 1000).toFixed(1) + 'k' : d.ir}</b>` : ''}</div>
        <div class="rlast">${best}</div>`;
    };

    const row = (r, side) => {
      if (!r) return '<div class="rrow empty"></div>';
      const d = S.drivers[r.i];
      if (!d) return '<div class="rrow empty"></div>';
      const lap = r.dl > 0 ? `<span class="lapt up">+${r.dl}L</span>` : r.dl < 0 ? `<span class="lapt down">${r.dl}L</span>` : '';
      const t = Math.abs(r.dt);
      // no sign: the row order already says ahead/behind; 92.0 -> 1:32.0
      const tr = Math.round(t * 10) / 10;   // round first so 119.97 is 2:00.0, not 1:60.0
      const txt = tr >= 60 ? `${Math.floor(tr / 60)}:${(tr % 60).toFixed(1).padStart(4, '0')}` : tr.toFixed(1);
      return `<div class="rrow ${r.dl > 0 ? 'up' : r.dl < 0 ? 'down' : ''} ${r.pit ? 'pitrow' : ''} ${S.sel === r.i ? 'sel' : ''}" data-i="${r.i}">
        ${cells(r.i, d, (r.out ? OUT : lap) + stHtml(cars.get(r.i) || r))}<div class="rt ${side}">${txt}</div></div>`;
    };

    const md = S.drivers[st.me.i];
    const meRow = md ? `<div class="rrow me">${cells(st.me.i, md, (cars.get(st.me.i)?.out ? OUT : '') + stHtml(cars.get(st.me.i) || {}))}<div class="rt">–</div></div>` : '<div class="rrow empty"></div>';

    // ahead is ordered far → near already; pad on top so the layout never jumps
    const a = [...Array(Math.max(0, n - ahead.length)).fill(null), ...ahead];
    const b = [...behind, ...Array(Math.max(0, n - behind.length)).fill(null)];
    const html = a.map((r) => row(r, 'ahead')).join('') + meRow + b.map((r) => row(r, 'behind')).join('');
    if (html !== this.last) { this.body.innerHTML = html; this.last = html; }
  },
};
