import { prefs, savePrefs, fmt } from './util.js';

const R = 56, C = 2 * Math.PI * R;

/**
 * Fuel calculator. Consumption comes from clean laps only (backend). Everything
 * about the plan (reserve, target laps) is computed here so the inputs react
 * instantly. When the session has a lap/time limit the target is automatic.
 */
export const fuel = {
  id: 'w-fuel',
  mount(root) {
    root.innerHTML = `
      <div class="card-h"><div class="ttl"><i></i>Fuel</div>
        <div class="fuel-ctl"><span>Reserve</span><input class="num-in" id="fu-res" type="number" step="0.1" min="0" max="5">
        <span id="fu-tl-wrap">Laps</span><input class="num-in" id="fu-tgt" type="number" step="1" min="1" max="999"></div></div>
      <div class="fuel">
        <div class="gauge"><svg viewBox="0 0 132 132">
          <circle cx="66" cy="66" r="${R}" fill="none" stroke="var(--line)" stroke-width="10"/>
          <circle id="fu-arc" cx="66" cy="66" r="${R}" fill="none" stroke="var(--accent)" stroke-width="10" stroke-linecap="round"
            stroke-dasharray="${C}" stroke-dashoffset="${C}" style="transition:stroke-dashoffset .4s, stroke .3s"/></svg>
          <div class="gv"><b id="fu-lvl">–</b><small id="fu-u">L</small></div></div>
        <div class="stats" id="fu-stats"></div>
      </div>
      <div class="verdict"><div class="vbox" id="fu-v"><b>Learning</b><span>Complete a clean lap</span></div>
        <div class="spark" id="fu-spark"></div></div>`;
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
    const auto = f.mode !== 'none' && f.lapsLeft != null;
    this.tgt.disabled = auto;
    this.tgt.style.opacity = auto ? 0.4 : 1;
    if (auto) this.tgt.value = Math.ceil(f.lapsLeft);

    const lvl = f.level, tank = f.tank || 0, avg = f.avg;
    const frac = tank ? Math.min(1, Math.max(0, lvl / tank)) : 0;
    const arc = q('#fu-arc');
    arc.style.strokeDashoffset = C * (1 - frac);
    const lowLaps = f.fuelLaps != null && f.fuelLaps < 3;
    arc.style.stroke = lowLaps ? 'var(--red)' : f.fuelLaps != null && f.fuelLaps < 6 ? 'var(--amber)' : 'var(--accent)';
    const v = fmt.vol(lvl);
    q('#fu-lvl').textContent = v == null ? '–' : v.toFixed(1);
    q('#fu-u').textContent = fmt.volU();

    const cell = (k, val, sub = '') => `<div class="kv"><small>${k}</small><b>${val}</b>${sub}</div>`;
    const per = (x) => (x == null ? '–' : fmt.vol(x).toFixed(2));
    const stats =
      cell('Avg / lap', per(avg), f.provisional ? '<small style="color:var(--amber)">estimate</small>' : '') +
      cell('Last lap', per(f.last)) +
      cell('Fuel laps', f.fuelLaps == null ? '–' : f.fuelLaps.toFixed(1)) +
      cell('Laps left', f.lapsLeft == null ? (auto ? '–' : `<span style="color:var(--dim)">${prefs.targetLaps}</span>`) : f.lapsLeft.toFixed(1));
    if (stats !== this.key) { q('#fu-stats').innerHTML = stats; this.key = stats; }

    // plan
    const box = q('#fu-v');
    const target = auto ? f.lapsLeft : prefs.targetLaps;
    let cls = '', head = 'Learning', tail = 'Complete a clean lap';
    if (avg && lvl != null && target != null) {
      const need = (target + prefs.reserve) * avg;
      const add = need - lvl;
      if (add <= 0) {
        cls = 'ok'; head = 'Enough fuel';
        tail = `+${fmt.vol(-add).toFixed(1)} ${fmt.volU()} spare`;
      } else if (tank && add <= tank - lvl + 1e-6) {
        cls = 'warn'; head = 'Add fuel';
        tail = `+${fmt.vol(add).toFixed(1)} ${fmt.volU()} · 1 stop`;
      } else {
        const stops = tank ? Math.ceil(add / tank) : 1;
        cls = 'bad'; head = `${stops} stop${stops > 1 ? 's' : ''}`;
        tail = `need ${fmt.vol(need).toFixed(1)} ${fmt.volU()}`;
      }
    }
    box.className = 'vbox ' + cls;
    box.innerHTML = `<b>${head}</b><span>${tail}</span>`;

    // per-lap sparkline
    const laps = (f.laps || []).slice(-12);
    const spark = q('#fu-spark');
    if (laps.length) {
      const lo = Math.min(...laps) * 0.9, hi = Math.max(...laps) * 1.02;
      const html = laps.map((x) => `<i title="${per(x)}" style="height:${Math.max(12, ((x - lo) / (hi - lo || 1)) * 100)}%"></i>`).join('');
      if (spark.innerHTML !== html) spark.innerHTML = html;
    } else spark.innerHTML = '';
  },
};
