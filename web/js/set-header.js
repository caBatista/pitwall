import { prefs } from './util.js';
import { HEADER, headerDefault } from './columns.js';
import { listEditor, sessionHead } from './set-list.js';

export function headerPage(root) {
  root.insertAdjacentHTML('beforeend', `
    <section class="st-sec">
      <div class="st-sec-h"><h2>Items</h2><button class="st-link" data-reset>Reset</button></div>
      <div class="col-top"><span>Drag to reorder, the boxes choose the sessions.</span>${sessionHead()}</div>
      <ul class="col-list" id="list-head"></ul>
    </section>`);
  const reset = listEditor(root.querySelector('#list-head'), () => prefs.header, HEADER, () => { prefs.header = headerDefault(); });
  root.querySelector('[data-reset]').addEventListener('click', reset);
}
