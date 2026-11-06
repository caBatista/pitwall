import { esc, savePrefs } from './util.js';
import { hiddenIn, optOf, orderOf } from './columns.js';
import { SESSIONS } from './layout.js';

const GRIP = '<svg viewBox="0 0 10 14" aria-hidden="true"><g fill="currentColor"><circle cx="3" cy="3" r="1.2"/><circle cx="7" cy="3" r="1.2"/><circle cx="3" cy="7" r="1.2"/><circle cx="7" cy="7" r="1.2"/><circle cx="3" cy="11" r="1.2"/><circle cx="7" cy="11" r="1.2"/></g></svg>';
const ARROW = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M3.5 2 7 5 3.5 8" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const SHORT = { test: 'Test', practice: 'Prac', qualify: 'Qual', race: 'Race', over: 'Over' };
const LIST = SESSIONS.filter(([s]) => s !== 'out');   // the garage is a screen of its own in the Layout, not a session for the lists

/** The titles over the session boxes. */
export const sessionHead = () => `<span class="col-s">${LIST.map(([s, n]) => `<small title="${esc(n)}">${SHORT[s]}</small>`).join('')}</span>`;

function optionHtml(cfg, table, k, o) {
  const v = optOf(cfg, table, k, o.k);
  const field = o.type === 'bool'
    ? `<label class="st-sw"><input type="checkbox" data-opt="${o.k}" ${v ? 'checked' : ''} aria-label="${esc(o.label)}"><i></i></label>`
    : o.type === 'select'
      ? `<select data-opt="${o.k}" data-pick aria-label="${esc(o.label)}">${o.values.map(([x, n]) => `<option value="${esc(x)}" ${x === v ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select>`
    : o.type === 'seg'
      ? `<div class="seg">${o.values.map(([x, n]) => `<button data-opt="${o.k}" data-val="${esc(x)}" class="${x === v ? 'on' : ''}">${esc(n)}</button>`).join('')}</div>`
      : `<div class="col-multi">${o.values.map(([x, n]) => `<label><input type="checkbox" data-opt="${o.k}" data-val="${esc(x)}" ${v.includes(x) ? 'checked' : ''}>${esc(n)}</label>`).join('')}</div>`;
  return `<div class="col-opt"><span>${esc(o.label)}</span>${field}</div>`;
}

function rowHtml(cfg, table, k, open) {
  const c = table[k];
  const on = c.fixed || LIST.some(([s]) => !hiddenIn(cfg, table, k, s));
  const has = !!c.opts?.length, show = has && open.has(k);
  return `<li class="col-row${on ? '' : ' off'}${show ? ' open' : ''}${c.child ? ' child' : ''}" data-k="${k}">
    <div class="col-main">
      ${c.child ? '<span class="col-h none"></span>' : `<span class="col-h" title="Drag to reorder">${GRIP}</span>`}
      <label class="st-sw"><input type="checkbox" data-all ${on ? 'checked' : ''} ${c.fixed ? 'disabled' : ''} aria-label="${esc(c.label)}"><i></i></label>
      <span class="col-n">${esc(c.label)}${c.fixed ? '<small>Always on</small>' : ''}${c.note ? `<em>${esc(c.note)}</em>` : ''}</span>
      ${has ? `<button class="col-x" data-open title="Options" aria-label="${esc(c.label)} options" aria-expanded="${show}">${ARROW}</button>` : ''}
      <span class="col-s">${LIST.map(([s, name]) => `<input type="checkbox" data-s="${s}" ${hiddenIn(cfg, table, k, s) ? '' : 'checked'} ${c.fixed ? 'disabled' : ''} aria-label="${esc(c.label)}: ${name}">`).join('')}</span>
    </div>
    ${show ? `<div class="col-opts">${c.opts.map((o) => optionHtml(cfg, table, k, o)).join('')}</div>` : ''}
  </li>`;
}

/** Drag by the handle. The other rows move, not this one: moving it would drop the pointer capture. */
function draggable(list, onOrder, onDrop) {
  let cur = null;
  list.addEventListener('pointerdown', (e) => {
    if (!e.target.closest('.col-h:not(.none)')) return;
    cur = e.target.closest('.col-row');
    cur.setPointerCapture(e.pointerId);
    cur.classList.add('drag');
    e.preventDefault();
  });
  list.addEventListener('pointermove', (e) => {
    if (!cur) return;
    const mid = (r) => { const b = r.getBoundingClientRect(); return b.top + b.height / 2; };
    const was = cur.previousElementSibling;
    let r;
    while ((r = cur.previousElementSibling) && e.clientY < mid(r)) list.insertBefore(r, cur.nextElementSibling);
    while ((r = cur.nextElementSibling) && e.clientY > mid(r)) list.insertBefore(r, cur);
    if (cur.previousElementSibling !== was) onOrder([...list.children].map((x) => x.dataset.k));
  });
  const end = () => { if (cur) onDrop(); cur = null; };
  list.addEventListener('pointerup', end);
  list.addEventListener('pointercancel', end);
}

/**
 * The editor of a list: on/off, order, the sessions, and the options behind the arrow.
 * cfg() gives the list as it is now (it is replaced by Reset), onReset puts the default back.
 */
export function listEditor(list, cfg, table, onReset) {
  const open = new Set();
  // an entry's children are part of what its arrow opens
  const draw = () => {
    const c = cfg();
    list.innerHTML = orderOf(c, table).filter((k) => !table[k].child || open.has(table[k].child)).map((k) => rowHtml(c, table, k, open)).join('');
  };
  const sessions = LIST.map(([s]) => s);
  draw();
  draggable(list, (order) => { cfg().order = order; savePrefs(); }, draw);   // draw: an entry's children go back under it

  list.addEventListener('change', (e) => {
    const t = e.target, k = t.closest('.col-row').dataset.k, c = cfg();
    c.hide ??= {};
    if ('all' in t.dataset) c.hide[k] = t.checked ? [] : sessions;
    else if (t.dataset.s) c.hide[k] = t.checked ? (c.hide[k] ?? []).filter((x) => x !== t.dataset.s) : [...(c.hide[k] ?? []), t.dataset.s];
    else if (t.dataset.opt) {
      const o = (c.opt ??= {})[k] ??= {}, name = t.dataset.opt;
      if ('pick' in t.dataset) o[name] = t.value;
      else if (t.dataset.val == null) o[name] = t.checked;
      else {
        const now = optOf(c, table, k, name);
        o[name] = t.checked ? [...now, t.dataset.val] : now.filter((x) => x !== t.dataset.val);
      }
    } else return;
    savePrefs(); draw();
  });
  list.addEventListener('click', (e) => {
    const row = e.target.closest('.col-row');
    if (!row) return;
    const k = row.dataset.k;
    if (e.target.closest('[data-open]')) { open.has(k) ? open.delete(k) : open.add(k); draw(); return; }
    const b = e.target.closest('button[data-opt]');
    if (!b) return;
    const c = cfg(), o = table[k].opts.find((x) => x.k === b.dataset.opt);
    const value = o.values.find(([x]) => String(x) === b.dataset.val)[0];   // 3 stays a number
    ((c.opt ??= {})[k] ??= {})[o.k] = value;
    savePrefs(); draw();
  });
  return () => { onReset(); savePrefs(); draw(); };
}
