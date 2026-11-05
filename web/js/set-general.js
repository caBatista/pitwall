import { desktop } from './set-screen.js';

/** What belongs to the app window: only in the desktop app, a browser has its own. */
export async function generalPage(root) {
  const shown = root.dataset.shown;
  const api = await desktop();
  if (root.dataset.shown !== shown) return;
  if (!api) {
    root.insertAdjacentHTML('beforeend', '<div class="st-none">No settings yet</div>');
    return;
  }
  const on = await api.get_fullscreen();
  if (root.dataset.shown !== shown) return;
  root.insertAdjacentHTML('beforeend', `
    <section class="st-sec">
      <div class="st-sec-h"><h2>Window</h2></div>
      <div class="st-list">
        <label class="st-row"><span>Full screen<small>On by default. F11 does the same.</small></span>
          <span class="st-sw"><input type="checkbox" id="set-full" ${on ? 'checked' : ''}><i></i></span></label>
      </div>
    </section>`);
  root.querySelector('#set-full').addEventListener('change', (e) => api.set_fullscreen(e.target.checked));
}
