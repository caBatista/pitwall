import { esc, flagHtml, makeHtml, stHtml, talkHtml, OUT, flagFx, irHtml, pitHtml } from './util.js';

// lap time with one decimal: 211.827 -> 3:31.8
const lap1 = (x) => {
  const t = Math.round(x * 10) / 10, m = Math.floor(t / 60);
  return `${m}:${(t - m * 60).toFixed(1).padStart(4, '0')}`;
};

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
      </div>
      <div class="rel-body" id="rl-body"></div>`;
    this.body = root.querySelector('#rl-body');
    this.last = '';
    root.addEventListener('click', (e) => {
      const r = e.target.closest('.rrow[data-i]');
      if (r) { const i = Number(r.dataset.i); S.sel = S.sel === i ? null : i; this.last = ''; }
    });
  },

  update(S) {
    const st = S.st;
    if (!st) return;
    const n = 3;   // 3 ahead, 3 behind

    const cars = new Map(st.cars.map((c) => [c.i, c]));
    const ahead = st.rel.filter((r) => r.dt >= 0).slice(-n);   // nearest n ahead (list is far→near)
    const behind = st.rel.filter((r) => r.dt < 0).slice(0, n);

    // pos | # | make | flag | name [OUT][status] | SR | iRating | best lap | relative
    const cells = (i, d, extra) => {
      const c = cars.get(i) || {};
      const cls = S.classMap.get(d.cls) || { color: '#8b95a7' };
      const [lic, sr] = (d.lic || '').split(' ');
      // best lap (like RaceLab): the last one is -1 whenever iRacing invalidated it
      const best = c.best ? `<span class="t ${c.cb ? 'cb' : ''}">${lap1(c.best)}</span>` : '<span class="t dim">-:--.-</span>';
      return `<div class="rpos">${c.cp || '–'}</div>
        <div class="rcar" style="--cc:${cls.color}"><span class="rn">${esc(d.num)}</span><span class="mk">${makeHtml(d.make)}</span></div>
        ${flagHtml(d.country)}
        <div class="rname"><span class="nm">${esc(d.name)}</span>${extra}</div>
        <div class="sr" style="--lc:${d.licColor}">${lic ? `<b>${esc((sr || '').slice(0, 3))}</b><i>${esc(lic)}</i>` : ''}</div>
        <div class="irb">${irHtml(d.ir, c.irg)}</div>
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
      const c = cars.get(r.i) || r;
      return `<div class="rrow ${r.dl > 0 ? 'up' : r.dl < 0 ? 'down' : ''} ${r.pit ? 'pitrow' : ''} ${S.sel === r.i ? 'sel' : ''}" data-i="${r.i}">
        ${cells(r.i, d, (r.out ? OUT : lap) + pitHtml(c, st.session?.kind) + `<span class="fxw" style="${flagFx('r' + r.i, c.fl)}">${stHtml(c)}</span>` + talkHtml(st.talk === r.i))}<div class="rt ${side}">${txt}</div></div>`;
    };

    const md = S.drivers[st.me.i];
    const meRow = md ? `<div class="rrow me">${cells(st.me.i, md, (cars.get(st.me.i)?.out ? OUT : '') + pitHtml(cars.get(st.me.i), st.session?.kind) + `<span class="fxw" style="${flagFx('r' + st.me.i, cars.get(st.me.i)?.fl)}">${stHtml(cars.get(st.me.i) || {})}</span>` + talkHtml(st.talk === st.me.i))}<div class="rt">–</div></div>` : '<div class="rrow empty"></div>';

    // ahead is ordered far → near already; pad on top so the layout never jumps
    const a = [...Array(Math.max(0, n - ahead.length)).fill(null), ...ahead];
    const b = [...behind, ...Array(Math.max(0, n - behind.length)).fill(null)];
    const html = a.map((r) => row(r, 'ahead')).join('') + meRow + b.map((r) => row(r, 'behind')).join('');
    if (html !== this.last) { this.body.innerHTML = html; this.last = html; }
  },
};
