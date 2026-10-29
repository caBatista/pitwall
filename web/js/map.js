import { esc } from './util.js';

/**
 * Track map drawn on a canvas from the outline the backend records during your
 * first clean lap (cached per track afterwards). Cars are placed by lap
 * distance on the outline, coloured by class.
 */
export const trackmap = {
  id: 'w-map',
  mount(root, S) {
    root.innerHTML = `
      <div class="card-h"><div class="ttl"><i></i>Track map</div>
        <div class="ctl"><span class="ghost-btn" id="mp-reset" title="Re-record the outline on your next clean lap">Re-record</span></div></div>
      <div class="map-wrap"><canvas id="mp-cv"></canvas><div class="map-note" id="mp-note"></div></div>`;
    this.cv = root.querySelector('#mp-cv');
    this.note = root.querySelector('#mp-note');
    this.ctx = this.cv.getContext('2d');
    this.fit = null;
    this.fitVer = -1;
    this.noteKey = '';
    root.querySelector('#mp-reset').addEventListener('click', () => S.send({ cmd: 'reset_map' }));
    new ResizeObserver(() => { this.fitVer = -1; this.size(); }).observe(this.cv.parentElement);
    this.size();
  },

  size() {
    const r = this.cv.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.cv.width = Math.max(1, Math.round(r.width * dpr));
    this.cv.height = Math.max(1, Math.round(r.height * dpr));
    this.dpr = dpr; this.W = r.width; this.H = r.height;
  },

  compute(pts) {
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const [x, y] of pts) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
    const pad = 26, w = x1 - x0 || 1, h = y1 - y0 || 1;
    const sc = Math.min((this.W - pad * 2) / w, (this.H - pad * 2) / h);
    const ox = (this.W - w * sc) / 2 - x0 * sc, oy = (this.H - h * sc) / 2 + y1 * sc; // y flipped: north up
    this.fit = (p) => [p[0] * sc + ox, oy - p[1] * sc];
  },

  at(pts, pct) {
    const n = pts.length, f = ((pct % 1) + 1) % 1 * n, i = Math.floor(f) % n, j = (i + 1) % n, w = f - Math.floor(f);
    return [pts[i][0] + (pts[j][0] - pts[i][0]) * w, pts[i][1] + (pts[j][1] - pts[i][1]) * w];
  },

  update(S) {
    const st = S.st, ctx = this.ctx, pts = S.track?.points;
    if (!this.W) this.size();
    const status = pts ? 'ready' : st?.map?.status || 'none';
    // note
    let note = '';
    if (!pts) {
      if (status === 'recording') note = `<b>Recording the outline…</b>Keep driving a clean lap — ${Math.round((st.map.progress || 0) * 100)}%<div class="bar"><i style="width:${(st.map.progress || 0) * 100}%"></i></div>`;
      else if (status === 'waiting') note = '<b>Track map</b>The outline is drawn from your first clean lap. Cross the line on track to start.';
      else note = '<b>No outline yet</b>Drive a lap to record it.';
    }
    if (note !== this.noteKey) { this.note.innerHTML = note; this.noteKey = note; }

    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.W, this.H);
    if (!pts || !st) return;
    if (this.fitVer !== S.track.ver) { this.compute(pts); this.fitVer = S.track.ver; }
    const P = pts.map(this.fit);

    // asphalt ribbon
    ctx.lineJoin = ctx.lineCap = 'round';
    const path = () => { ctx.beginPath(); P.forEach(([x, y], k) => (k ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); };
    path(); ctx.strokeStyle = '#111112'; ctx.lineWidth = 15; ctx.stroke();
    path(); ctx.strokeStyle = '#3a3a3e'; ctx.lineWidth = 11; ctx.stroke();
    path(); ctx.strokeStyle = '#2a2a2d'; ctx.lineWidth = 8; ctx.stroke();

    // start / finish
    const [sx, sy] = P[0], [nx, ny] = P[3];
    const a = Math.atan2(ny - sy, nx - sx) + Math.PI / 2;
    ctx.strokeStyle = '#f4f2ec'; ctx.lineWidth = 2.5; ctx.beginPath();
    ctx.moveTo(sx - Math.cos(a) * 9, sy - Math.sin(a) * 9); ctx.lineTo(sx + Math.cos(a) * 9, sy + Math.sin(a) * 9); ctx.stroke();

    // cars: others first, then selected, then me on top
    const dot = (c, r, fill, ring) => {
      const [x, y] = this.fit(this.at(pts, c.pct));
      ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fillStyle = fill; ctx.fill();
      if (ring) { ctx.lineWidth = 2; ctx.strokeStyle = ring; ctx.stroke(); }
      return [x, y];
    };
    const me = st.me.i;
    for (const c of st.cars) {
      if (c.i === me || c.i === S.sel || c.pct == null || c.pct < 0 || c.srf < 0) continue;
      const d = S.drivers[c.i];
      ctx.globalAlpha = c.pit ? 0.4 : 0.95;
      dot(c, 4.5, S.classMap.get(d?.cls)?.color || '#8a8a8f', '#111112');
    }
    ctx.globalAlpha = 1;
    const label = (c, text, col) => {
      const [x, y] = this.fit(this.at(pts, c.pct));
      ctx.font = '600 11px Geist Mono, monospace'; ctx.textAlign = 'left';
      ctx.fillStyle = '#06080bcc'; const w = ctx.measureText(text).width + 8;
      ctx.fillRect(x + 10, y - 17, w, 16); ctx.fillStyle = col; ctx.fillText(text, x + 14, y - 5);
    };
    const sel = st.cars.find((c) => c.i === S.sel);
    if (sel && sel.pct >= 0) {
      const d = S.drivers[sel.i];
      dot(sel, 6, S.classMap.get(d?.cls)?.color || '#fff', '#ffffff');
      label(sel, '#' + (d?.num || ''), '#ffffff');
    }
    const mc = st.cars.find((c) => c.i === me);
    if (mc && mc.pct >= 0) {
      const d = S.drivers[me];
      const [x, y] = dot(mc, 6.5, '#f4b400', '#111112');
      ctx.beginPath(); ctx.arc(x, y, 11, 0, 7); ctx.lineWidth = 1.5; ctx.strokeStyle = 'rgba(244,180,0,.6)'; ctx.stroke();
    }
  },
};
