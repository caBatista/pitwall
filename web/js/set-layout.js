import { esc, prefs, savePrefs } from './util.js';
import { SESSIONS, WIDGETS, addItem, clearLayout, fixedAnchor, gridOf, layoutFor, moveItem, resizeItem, saveLayout, shapeOf, widgetsFor } from './layout.js';
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
    // as on the board: the rows of a fixed widget take its height, the others share the rest
    const f = items.find((o) => WIDGETS[o.id].px), part = f ? (WIDGETS[f.id].px[1] * (prefs.zoom ?? 1.1)) / scr.h : 0;
    const at = (r) => (f ? (Math.min(r, f.y) + Math.max(0, r - f.y - f.h)) * ((1 - part) / (rows - f.h)) + part * Math.max(0, Math.min(r - f.y, f.h)) / f.h : r / rows);
    el.style.left = pct(i.x, cols); el.style.top = `${100 * at(i.y)}%`;
    el.style.width = pct(i.w, cols); el.style.height = `${100 * (at(i.y + i.h) - at(i.y))}%`;
    const px = WIDGETS[i.id]?.px;
    if (px) {   // a fixed widget at its true size on this screen, where the board puts it in its cells
      const w = px[0] ? (100 * px[0] * (prefs.zoom ?? 1.1)) / scr.w : (100 * i.w) / cols;
      el.style.width = `${w}%`;
      if (fixedAnchor(i, { cols, rows }).right) el.style.left = `${100 - w}%`;
    }
  };
  root.insertAdjacentHTML('beforeend', `
    <section class="st-sec">
      <div class="st-sec-h"><div class="seg" id="ly-tabs">${SESSIONS.map(([k, n]) => `<button data-s="${k}">${n}</button>`).join('')}</div>
        <div class="seg" id="ly-where"><button data-w="">In car</button><button data-w=":out">Out of car</button></div>
        <button class="st-link" data-reset>Reset</button></div>
      <div class="ly-board" id="ly-board"></div>
      <div class="ly-tray" id="ly-tray"></div>
    </section>`);
  const tabs = root.querySelector('#ly-tabs'), where = root.querySelector('#ly-where'), board = root.querySelector('#ly-board'), tray = root.querySelector('#ly-tray');
  board.style.aspectRatio = `${scr.w} / ${scr.h}`;
  board.classList.toggle('tall', shape === 'portrait');
  const known = (s) => SESSIONS.some(([k]) => k === s?.split(':')[0]);
  let session = known(live()) ? live() : 'race';
  let items = [], drag = null;

  const save = () => { saveLayout(prefs.layout ??= {}, session, shape, items); savePrefs(); };

  function paint() {
    for (const i of items) place(board.querySelector(`[data-id="${i.id}"]`), i);
  }
  function draw() {
    const [tab, out] = session.split(':');
    for (const b of tabs.children) b.classList.toggle('on', b.dataset.s === tab);
    where.hidden = tab === 'over';
    for (const b of where.children) b.classList.toggle('on', b.dataset.w === (out ? ':out' : ''));
    board.innerHTML = items.map((i) => `<div class="ly-tile" data-id="${i.id}">
        <button class="ly-rm" data-rm title="Remove" aria-label="Remove ${esc(WIDGETS[i.id].name)}"></button>
        <b>${esc(WIDGETS[i.id].name)}</b>
        ${WIDGETS[i.id].px ? '' : '<span class="ly-rz" title="Drag to resize"></span>'}
      </div>`).join('');
    paint();
    const free = widgetsFor(session).filter((id) => !items.some((i) => i.id === id));
    tray.innerHTML = free.length
      ? free.map((id) => `<button data-add="${id}" ${addItem(items, id, shape) ? '' : 'disabled title="No room left"'}>${esc(WIDGETS[id].name)}</button>`).join('')
      : '<small>All widgets are on the board</small>';
  }
  function open(s) {
    session = s;
    items = layoutFor(prefs.layout, s, shape);
    draw();
  }

  tabs.addEventListener('click', (e) => {   // keeps in car / out of car
    const s = e.target.closest('[data-s]')?.dataset.s;
    if (s) open(s === 'over' ? s : s + (session.endsWith(':out') ? ':out' : ''));
  });
  where.addEventListener('click', (e) => {
    const w = e.target.closest('[data-w]')?.dataset.w;
    if (w != null) open(session.split(':')[0] + w);
  });
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
    if (e.key === 'pitwall.session' && e.newValue && !drag && root.dataset.shown === shown && known(e.newValue)) open(e.newValue);
  });

  open(session);
}
