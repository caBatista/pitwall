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
          <span class="st-sw"><input type="checkbox" id="set-sim-full" ${prefs.simFull !== false ? 'checked' : ''}><i></i></span></label>
        <label class="st-row"><span>Race flags on the background<small>The background takes the colour of the flag you get.</small></span>
          <span class="st-sw"><input type="checkbox" id="set-flags" ${prefs.raceFlags !== false ? 'checked' : ''}><i></i></span></label>
      </div>
    </section>`);
  root.querySelector('#set-flags').addEventListener('change', (e) => { prefs.raceFlags = e.target.checked; savePrefs(); });
  root.querySelector('#set-sim-full').addEventListener('change', (e) => { prefs.simFull = e.target.checked; savePrefs(); });
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
