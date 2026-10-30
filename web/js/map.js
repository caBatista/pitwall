
/**
 * Track map on a canvas. The outline comes from the track library (iRacing's own
 * drawing, there from the first second) or from your first clean lap. Cars are
 * placed by lap distance: a disc with the class position (class colours in
 * multiclass), me as the CB mark. Sector ticks from SplitTimeInfo, turn numbers
 * from the library. Qualifying shows only me.
 */
export const trackmap = {
  id: 'w-map',
  mount(root, S) {
    root.innerHTML = `
      <div class="card-h"><div class="ttl"><i></i>Track map</div></div>
      <div class="map-wrap"><canvas id="mp-cv"></canvas><div class="map-note" id="mp-note"></div></div>`;
    this.cv = root.querySelector('#mp-cv');
    this.note = root.querySelector('#mp-note');
    this.ctx = this.cv.getContext('2d');
    this.logo = new Image(); this.logo.src = '/img/cb-sprint-amber.svg';   // my car on the map
    this.fit = null;
    this.fitVer = -1;
    this.noteKey = '';
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

  compute(pts, turns = []) {
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const [x, y] of pts.concat(turns)) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
    const w = x1 - x0 || 1, h = y1 - y0 || 1;
    // everything (ribbon, discs, labels, margin) scales with one unit, so a small map stays balanced
    const fitTo = (pad) => Math.min((this.W - pad * 2) / w, (this.H - pad * 2) / h);
    let sc = fitTo(12);
    this.u = Math.max(3.5, Math.min(10, Math.min(w, h) * sc / 30));
    sc = fitTo(this.u * 1.8);
    const ox = (this.W - w * sc) / 2 - x0 * sc, oy = (this.H - h * sc) / 2 + y1 * sc; // y flipped: north up
    this.fit = (p) => [p[0] * sc + ox, oy - p[1] * sc];
  },

  at(pts, pct) {
    pct += this.off || 0;   // library outlines: calibrated shift of the start/finish line
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
      else if (status === 'waiting') note = '<b>Track map</b>No drawing of this track in the library: the outline is recorded on your first clean lap. Cross the line on track to start.';
      else note = '<b>No outline yet</b>Drive a lap to record it.';
    }
    if (note !== this.noteKey) { this.note.innerHTML = note; this.noteKey = note; }

    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.W, this.H);
    if (!pts || !st) return;
    if (this.fitVer !== S.track.ver) { this.compute(pts, S.track.turns || []); this.fitVer = S.track.ver; }
    const u = this.u;   // size unit, see compute()
    this.off = S.track.offset || 0;
    const P = pts.map(this.fit);

    // asphalt ribbon
    ctx.lineJoin = ctx.lineCap = 'round';
    const path = () => { ctx.beginPath(); P.forEach(([x, y], k) => (k ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); };
    path(); ctx.strokeStyle = '#111112'; ctx.lineWidth = u * 1.7; ctx.stroke();
    path(); ctx.strokeStyle = '#3a3a3e'; ctx.lineWidth = u * 1.25; ctx.stroke();
    path(); ctx.strokeStyle = '#2a2a2d'; ctx.lineWidth = u * 0.9; ctx.stroke();

    // sector boundaries (iRacing SplitTimeInfo): an amber tick across the track
    const tick = (pct, len, col, w) => {
      const [x, y] = this.fit(this.at(pts, pct)), [nx, ny] = this.fit(this.at(pts, pct + 0.004));
      const a = Math.atan2(ny - y, nx - x) + Math.PI / 2;
      ctx.strokeStyle = col; ctx.lineWidth = w; ctx.beginPath();
      ctx.moveTo(x - Math.cos(a) * len, y - Math.sin(a) * len); ctx.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len); ctx.stroke();
    };
    for (const sp of S.meta.sectors || []) if (sp > 0) tick(sp, u * 1.2, '#f4b400', Math.max(2, u * 0.32));
    tick(0, u * 1.2, '#f4f2ec', Math.max(2, u * 0.32));   // start / finish

    // turn numbers (library maps carry them in the same frame as the outline)
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (const [tx, ty, label] of S.track.turns || []) {
      const [x, y] = this.fit([tx, ty]);
      // no disc: a white number with a dark outline so it reads on any background
      ctx.font = `700 ${(u * 1.15).toFixed(1)}px Montserrat, sans-serif`;
      ctx.lineJoin = 'round'; ctx.lineWidth = Math.max(2.5, u * 0.45); ctx.strokeStyle = '#111112'; ctx.strokeText(label, x, y + 0.5);
      ctx.fillStyle = '#f4f2ec'; ctx.fillText(label, x, y + 0.5);
    }

    // cars: a disc with the class position; class colours only in multiclass
    const multi = S.classes.length > 1, me = st.me.i;
    const disc = (c, r, fill, txt, ring) => {
      const [x, y] = this.fit(this.at(pts, c.pct));
      ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fillStyle = fill; ctx.fill();
      ctx.lineWidth = Math.max(1.2, u * 0.2); ctx.strokeStyle = ring; ctx.stroke();
      if (txt != null) { ctx.font = `600 ${(r * 1.05).toFixed(1)}px Montserrat, sans-serif`; ctx.fillStyle = txt.col; ctx.fillText(txt.t, x, y + 0.5); }
      return [x, y];
    };
    const solo = st.session.kind === 'qualify';   // qualifying: only me on the map
    if (!solo) {
      for (const c of st.cars) {
        if (c.i === me || c.pct == null || c.pct < 0 || c.srf < 0) continue;
        const col = multi ? S.classMap.get(S.drivers[c.i]?.cls)?.color || '#8a8a8f' : '#f4b400';   // single class: amber
        ctx.globalAlpha = c.pit ? 0.45 : 1;
        disc(c, u, col, { t: c.cp ?? '–', col: '#111112' }, c.i === S.sel ? '#f4f2ec' : '#111112');
      }
      ctx.globalAlpha = 1;
    }
    // me: the CB mark, a bit bigger, ringed with my class colour in multiclass
    const mc = st.cars.find((c) => c.i === me);
    if (mc && mc.pct >= 0) {
      const ring = multi ? S.classMap.get(S.drivers[me]?.cls)?.color || '#f4b400' : '#f4b400';
      const r = u * 1.35, [x, y] = disc(mc, r, '#111112', null, ring);
      if (this.logo.complete) ctx.drawImage(this.logo, x - r * 0.75, y - r * 0.52, r * 1.5, r * 1.03);
    }
  },
};
