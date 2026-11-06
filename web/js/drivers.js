import { esc } from './util.js';

/**
 * What a driver row does, in the standings and the relative alike:
 * click = make them the reference driver (iRacing's camera, so everything follows through CamCarIdx);
 * right click = menu to message them, which opens the chat in the sim with the target typed in.
 */
let menu = null;

function close() {
  menu?.remove();
  menu = null;
}

/** before: what to do first, when an item is picked. */
export function driverMenu(e, S, i, before) {
  close();
  const d = S.drivers[i];
  if (!d) return;
  const items = [['driver', `Message ${esc(d.name)}`], ['car', `Message car #${esc(d.num)}`]];
  if (d.team) items.push(['team', `Message ${esc(d.team)}`]);
  menu = document.createElement('div');
  menu.className = 'ctx';
  menu.innerHTML = items.map(([to, label]) => `<button data-to="${to}">${label}</button>`).join('');
  menu.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-to]');
    if (b) { const wait = before?.() ? 200 : 0; setTimeout(() => S.send({ cmd: 'chat', i, to: b.dataset.to }), wait); }
    close();
  });
  document.body.appendChild(menu);
  // the body is zoomed, so the menu's own px are too: place it through its parent's scale
  const z = document.body.getBoundingClientRect().width / document.body.offsetWidth || 1;
  const m = menu.getBoundingClientRect();
  menu.style.left = `${Math.min(e.clientX, innerWidth - m.width - 4) / z}px`;
  menu.style.top = `${Math.min(e.clientY, innerHeight - m.height - 4) / z}px`;
}

export function driverActions(root, S) {
  root.addEventListener('click', (e) => {
    const r = e.target.closest('.rrow[data-i]');
    if (r) S.send({ cmd: 'focus', i: Number(r.dataset.i) });
  });
  root.addEventListener('contextmenu', (e) => {
    const r = e.target.closest('.rrow[data-i]');
    if (!r) return;
    e.preventDefault();
    driverMenu(e, S, Number(r.dataset.i));
  });
}

addEventListener('pointerdown', (e) => { if (menu && !menu.contains(e.target)) close(); });
addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
addEventListener('blur', close);
