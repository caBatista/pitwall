import { esc, prefs, savePrefs } from './util.js';
import { FLAGS, flagCfg } from './flagcfg.js';

export function flagsPage(root) {
  const cfg = flagCfg(prefs);
  const row = (k, f) => `<div class="st-row">
      <span>${esc(f.name)}<small>${esc(f.note ?? 'Seconds on the background, 0 for as long as the flag is out')}</small></span>
      <input class="st-num" type="number" min="0" max="600" step="1" data-secs="${k}" value="${cfg.items[k].secs}" aria-label="${esc(f.name)} seconds">
      <span class="st-sw"><input type="checkbox" data-on="${k}" ${cfg.items[k].on ? 'checked' : ''}><i></i></span>
    </div>`;
  root.insertAdjacentHTML('beforeend', `
    <section class="st-sec">
      <div class="st-list">
        <label class="st-row"><span>Race flags<small>The background takes the colour of the flag you get.</small></span>
          <span class="st-sw"><input type="checkbox" id="set-flags" ${cfg.on ? 'checked' : ''}><i></i></span></label>
      </div>
    </section>
    <section class="st-sec">
      <div class="st-sec-h"><h2>Flags</h2></div>
      <div class="st-list">${Object.entries(FLAGS).map(([k, f]) => row(k, f)).join('')}</div>
    </section>`);
  const save = () => { prefs.flags = cfg; savePrefs(); };
  root.querySelector('#set-flags').addEventListener('change', (e) => { cfg.on = e.target.checked; save(); });
  root.addEventListener('change', (e) => {
    const d = e.target.dataset;
    if (d.on) cfg.items[d.on].on = e.target.checked;
    else if (d.secs) cfg.items[d.secs].secs = Math.max(0, Math.min(600, Math.round(Number(e.target.value) || 0)));
    else return;
    save();
  });
}
