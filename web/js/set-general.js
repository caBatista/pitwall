import { desktop } from './set-screen.js';
import { prefs, savePrefs } from './util.js';

/** What belongs to the app window: only in the desktop app, a browser has its own. */
export async function generalPage(root) {
  const shown = root.dataset.shown;
  const api = await desktop();
  if (root.dataset.shown !== shown) return;
  root.insertAdjacentHTML('beforeend', `
    <section class="st-sec">
      <div class="st-sec-h"><h2>iRacing</h2></div>
      <div class="st-list">
        <label class="st-row"><span>Keep iRacing in full screen<small>When it takes the focus in a window, Pitwall presses Alt+Enter.</small></span>
          <select id="set-sim-full" class="st-pick">${[['on', 'Always'], ['car', 'Only in the car'], ['off', 'Off']].map(([v, n]) => `<option value="${v}" ${(prefs.simFull === false ? 'off' : prefs.simFull === 'car' ? 'car' : 'on') === v ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
      </div>
    </section>
    <section class="st-sec">
      <div class="st-sec-h"><h2>Look</h2></div>
      <div class="st-list">
        <label class="st-row"><span>Size<small>Of everything on the board. The keys all go to iRacing.</small></span>
          <select id="set-zoom" class="st-pick">${[0.9, 1, 1.05, 1.1, 1.15, 1.2, 1.3, 1.4, 1.5].map((z) => `<option value="${z}" ${Math.abs((prefs.zoom ?? 1.1) - z) < 0.001 ? 'selected' : ''}>${Math.round(z * 100)}%${z === 1.1 ? ' (default)' : ''}</option>`).join('')}</select></label>
      </div>
    </section>
    <section class="st-sec">
      <div class="st-sec-h"><h2>Animations</h2></div>
      <div class="st-list">
        <label class="st-row"><span>Animations<small>Position changes, flags in the background and on the tables, radio and pit blink.</small></span>
          <span class="st-sw"><input type="checkbox" id="set-anim" ${prefs.anim !== false ? 'checked' : ''}><i></i></span></label>
        <label class="st-row"><span>Position change<small>Picking one shows it on the board.</small></span>
          <select id="set-posfx" class="st-pick">${[['slide', 'Slide'], ['lift', 'Lift'], ['spring', 'Spring'], ['off', 'None']].map(([v, n]) => `<option value="${v}" ${(prefs.posFx ?? 'slide') === v ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
      </div>
    </section>`);
  root.querySelector('#set-zoom').addEventListener('change', (e) => { prefs.zoom = Number(e.target.value); savePrefs(); });
  root.querySelector('#set-anim').addEventListener('change', (e) => { prefs.anim = e.target.checked; savePrefs(); });
  root.querySelector('#set-posfx').addEventListener('change', (e) => { prefs.posFx = e.target.value; savePrefs(); });
  root.querySelector('#set-sim-full').addEventListener('change', (e) => { prefs.simFull = { on: true, car: 'car', off: false }[e.target.value]; savePrefs(); });
  if (!api) return;
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
