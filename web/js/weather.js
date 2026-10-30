import { fmt, tod } from './util.js';

const SKIES = ['Clear', 'Partly cloudy', 'Mostly cloudy', 'Overcast'];
const WET = ['Dry', 'Mostly dry', 'Very lightly wet', 'Lightly wet', 'Moderately wet', 'Very wet', 'Extremely wet'];

/**
 * Weather monitor. iRacing exposes the *current* conditions only (no forecast),
 * so this shows trends over the last hour instead: temperature drift, rain
 * arriving, track getting wetter or drying out.
 */
export const weather = {
  id: 'w-weather',
  mount(root) {
    root.innerHTML = `
      <div class="card-h"><div class="ttl"><i></i>Weather</div>
        <div class="leg"><span><i style="background:var(--amber)"></i>Track</span><span><i style="background:var(--txt)"></i>Air</span></div></div>
      <div class="wx" id="wx-grid"></div>`;
    this.grid = root.querySelector('#wx-grid');
    this.grid.innerHTML = `
      <div><div class="kv"><small>Track</small></div><div class="wx-temp"><b id="wx-tr">–</b><em id="wx-tru"></em><span class="trend" id="wx-trt"></span></div></div>
      <div><div class="kv"><small>Air</small></div><div class="wx-temp"><b id="wx-ai">–</b><em id="wx-aiu"></em><span class="trend" id="wx-ait"></span></div></div>
      <div><div class="kv"><small>Track surface</small><b id="wx-wn" style="font-size:13px">–</b></div><div class="wet" id="wx-wet">${'<i></i>'.repeat(7)}</div></div>
      <div style="display:flex;gap:12px;align-items:center;justify-content:flex-end">
        <div class="kv" style="text-align:right"><small>Wind</small><b id="wx-wd">–</b><small id="wx-wdu" style="margin-top:2px"></small></div>
        <div class="compass"><svg viewBox="0 0 64 64"><g id="wx-arrow"><path d="M32 8 L40 36 L32 31 L24 36 Z" fill="var(--accent)"/></g>
          <circle cx="32" cy="32" r="2.2" fill="var(--bg-2)"/></svg></div></div>
      <div class="kv"><small>Rain</small><b id="wx-pr">–</b></div>
      <div class="kv"><small>Humidity · Fog</small><b id="wx-hu">–</b></div>
      <div class="kv"><small>Skies</small><b id="wx-sk" style="font-size:13px">–</b></div>
      <div class="kv"><small>Grip</small><b id="wx-gr" style="font-size:13px">–</b></div>
      <div class="kv"><small>Pressure · Time</small><b id="wx-pt" style="font-size:13px">–</b></div>
      <div class="wx-chart"><canvas id="wx-cv"></canvas></div>`;
    const q = (s) => root.querySelector(s);
    this.q = q;
    this.cv = q('#wx-cv');
    this.ctx = this.cv.getContext('2d');
    this.drawn = 0;
    new ResizeObserver(() => { this.drawn = 0; }).observe(this.cv.parentElement);
  },

  trend(hist, col, unit) {
    // change over (up to) the last 10 minutes
    if (hist.length < 12) return '';
    const last = hist[hist.length - 1], ref = hist[Math.max(0, hist.length - 120)];
    const d = last[col] - ref[col];
    if (Math.abs(d) < 0.3) return '';
    const v = unit === 'f' ? d * 9 / 5 : d;
    return `<span class="trend ${d > 0 ? 'up' : 'down'}">${d > 0 ? '▲' : '▼'}${Math.abs(v).toFixed(1)}</span>`;
  },

  update(S) {
    const st = S.st;
    if (!st) return;
    const w = st.wx, q = this.q;
    const t = (c) => (c == null ? '–' : fmt.temp(c).toFixed(1));
    q('#wx-tr').textContent = t(w.track); q('#wx-ai').textContent = t(w.air);
    q('#wx-tru').textContent = q('#wx-aiu').textContent = fmt.tempU();
    const h = S.wxHist;
    const u = fmt.tempU() === '°F' ? 'f' : 'c';
    q('#wx-trt').innerHTML = this.trend(h, 2, u);
    q('#wx-ait').innerHTML = this.trend(h, 1, u);

    // track wetness
    const wet = Math.max(0, Math.min(7, w.wet || 0));
    q('#wx-wn').textContent = w.wetName && w.wetName !== 'Unknown' ? w.wetName : WET[Math.max(0, wet - 1)] || '–';
    [...q('#wx-wet').children].forEach((el, k) => {
      el.className = k < wet ? 'on' : '';
      if (k < wet && wet <= 1) el.classList.add('dry');
    });
    if (wet <= 1) [...q('#wx-wet').children].forEach((el, k) => { el.className = k === 0 ? 'on dry' : ''; });

    // wind relative to the car: arrow shows where the wind pushes the car from
    const ws = w.wind;
    q('#wx-wd').textContent = ws == null ? '–' : fmt.speed(ws).toFixed(0);
    q('#wx-wdu').textContent = fmt.speedU();
    if (w.windDir != null && w.yaw != null) {
      const rel = ((w.windDir - w.yaw) * 180) / Math.PI; // 0 = headwind
      q('#wx-arrow').setAttribute('transform', `rotate(${rel.toFixed(1)} 32 32)`);
    }

    const pr = w.precip;
    q('#wx-pr').innerHTML = pr == null ? '–' : pr > 0.02 ? `<span style="color:var(--txt)">${(pr * 100).toFixed(0)}%</span>` : '<span style="color:var(--dim)">None</span>';
    q('#wx-hu').textContent = `${w.hum == null ? '–' : Math.round(w.hum * 100) + '%'} · ${w.fog ? Math.round(w.fog * 100) + '%' : '0%'}`;
    q('#wx-sk').textContent = w.skies == null ? '–' : SKIES[w.skies] || '–';
    // rubber on the racing line, as iRacing words it ("slight usage", "moderate usage", ...)
    q('#wx-gr').textContent = w.grip ? w.grip[0].toUpperCase() + w.grip.slice(1) : '–';
    const p = fmt.press(w.press);
    q('#wx-pt').textContent = `${p == null ? '–' : p.toFixed(fmt.pressU() === 'hPa' ? 0 : 2) + ' ' + fmt.pressU()} · ${tod(w.tod)}`;

    // chart, redraw when history grows or on resize
    const key = h.length + ':' + (h.length ? h[h.length - 1][0] : 0) + fmt.tempU();
    if (key !== this.drawn) { this.drawn = key; this.chart(h); }
  },

  chart(h) {
    const cv = this.cv, r = cv.parentElement.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
    const c = this.ctx; c.setTransform(dpr, 0, 0, dpr, 0, 0);
    const W = r.width, H = r.height;
    c.clearRect(0, 0, W, H);
    if (h.length < 2) return;
    const tr = h.map((p) => fmt.temp(p[2])), ai = h.map((p) => fmt.temp(p[1]));
    const all = tr.concat(ai), lo = Math.min(...all) - 1, hi = Math.max(...all) + 1;
    const x = (k) => (k / (h.length - 1)) * (W - 2) + 1, y = (v) => H - 4 - ((v - lo) / (hi - lo || 1)) * (H - 10);
    // rain bars
    h.forEach((p, k) => {
      if (p[4] > 0.02 || p[3] > 2) {
        c.fillStyle = `rgba(244,242,236,${Math.min(0.22, 0.06 + p[4] * 0.3)})`;
        c.fillRect(x(k) - 1, 0, Math.max(2, W / h.length), H);
      }
    });
    const line = (arr, col) => { c.beginPath(); arr.forEach((v, k) => (k ? c.lineTo(x(k), y(v)) : c.moveTo(x(k), y(v)))); c.strokeStyle = col; c.lineWidth = 1.8; c.lineJoin = 'round'; c.stroke(); };
    line(ai, '#f4f2ec'); line(tr, '#f4b400');
    c.font = '600 10px Montserrat, sans-serif'; c.fillStyle = '#8a8a8f'; c.textAlign = 'left';
    c.fillText(hi.toFixed(0), 2, 9); c.fillText(lo.toFixed(0), 2, H - 1);
  },
};
