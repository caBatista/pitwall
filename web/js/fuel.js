import { prefs, savePrefs, fmt } from './util.js';

/** Scroll wheel of values, like a phone's date picker: 0.0 to 5.0 by tenths, with the mouse wheel,
 *  by dragging or touch, by tapping a value or with the arrow keys. */
function picker(el, value, change) {
  const MAX = 50;
  const list = el.querySelector('.fu-list');
  list.innerHTML = Array.from({ length: MAX + 1 }, (_, k) => `<span>${(k / 10).toFixed(1)}</span>`).join('');
  const items = [...list.children];
  const clamp = (k) => Math.max(0, Math.min(MAX, k));
  let at = clamp(Math.round(value * 10)), lit = null, spun = 0, drag = null;
  const show = (pos, slide) => {
    list.classList.toggle('slide', slide);
    list.style.setProperty('--at', pos);
    const k = items[clamp(Math.round(pos))];
    if (k !== lit) { lit?.classList.remove('on'); k.classList.add('on'); lit = k; }
  };
  const go = (k) => {
    k = clamp(k);
    show(k, true);
    if (k !== at) { at = k; change(k / 10); }
  };
  show(at, false);
  el.addEventListener('wheel', (e) => {
    spun += e.deltaY;
    if (Math.abs(spun) >= 50) { go(at + Math.sign(spun)); spun = 0; }
  }, { passive: true });
  el.addEventListener('keydown', (e) => {
    const step = { ArrowDown: 1, ArrowUp: -1 }[e.key];
    if (step) { e.preventDefault(); go(at + step); }
  });
  el.addEventListener('pointerdown', (e) => {
    el.setPointerCapture(e.pointerId);
    drag = { y: e.clientY, h: items[0].getBoundingClientRect().height, moved: false, on: e.target.closest('.fu-list span') };
  });
  el.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const dy = drag.y - e.clientY;
    if (Math.abs(dy) > 3) drag.moved = true;
    if (drag.moved) show(clamp(at + dy / drag.h), false);
  });
  const drop = (e) => {
    if (!drag) return;
    const { y, h, moved, on } = drag;
    drag = null;
    if (moved) go(Math.round(at + (y - e.clientY) / h));
    else if (on) go(items.indexOf(on));
  };
  el.addEventListener('pointerup', drop);
  el.addEventListener('pointercancel', drop);
}

/** How to reach the flag with reserve laps of fuel left. Enough already: {stops: 0, toGo, spare}.
 *  Otherwise how many stops and the laps of the next one: last is the last lap the fuel in the tank
 *  completes, first the earliest from which full tanks at every stop still get there, never before the
 *  next lap. add: what goes in if that stop is made on first. */
export function pitPlan(level, avg, laps, reserve, tank, lap) {
  if (!avg || level == null || laps == null) return null;
  const toGo = laps * avg, spare = level - toGo;
  if (spare >= reserve * avg) return { stops: 0, toGo, spare };
  const missing = toGo + reserve * avg - level;
  const reach = Math.max(0, Math.floor(level / avg));
  let stops = tank ? Math.max(1, Math.ceil(missing / tank)) : 1, wait = 0;
  for (; tank; stops++) {   // stopping too early would need one stop more
    wait = Math.max(0, Math.ceil(laps + reserve - stops * tank / avg));
    if (wait <= reach) break;
  }
  wait = Math.max(wait, Math.min(1, reach));
  const add = tank ? Math.min(missing, tank - (level - wait * avg)) : missing;
  return { stops, add, first: lap + wait, last: lap + reach };
}

/**
 * Fuel. Consumption comes from clean laps only (backend). The level is a bar, the readings a list of
 * label + value. In a race it also plans the finish ("TO FINISH"): with enough fuel, how much is still
 * needed and the spare; otherwise between which laps to stop, how much is missing and how many stops. With Auto fuel on, the
 * server sets iRacing's pit menu to what is missing as I enter the pit lane (nothing, if nothing is).
 * Practice, qualifying and test sessions only show the readings.
 */
