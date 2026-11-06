import { esc, flagHtml, makeHtml, stHtml, talkHtml, OUT, flagFx, irHtml, pitHtml, fitIr, irKeyOf, INV, patchRows } from './util.js';
import { driverActions } from './drivers.js';

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
    driverActions(root, S);
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
      // best lap (like RaceLab); * = their latest lap was invalidated / had an incident
      const best = c.best ? `<span class="t ${c.cb ? 'cb' : ''}">${lap1(c.best)}${c.lastx ? INV : ''}</span>` : `<span class="t dim">-:--.-${c.lastx ? INV : ''}</span>`;
      return [
        ['spos', `<span class="sp">${c.cp || '–'}</span>`, `--cc:${cls.color}`],
        ['sn', esc(d.num)],
        ['mk', makeHtml(d.make)],
        ['fc', flagHtml(d.country)],
        ['rname', `<span class="nm">${esc(d.name)}</span>${extra}`],
        ['sr', lic ? `<b>${esc((sr || '').slice(0, 3))}</b><i>${esc(lic)}</i>` : '', `--lc:${d.licColor}`],
        ['irb', irHtml(d.ir, c.irg, st.session?.kind === 'race')],
        ['rlast', best],
      ];
    };

    // slots of the panel, top to bottom: a slot with no car keeps its height
    const empty = (slot) => ({ key: 'e' + slot, cls: 'rrow empty', cells: [] });
    const row = (r, side, slot) => {
      const d = r && S.drivers[r.i];
      if (!d) return empty(slot);
      const lap = r.dl > 0 ? `<span class="lapt up">+${r.dl}L</span>` : r.dl < 0 ? `<span class="lapt down">${r.dl}L</span>` : '';
      const t = Math.abs(r.dt);
      // no sign: the row order already says ahead/behind; 92.0 -> 1:32.0
      const tr = Math.round(t * 10) / 10;   // round first so 119.97 is 2:00.0, not 1:60.0
      const txt = tr >= 60 ? `${Math.floor(tr / 60)}:${(tr % 60).toFixed(1).padStart(4, '0')}` : tr.toFixed(1);
      const c = cars.get(r.i) || r;
      const extra = (r.out ? OUT : lap) + pitHtml(c, st.session?.kind) + `<span class="fxw" style="${flagFx('r' + r.i, c.fl)}">${stHtml(c)}</span>` + talkHtml(st.talk === r.i);
      return { key: r.i, i: r.i, cls: `rrow ${r.dl > 0 ? 'up' : r.dl < 0 ? 'down' : ''} ${r.pit ? 'pitrow' : ''}`, cells: [...cells(r.i, d, extra), [`rt ${side}`, txt]] };
    };

    const md = S.drivers[st.me.i], mine = cars.get(st.me.i);
    const meRow = md ? { key: 'me', i: st.me.i, cls: 'rrow me', cells: [...cells(st.me.i, md, (mine?.out ? OUT : '') + pitHtml(mine, st.session?.kind) + `<span class="fxw" style="${flagFx('r' + st.me.i, mine?.fl)}">${stHtml(mine || {})}</span>` + talkHtml(st.talk === st.me.i)), ['rt', '–']] } : empty('m');

    // ahead is ordered far → near already; pad on top so the layout never jumps
    const a = [...Array(Math.max(0, n - ahead.length)).fill(null), ...ahead];
    const b = [...behind, ...Array(Math.max(0, n - behind.length)).fill(null)];
    patchRows(this.body, [...a.map((r, k) => row(r, 'ahead', 'a' + k)), meRow, ...b.map((r, k) => row(r, 'behind', 'b' + k))]);
    // the standings sizes the iRating chips (it has every driver); alone, the relative does
    if (!document.querySelector('#w-standings .irb')) fitIr(this.body, irKeyOf(S, st.cars));
  },
};
