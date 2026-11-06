import { prefs, animOn } from './util.js';

/**
 * A position change on a board (Standings, Relative): the block of each driver travels from the old place to the
 * new one, so one goes up as the other goes down. Nothing here costs anything between changes: the rows are read
 * only when a position changed, and the movement is a transform, on the compositor, only while it plays.
 *   slide:  both glide, straight
 *   lift:   whoever gained comes over the other, in front and lit, the other passes underneath
 *   spring: both overshoot and settle
 * More than MANY gains in one frame is not a fight (a stop, the start): nothing moves. A pair side by side trading
 * places every frame moves once per REPEAT.
 */
const MANY = 6, REPEAT = 1500;
const EASE = { slide: [340, 'cubic-bezier(.2,.7,.2,1)'], lift: [420, 'cubic-bezier(.3,.6,.2,1)'], spring: [460, 'cubic-bezier(.3,1.5,.5,1)'] };

function play(row, from, kind, up) {
  const lifted = kind === 'lift' && up;
  const start = { transform: `translateY(${from}px)${lifted ? ' scale(1.012)' : ''}`, zIndex: up ? 3 : 2 };
  if (lifted) start.boxShadow = '0 0 16px 2px rgba(255, 255, 255, .4)';
  row.animate([start, { transform: 'none', zIndex: up ? 3 : 2, ...(lifted ? { boxShadow: '0 0 0 0 rgba(255, 255, 255, 0)' } : {}) }], { duration: EASE[kind][0], easing: EASE[kind][1] });
}

export function posFx(body) {
  const seen = new Map(), last = new Map();
  let tops = null, gains = new Set(), moved = [], kind = 'off', test = 0, swap = null, previewed = prefs.posFx;

  const rowsOf = () => [...body.children].filter((r) => r.dataset.i != null);

  return {
    /** Before the rows change: who moved, and where they are now. */
    before(cars) {
      const want = prefs.posFx ?? 'slide';
      kind = animOn() && !document.body.dataset.over && !document.body.hasAttribute('data-static') ? want : 'off';
      gains = new Set(); moved = []; tops = null; swap = null;
      if (!EASE[kind]) { seen.clear(); previewed = prefs.posFx; return; }
      const now = performance.now();
      for (const c of cars) {
        const was = seen.get(c.i);
        seen.set(c.i, c.cp);
        if (c.cp == null || was == null || c.cp === was) continue;
        moved.push(c.i);
        if (c.cp < was && !c.pit) gains.add(c.i);
      }
      if (gains.size > MANY || !moved.length || [...gains].every((i) => now - (last.get(i) ?? -1e9) < REPEAT)) moved = [];
      for (const i of gains) last.set(i, now);
      if (moved.length) tops = new Map(rowsOf().map((r) => [Number(r.dataset.i), r.offsetTop]));
      const every = prefs.posFxBench;   // only tools/bench_cpu.py: this many ms between swaps
      if ((every && now - test >= every) || previewed !== prefs.posFx) {
        previewed = prefs.posFx;   // picked another one in Settings: it shows
        test = now;
        const rows = rowsOf(), k = 1 + Math.floor(Math.random() * (rows.length - 1));
        if (rows[k]) swap = [rows[k], rows[k - 1]];
      }
    },

    /** After: plays it. */
    after() {
      if (swap) {
        const [a, b] = swap, h = a.offsetTop - b.offsetTop;
        play(a, h, kind, true);
        play(b, -h, kind, false);
      }
      if (!tops) return;
      const rows = new Map(rowsOf().map((r) => [Number(r.dataset.i), r]));
      for (const i of moved) {
        const r = rows.get(i), was = tops.get(i), now = r?.offsetTop;
        if (was != null && r && was !== now) play(r, was - now, kind, gains.has(i));
      }
    },
  };
}
