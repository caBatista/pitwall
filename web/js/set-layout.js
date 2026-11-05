import { esc, prefs, savePrefs } from './util.js';
import { SESSIONS, WIDGETS, addItem, clearLayout, gridOf, layoutFor, moveItem, resizeItem, saveLayout, shapeOf } from './layout.js';
import { currentScreen } from './set-screen.js';

const pct = (v, of) => `${(100 * v) / of}%`;

/** The session the board is in, told by main.js. */
const live = () => { try { return localStorage.getItem('pitwall.session'); } catch { return null; } };

export async function layoutPage(root) {
  const shown = root.dataset.shown;
  const scr = await currentScreen();
  if (root.dataset.shown !== shown) return;   // left the page meanwhile
  const shape = shapeOf(scr.w, scr.h), { cols, rows } = gridOf(shape);
  const place = (el, i) => {
    el.style.left = pct(i.x, cols); el.style.top = pct(i.y, rows);
    el.style.width = pct(i.w, cols); el.style.height = pct(i.h, rows);
  };
  root.insertAdjacentHTML('beforeend', `
    <section class="st-sec">
      <div class="st-sec-h"><div class="seg" id="ly-tabs">${SESSIONS.map(([k, n]) => `<button data-s="${k}">${n}</button>`).join('')}</div><button class="st-link" data-reset>Reset</button></div>
      <div class="ly-board" id="ly-board"></div>
      <div class="ly-tray" id="ly-tray"></div>
    </section>`);
  const tabs = root.querySelector('#ly-tabs'), board = root.querySelector('#ly-board'), tray = root.querySelector('#ly-tray');
  board.style.aspectRatio = `${scr.w} / ${scr.h}`;
  board.classList.toggle('tall', shape === 'portrait');
  let session = SESSIONS.some(([k]) => k === live()) ? live() : 'race';
  let items = [], drag = null;

  const save = () => { saveLayout(prefs.layout ??= {}, session, shape, items); savePrefs(); };

  function paint() {
    for (const i of items) place(board.querySelector(`[data-id="${i.id}"]`), i);
  }
  function draw() {
    for (const b of tabs.children) b.classList.toggle('on', b.dataset.s === session);
    board.innerHTML = items.map((i) => `<div class="ly-tile" data-id="${i.id}">
        <button class="ly-rm" data-rm title="Remove" aria-label="Remove ${esc(WIDGETS[i.id].name)}"></button>
        <b>${esc(WIDGETS[i.id].name)}</b>
        <span class="ly-rz" title="Drag to resize"></span>
      </div>`).join('');
    paint();
    const out = Object.keys(WIDGETS).filter((id) => !items.some((i) => i.id === id));
    tray.innerHTML = out.length
      ? out.map((id) => `<button data-add="${id}" ${addItem(items, id, shape) ? '' : 'disabled title="No room left"'}>${esc(WIDGETS[id].name)}</button>`).join('')
      : '<small>All widgets are on the board</small>';
  }
  function open(s) {
    session = s;
    items = layoutFor(prefs.layout, s, shape);
    draw();
  }

  tabs.addEventListener('click', (e) => { const s = e.target.closest('[data-s]')?.dataset.s; if (s) open(s); });
  tray.addEventListener('click', (e) => {
    const id = e.target.closest('[data-add]')?.dataset.add, next = id && addItem(items, id, shape);
    if (next) { items = next; save(); draw(); }
  });
  root.querySelector('[data-reset]').addEventListener('click', () => {
    clearLayout(prefs.layout, session, shape);
    savePrefs(); open(session);
  });
  board.addEventListener('click', (e) => {
    const b = e.target.closest('[data-rm]');
    if (b) { items = items.filter((i) => i.id !== b.parentElement.dataset.id); save(); draw(); }
  });

  // Moving: the tile follows the pointer, a dashed place shows where it lands and the others make room.
  // Always worked out from the board as it was when the drag began: move away and they come back.
  board.addEventListener('pointerdown', (e) => {
    const t = e.target.closest('.ly-tile');
    if (!t || e.target.closest('[data-rm]')) return;
    const b = board.getBoundingClientRect(), from = items.find((i) => i.id === t.dataset.id);
    const ghost = document.createElement('div');
    ghost.className = 'ly-ghost';
    place(ghost, from);
    board.appendChild(ghost);
    t.classList.add('held');
    drag = { t, ghost, from, base: items, x: e.clientX, y: e.clientY, cw: b.width / cols, ch: b.height / rows, size: !!e.target.closest('.ly-rz') };
    board.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  board.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const { t, ghost, from, base, cw, ch, size } = drag;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    const next = size
      ? resizeItem(base, from.id, from.w + Math.round(dx / cw), from.h + Math.round(dy / ch), shape)
      : moveItem(base, from.id, from.x + Math.round(dx / cw), from.y + Math.round(dy / ch), shape);
    if (next) { items = next; paint(); }
    const cur = items.find((i) => i.id === from.id);
    place(ghost, cur);
    if (!size) t.style.transform = `translate(${dx - (cur.x - from.x) * cw}px, ${dy - (cur.y - from.y) * ch}px)`;
  });
  const drop = () => {
    if (!drag) return;
    const changed = JSON.stringify(items) !== JSON.stringify(drag.base);
    drag.ghost.remove();
    drag.t.classList.remove('held');
    drag.t.style.transform = '';
    drag = null;
    if (changed) save();
    draw();
  };
  board.addEventListener('pointerup', drop);
  board.addEventListener('pointercancel', drop);

  // the session changed on the board (the simulator's selector, or the race went on): follow it
  addEventListener('storage', (e) => {
    if (e.key === 'pitwall.session' && e.newValue && !drag && root.dataset.shown === shown && SESSIONS.some(([k]) => k === e.newValue)) open(e.newValue);
  });

  open(session);
}
