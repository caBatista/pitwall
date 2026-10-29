import { esc, prefs, savePrefs } from './util.js';

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
    this.hist = new Map();
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

    const now = st.t;
    const ahead = st.rel.filter((r) => r.dt >= 0).slice(-n);   // nearest n ahead (list is far→near)
    const behind = st.rel.filter((r) => r.dt < 0).slice(0, n);

    // closing rate over ~1.5 s, per car
    const rate = (r) => {
      let h = this.hist.get(r.i);
      if (!h) { h = []; this.hist.set(r.i, h); }
      h.push([now, Math.abs(r.dt)]);
      while (h.length > 2 && now - h[0][0] > 1.6) h.shift();
      const [t0, v0] = h[0];
      return now - t0 > 0.8 ? (Math.abs(r.dt) - v0) / (now - t0) : 0;
    };

    const row = (r, side) => {
      if (!r) return '<div class="rrow empty"></div>';
      const d = S.drivers[r.i];
      if (!d) return '<div class="rrow empty"></div>';
      const cls = S.classMap.get(d.cls) || { color: '#8b95a7', name: '' };
      const rt = rate(r);
      let arrow = '';
      if (rt < -0.12) arrow = side === 'behind' ? '<span class="cl" style="color:var(--red)">▲</span>' : '<span class="cl" style="color:var(--green)">▲</span>';
      else if (rt > 0.12) arrow = '<span class="cl" style="color:var(--mute)">▼</span>';
      const lap = r.dl > 0 ? `<span class="lapt up">+${r.dl}L</span>` : r.dl < 0 ? `<span class="lapt down">${r.dl}L</span>` : '';
      const tag = r.pit ? '<span class="tag">PIT</span>' : lap;
      const t = Math.abs(r.dt);
      const txt = (r.dt >= 0 ? '-' : '+') + (t < 10 ? t.toFixed(1) : t.toFixed(1));
      return `<div class="rrow ${r.dl > 0 ? 'up' : r.dl < 0 ? 'down' : ''} ${r.pit ? 'pitrow' : ''} ${S.sel === r.i ? 'sel' : ''}" data-i="${r.i}" style="--cc:${cls.color}">
        <div class="rt ${side}">${arrow}${txt}</div><div class="cbar"></div>
        <div class="rn">#${esc(d.num)}</div>
        <div class="rname">${esc(d.name)}</div>
        <div class="rir">${d.ir || ''}</div>
        <div class="rtag">${tag}</div></div>`;
    };

    const md = S.drivers[st.me.i];
    const mcls = md ? (S.classMap.get(md.cls) || { color: '#8b95a7' }) : { color: '#8b95a7' };
    const meRow = `<div class="rrow me" style="--cc:${mcls.color}">
      <div class="rt">YOU</div><div class="cbar"></div>
      <div class="rn">#${esc(md?.num ?? '')}</div>
      <div class="rname">${esc(md?.name ?? '')}</div>
      <div class="rir">${md?.ir || ''}</div>
      <div class="rtag">${st.me.pit ? '<span class="tag">PIT</span>' : ''}</div></div>`;

    // ahead is ordered far → near already; pad on top so the layout never jumps
    const a = [...Array(Math.max(0, n - ahead.length)).fill(null), ...ahead];
    const b = [...behind, ...Array(Math.max(0, n - behind.length)).fill(null)];
    const html = a.map((r) => row(r, 'ahead')).join('') + meRow + b.map((r) => row(r, 'behind')).join('');
    if (html !== this.last) { this.body.innerHTML = html; this.last = html; }
    if (this.hist.size > 80) this.hist.clear();
  },
};
