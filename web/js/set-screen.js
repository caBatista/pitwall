import { esc } from './util.js';
import { shapeOf } from './layout.js';

/** The app's API; in a browser it never comes. */
export function desktop() {
  if (window.pywebview?.api?.screens) return Promise.resolve(window.pywebview.api);
  return new Promise((done) => {
    addEventListener('pywebviewready', () => done(window.pywebview.api), { once: true });
    setTimeout(() => done(null), 600);
  });
}

async function monitors() {
  const api = await desktop();
  return { api, list: api ? await api.screens() : null };
}

/** The screen the layouts are made for: the one picked in the app, this one in a browser. */
export async function currentScreen() {
  const { list } = await monitors();
  const s = list?.find((m) => m.on) ?? list?.[0];
  if (s) return s;
  const board = window.opener;   // a browser: the window of the board, if this pop-up came from it
  return board?.innerWidth ? { w: board.innerWidth, h: board.innerHeight } : { w: screen.width, h: screen.height };
}

const SHAPE = { landscape: 'Landscape', portrait: 'Portrait' };

function ratio(w, h) {
  const r = Math.max(w, h) / Math.min(w, h);
  return r > 2 ? 'Ultrawide' : SHAPE[shapeOf(w, h)];
}

export async function screenPage(root) {
  const shown = root.dataset.shown;
  const { api, list: first } = await monitors();
  if (root.dataset.shown !== shown) return;   // left the page meanwhile
  if (!api) {
    root.insertAdjacentHTML('beforeend', `<section class="st-sec"><div class="st-none">Pitwall fills this browser window: ${screen.width} × ${screen.height}</div></section>`);
    return;
  }
  root.insertAdjacentHTML('beforeend', '<section class="st-sec"><div class="sc-desk" id="sc-desk"></div><div class="sc-note" id="sc-note"></div></section>');
  const desk = root.querySelector('#sc-desk'), note = root.querySelector('#sc-note');

  function draw(list) {
    // the monitors as they sit on the desk, to scale
    const x0 = Math.min(...list.map((m) => m.x)), y0 = Math.min(...list.map((m) => m.y));
    const W = Math.max(...list.map((m) => m.x + m.w)) - x0, H = Math.max(...list.map((m) => m.y + m.h)) - y0;
    desk.style.aspectRatio = `${W} / ${H}`;
    desk.innerHTML = list.map((m, i) => `<button class="sc-mon${m.on ? ' on' : ''}" data-i="${i}" style="left:${(100 * (m.x - x0)) / W}%;top:${(100 * (m.y - y0)) / H}%;width:${(100 * m.w) / W}%;height:${(100 * m.h) / H}%">
        <b>${i + 1}</b><span>${m.w} × ${m.h}</span><small>${ratio(m.w, m.h)}${m.primary ? ' · Primary' : ''}</small>
      </button>`).join('');
    const on = list.find((m) => m.on);
    note.textContent = on ? `Layouts are edited for this ${esc(SHAPE[shapeOf(on.w, on.h)].toLowerCase())} screen. Landscape and portrait keep separate layouts.` : 'Pick the screen for Pitwall.';
  }
  desk.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-i]');
    if (b && !b.classList.contains('on')) draw(await api.set_screen(Number(b.dataset.i)));
  });
  draw(first);
}
