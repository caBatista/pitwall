import { esc, prefs, savePrefs } from './util.js';
import { CLASS_HEAD, FOOT, STAND, classDefault, footDefault, standDefault } from './columns.js';
import { SESSIONS } from './layout.js';
import { listEditor, sessionHead } from './set-list.js';

const section = (id, title, hint) => `
  <section class="st-sec">
    <div class="st-sec-h"><h2>${title}</h2><button class="st-link" data-reset="${id}">Reset</button></div>
    ${id === 'cols' ? '<div class="fit" id="fit"></div>' : ''}
    <div class="col-top"><span>${hint}</span>${sessionHead()}</div>
    <ul class="col-list" id="list-${id}"></ul>
  </section>`;

/** What the board says fits: it knows the panel, the page knows what was asked for. */
function fitBox(el) {
  let f = null;
  try { f = JSON.parse(localStorage.getItem('pitwall.fit')); } catch { /* ignore */ }
  if (!f?.room) { el.hidden = true; return; }
  el.hidden = false;
  const name = SESSIONS.find(([s]) => s === f.session)?.[1] ?? f.session;
  const over = f.need > f.room, full = Math.min(100, (100 * f.need) / f.room);
  el.className = `fit${over ? ' over' : ''}`;
  el.innerHTML = `
    <div class="fit-h"><span>Width in ${esc(name)}</span><b>${f.need} of ${f.room} px</b></div>
    <div class="fit-bar"><i style="width:${full}%"></i></div>
    ${f.cols.length || f.foot.length ? `<p>Not showing, no room: ${esc([...f.cols, ...f.foot].join(', '))}. Turn something off or make the widget bigger in Layout.</p>` : ''}`;
}

export function standingsPage(root) {
  root.insertAdjacentHTML('beforeend',
    section('cols', 'Columns', 'Drag to reorder, the boxes choose the sessions.')
    + section('class', 'Class header', 'After the class name.')
    + section('foot', 'Footer', 'Drag to reorder, the boxes choose the sessions.'));
  const resets = {
    cols: listEditor(root.querySelector('#list-cols'), () => prefs.stand, STAND, () => { prefs.stand = standDefault(); }),
    class: listEditor(root.querySelector('#list-class'), () => prefs.classHead, CLASS_HEAD, () => { prefs.classHead = classDefault(); }),
    foot: listEditor(root.querySelector('#list-foot'), () => prefs.standFoot, FOOT, () => { prefs.standFoot = footDefault(); }),
  };
  root.addEventListener('click', (e) => { const r = e.target.closest('[data-reset]')?.dataset.reset; if (r) resets[r](); });
  const fit = root.querySelector('#fit');
  fitBox(fit);
  const shown = root.dataset.shown;
  addEventListener('storage', (e) => { if (e.key === 'pitwall.fit' && root.dataset.shown === shown) fitBox(fit); });

}