export const fuel = {
  id: 'w-fuel',
  mount(root, S) {
    root.innerHTML = `
      <div class="card-h"><div class="ttl"><i></i>Fuel</div>
        <label class="switch" id="fu-sw" title="Sets the fuel you need as you enter the pits"><span>Auto fuel</span><input type="checkbox" id="fu-auto"><i></i></label></div>
      <div class="fuel">
        <div class="fu-top">
          <div class="fu-lvl">
            <div class="fu-val"><b id="fu-lvl">–</b><small id="fu-u"></small><span id="fu-pct"></span></div>
            <div class="fu-bar"><i id="fu-bar"></i></div>
          </div>
          <div class="fu-rows">
            <div class="fu-row"><span>Avg / lap</span><b id="fu-avg">–</b></div>
            <div class="fu-row"><span>Last lap</span><b id="fu-last">–</b></div>
            <div class="fu-row"><span>Fuel laps</span><b id="fu-laps">–</b></div>
            <div class="fu-row" id="fu-r-tgt"><span>Laps left</span><input class="num-in" id="fu-tgt" type="number" step="1" min="1" max="999"></div>
          </div>
          <div class="fu-wheel" id="fu-wheel" tabindex="0" role="spinbutton" aria-label="Reserve, in laps">
            <small>Reserve</small><div class="fu-win"><div class="fu-list"></div></div><small>laps</small>
          </div>
        </div>
        <div class="fu-fin" id="fu-fin">
          <small>To finish</small>
          <div class="fu-l"><small id="fu-key"></small><b id="fu-main"></b></div>
          <div class="fu-r"><b><span id="fu-val"></span><small id="fu-vu"></small></b><span id="fu-sub"></span></div>
        </div>
      </div>`;
    this.q = (s) => root.querySelector(s);
    const tgt = this.q('#fu-tgt'), sw = this.q('#fu-auto');
    tgt.value = prefs.targetLaps; sw.checked = prefs.autoFuel;
    picker(this.q('#fu-wheel'), prefs.reserve, (v) => { prefs.reserve = v; savePrefs(); S.invalidate(); });
    tgt.addEventListener('input', () => { prefs.targetLaps = Math.max(1, Number(tgt.value) || 1); savePrefs(); });
    sw.addEventListener('change', () => { prefs.autoFuel = sw.checked; savePrefs(); });
    this.tgt = tgt;
    this.frac = 0;
  },

  update(S) {
    const st = S.st;
    if (!st) return;
    const f = st.fuel, q = this.q;
    const race = st.session.kind === 'race';
    for (const id of ['#fu-sw', '#fu-r-tgt', '#fu-wheel', '#fu-fin']) q(id).hidden = !race;

    // the server does the refuelling, even with this window out of sight: it has to know the settings
    const cfg = `${prefs.autoFuel}|${prefs.reserve}|${prefs.targetLaps}`;
    if (cfg !== this.cfg || S.ws !== this.ws) {
      this.cfg = cfg; this.ws = S.ws;
      S.send({ cmd: 'auto_fuel', on: prefs.autoFuel, reserve: prefs.reserve, laps: prefs.targetLaps });
    }

    const auto = f.mode !== 'none' && f.lapsLeft != null;
    this.tgt.disabled = auto;
    if (auto) this.tgt.value = f.lapsLeft.toFixed(1);

    // the average (and all that depends on it) only from completed clean laps, never the live estimate
    const lvl = f.level, tank = f.tank || 0, avg = f.provisional ? null : f.avg;
    const fuelLaps = avg && lvl != null ? lvl / avg : null;
    const frac = tank ? Math.min(1, Math.max(0, lvl / tank)) : 0;
    const bar = q('#fu-bar');
    // the .4 s slide is for a real change (a stop). Burning fuel moves it by a fraction of a pixel every
    // update, and a width transition that never ends is a layout per display frame, all race long
    const width = (frac * 100).toFixed(1) + '%';
    if (width !== this.width) {
      bar.classList.toggle('still', Math.abs(frac - this.frac) < 0.02);
      bar.style.width = this.width = width;
      this.frac = frac;
    }
    bar.classList.toggle('low', fuelLaps != null && fuelLaps < 3);
    bar.classList.toggle('mid', fuelLaps != null && fuelLaps >= 3 && fuelLaps < 6);
    const v = fmt.vol(lvl);
    const set = (id, text) => { const el = q(id); if (el.textContent !== text) el.textContent = text; };
    set('#fu-lvl', v == null ? '–' : v.toFixed(1));
    set('#fu-u', fmt.volU());
    set('#fu-pct', tank ? `${Math.round(frac * 100)}% of ${fmt.vol(tank).toFixed(0)} ${fmt.volU()}` : '');
    const per = (x) => (x == null ? '–' : `${fmt.vol(x).toFixed(2)} ${fmt.volU()}`);
    set('#fu-avg', per(avg));
    set('#fu-last', per(f.last));
    set('#fu-laps', fuelLaps == null ? '–' : fuelLaps.toFixed(1));

    if (!race) return;
    // TO FINISH
    const plan = pitPlan(lvl, avg, auto ? f.lapsLeft : prefs.targetLaps, prefs.reserve, tank, f.lap ?? 0);
    const liters = (x) => fmt.vol(x).toFixed(2);
    const L1 = (x) => `${fmt.vol(x).toFixed(1)} ${fmt.volU()}`;
    let key = 'Waiting for', main = 'A clean lap', val = '', sub = '';
    if (plan?.stops === 0) {
      key = 'Fuel needed'; main = L1(plan.toGo); val = `+${liters(plan.spare)}`; sub = 'Spare';
    } else if (plan) {
      key = plan.stops > 1 ? 'Next pit between' : 'Pit between';
      main = plan.first === plan.last ? `Lap ${plan.last}` : `Lap ${plan.first} – ${plan.last}`;
      val = `+${liters(plan.add)}`; sub = `${plan.stops} ${plan.stops > 1 ? 'stops' : 'stop'}`;
    }
    q('#fu-fin').classList.toggle('ok', plan?.stops === 0);
    set('#fu-key', key);
    set('#fu-main', main);
    set('#fu-val', val);
    set('#fu-vu', val ? fmt.volU() : '');
    set('#fu-sub', sub);
  },
};
