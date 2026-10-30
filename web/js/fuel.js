import { prefs, savePrefs, fmt } from './util.js';

/**
 * Fuel. Consumption comes from clean laps only (backend). In a race it also plans
 * the finish ("TO FINISH"): with enough fuel, how much is still needed and the
 * spare; otherwise on which lap to stop and how much to put in. Practice,
 * qualifying and test sessions only show the readings (no refuelling plan).
 */
export const fuel = {
  id: 'w-fuel',
  mount(root) {
    root.innerHTML = `
      <div class="card-h"><div class="ttl"><i></i>Fuel</div>
        <div class="fuel-ctl" id="fu-ctl"><span>Reserve</span><input class="num-in" id="fu-res" type="number" step="0.1" min="0" max="5">
        <span>Laps</span><input class="num-in" id="fu-tgt" type="number" step="1" min="1" max="999"></div></div>
      <div class="fuel">
        <div class="fu-lvl"><b id="fu-lvl">–</b><small id="fu-u">L</small><span id="fu-pct"></span></div>
        <div class="fu-bar"><i id="fu-bar"></i></div>
        <div class="stats" id="fu-stats"></div>
        <div class="fu-fin" id="fu-fin"></div>
      </div>`;
    this.q = (s) => root.querySelector(s);
    const res = this.q('#fu-res'), tgt = this.q('#fu-tgt');
    res.value = prefs.reserve; tgt.value = prefs.targetLaps;
    res.addEventListener('input', () => { prefs.reserve = Math.max(0, Number(res.value) || 0); savePrefs(); });
    tgt.addEventListener('input', () => { prefs.targetLaps = Math.max(1, Number(tgt.value) || 1); savePrefs(); });
    this.tgt = tgt;
    this.key = '';
  },

  update(S) {
    const st = S.st;
    if (!st) return;
    const f = st.fuel, q = this.q;
    const race = st.session.kind === 'race';
    q('#fu-ctl').hidden = !race;
    q('#fu-fin').hidden = !race;

    const auto = f.mode !== 'none' && f.lapsLeft != null;
    this.tgt.disabled = auto;
    this.tgt.style.opacity = auto ? 0.4 : 1;
    if (auto) this.tgt.value = Math.ceil(f.lapsLeft);

    // level: big number + a horizontal bar
    // the average (and all that depends on it) only from completed clean laps, never the live estimate
    const lvl = f.level, tank = f.tank || 0, avg = f.provisional ? null : f.avg;
    const fuelLaps = avg && lvl != null ? lvl / avg : null;
    const frac = tank ? Math.min(1, Math.max(0, lvl / tank)) : 0;
    const bar = q('#fu-bar');
    bar.style.width = (frac * 100).toFixed(1) + '%';
    bar.className = fuelLaps != null && fuelLaps < 3 ? 'low' : fuelLaps != null && fuelLaps < 6 ? 'mid' : '';
    const v = fmt.vol(lvl);
    q('#fu-lvl').textContent = v == null ? '–' : v.toFixed(1);
    q('#fu-u').textContent = fmt.volU();
    q('#fu-pct').textContent = tank ? `${Math.round(frac * 100)}% of ${fmt.vol(tank).toFixed(0)} ${fmt.volU()}` : '';

    const cell = (k, val, sub = '') => `<div class="kv"><small>${k}</small><b>${val}</b>${sub}</div>`;
    const per = (x) => (x == null ? '–' : fmt.vol(x).toFixed(2));
    const stats =
      cell('Avg / lap', per(avg)) +
      cell('Last lap', per(f.last)) +
      cell('Fuel laps', fuelLaps == null ? '–' : fuelLaps.toFixed(1)) +
      (race ? cell('Laps left', f.lapsLeft == null ? (auto ? '–' : prefs.targetLaps) : f.lapsLeft.toFixed(1)) : '');
    if (stats !== this.key) { q('#fu-stats').innerHTML = stats; this.key = stats; }

    if (!race) return;
    // TO FINISH
    const L = (x) => `${fmt.vol(x).toFixed(1)} ${fmt.volU()}`;
    const target = auto ? f.lapsLeft : prefs.targetLaps;
    let main = 'Learning', sub = 'complete a clean lap', cls = '';
    if (avg && lvl != null && target != null) {
      const toGo = target * avg;                       // fuel still needed to see the flag
      const spare = lvl - toGo;
      if (spare >= prefs.reserve * avg) {
        main = `${L(toGo)} to go`; sub = `+${L(spare)} spare`; cls = 'ok';
      } else {
        const lapNow = st.me.lap ?? 0;
        const pitLap = lapNow + Math.max(0, Math.floor(lvl / avg));   // last lap you can complete
        const atStop = lvl - (pitLap - lapNow) * avg;                  // what is left when you stop
        const missing = toGo + prefs.reserve * avg - lvl;               // to finish with the reserve
        const room = tank ? tank - atStop : missing;
        const fill = missing > room;
        main = `Pit lap ${pitLap}`;
        sub = fill ? `fill the tank (+${L(room)}) · ${Math.ceil(missing / (tank || missing))} stops` : `add ${L(missing)}`;
        cls = fill ? 'bad' : 'warn';
      }
    }
    const fin = `<small>To finish</small><b>${main}</b><span>${sub}</span>`;
    const box = q('#fu-fin');
    box.className = 'fu-fin ' + cls;
    if (box.innerHTML !== fin) box.innerHTML = fin;
  },
};
