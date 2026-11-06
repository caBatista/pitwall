import { esc } from './util.js';

/**
 * Camera control: which camera, which driver, which lap, and moving the camera itself.
 * The SDK picks cameras and drives the replay; moving one is keys in iRacing's camera tool, held
 * for as long as a stick here is pushed (see pitwall/camera.py). Only with the driver out of the car.
 */
const SPEEDS = [['‹‹', -1], ['Ⅱ', 0], ['›', 1], ['2×', 2], ['4×', 4], ['8×', 8], ['16×', 16]];
const SLOW = [['1/2', 2], ['1/4', 4], ['1/8', 8]];
const SEND_MS = 90;

/** Pushed this far, the camera goes at this share of its speed: gentle near the centre. */
const curve = (v) => Math.round(v * v * 100) / 100;

// a stick: axes[0] is right/left, axes[1] up/down, each a pair of camera axes
function stickHtml(id, label, kind) {
  return `<div class="cam-stick"><div class="joy ${kind}" data-stick="${id}"><i></i></div>${label}</div>`;
}

const STICKS = {
  move: { x: ['lat-', 'lat+'], y: ['lon+', 'lon-'] },
  aim: { x: ['yaw-', 'yaw+'], y: ['pitch-', 'pitch+'] },
  height: { y: ['alt+', 'alt-'] },
  zoom: { y: ['fov-', 'fov+'] },
  roll: { x: ['roll+', 'roll-'] },
};

export const camera = {
  id: 'w-camera',
  mount(root, S) {
    this.root = root; this.S = S; this.key = '';
    root.innerHTML = `
      <div class="card-h"><div class="ttl">Camera control</div></div>
      <div class="cam" hidden>
        <div class="cam-row">
          <label>Camera group<select data-pick="group"></select></label>
          <label>Camera<select data-pick="camera"></select></label>
          <label>Driver<select data-pick="driver"></select></label>
        </div>
        <div class="cam-row">
          <button class="cam-b" data-do="follow" data-n="-2">Leader</button>
          <button class="cam-b" data-do="follow" data-n="-1">Exciting</button>
          <button class="cam-b" data-do="follow" data-n="-3">Incidents</button>
        </div>
        <div class="cam-h">Replay</div>
        <div class="cam-row" data-speeds>
          ${SPEEDS.map(([t, n]) => `<button class="cam-b" data-do="speed" data-n="${n}">${t}</button>`).join('')}
          ${SLOW.map(([t, n]) => `<button class="cam-b" data-do="speed" data-n="${n}" data-slow="1">${t}</button>`).join('')}
        </div>
        <div class="cam-row">
          <button class="cam-b" data-do="search" data-n="4" title="Previous lap">‹ Lap</button>
          <button class="cam-b" data-do="search" data-n="5" title="Next lap">Lap ›</button>
          <label style="flex:0 0 70px">Go to lap<input type="number" min="1" data-lap></label>
          <button class="cam-b" data-do="search" data-n="8" title="Previous incident">‹ Inc</button>
          <button class="cam-b" data-do="search" data-n="9" title="Next incident">Inc ›</button>
          <button class="cam-b" data-do="search" data-n="6" title="Previous frame">‹ F</button>
          <button class="cam-b" data-do="search" data-n="7" title="Next frame">F ›</button>
          <button class="cam-b" data-live>Live</button>
        </div>
        <div class="cam-h">Adjust the camera</div>
        <div class="cam-row">
          <button class="cam-b" data-tool>Edit</button>
          <button class="cam-b" data-hide>Hide panel</button>
          <button class="cam-b" data-do="tap" data-n="step-" title="Slower">Step −</button>
          <button class="cam-b" data-do="tap" data-n="step+" title="Faster">Step +</button>
          <button class="cam-b" data-do="tap" data-n="x10">×10</button>
        </div>
        <div class="cam-sticks">
          ${stickHtml('move', 'Move', '')}${stickHtml('aim', 'Aim', '')}
          ${stickHtml('height', 'Height', 'v')}${stickHtml('zoom', 'Zoom', 'v')}${stickHtml('roll', 'Roll', 'h')}
        </div>
      </div>
      <div class="cam-off">Camera control works with the driver out of the car.</div>`;
    this.box = root.querySelector('.cam');
    this.off = root.querySelector('.cam-off');
    const send = (o) => S.send({ cmd: 'cam', ...o });

    root.addEventListener('change', (e) => {
      const t = e.target;
      if (t.dataset.pick) send({ do: t.dataset.pick, n: Number(t.value) });
      if ('lap' in t.dataset && t.value) send({ do: 'lap', n: Number(t.value) });
    });
    root.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      const d = b.dataset, st = S.st?.cam?.st ?? 0;
      if (d.do) send({ do: d.do, n: /^-?\d+$/.test(d.n) ? Number(d.n) : d.n, slow: !!d.slow });
      else if ('live' in d) S.send({ cmd: 'replay_live' });
      else if ('tool' in d) send({ do: 'tool', on: !(st & 4) });
      else if ('hide' in d) send({ do: 'hide', on: !(st & 8) });
    });
    for (const el of root.querySelectorAll('[data-stick]')) this.stick(el, send);
  },

  /** Held: says where it is every SEND_MS, because the server lets go by itself if it stops hearing. */
  stick(el, send) {
    const spec = STICKS[el.dataset.stick], knob = el.firstElementChild;
    let timer = 0, x = 0, y = 0;
    const axes = () => {
      const out = {};
      if (spec.x && curve(Math.abs(x))) out[spec.x[x > 0 ? 0 : 1]] = curve(Math.abs(x));
      if (spec.y && curve(Math.abs(y))) out[spec.y[y < 0 ? 0 : 1]] = curve(Math.abs(y));
      return out;
    };
    const move = (e) => {
      const b = el.getBoundingClientRect();
      const rx = Math.max(1, b.width / 2 - 19), ry = Math.max(1, b.height / 2 - 19);
      let dx = spec.x ? (e.clientX - b.left - b.width / 2) / rx : 0, dy = spec.y ? (e.clientY - b.top - b.height / 2) / ry : 0;
      const len = Math.hypot(dx, dy);
      if (len > 1) { dx /= len; dy /= len; }
      x = dx; y = dy;
      knob.style.transform = `translate(${dx * rx}px, ${dy * ry}px)`;
    };
    el.addEventListener('pointerdown', (e) => {
      el.setPointerCapture(e.pointerId);
      el.classList.add('held');
      move(e);
      send({ do: 'stick', axes: axes() });
      timer = setInterval(() => send({ do: 'stick', axes: axes() }), SEND_MS);
    });
    el.addEventListener('pointermove', (e) => { if (timer) move(e); });
    const end = () => {
      if (!timer) return;
      clearInterval(timer); timer = 0; x = y = 0;
      el.classList.remove('held');
      knob.style.transform = '';
      send({ do: 'stick', axes: {} });
    };
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
    el.addEventListener('lostpointercapture', end);
  },

  update(S) {
    if (!this.root.offsetParent && !this.root.closest('.solo')) return;
    const s = S.st?.session, cam = S.st?.cam;
    if (!s || !cam) return;
    const on = !s.inCar;
    this.box.hidden = !on; this.off.hidden = on;
    if (!on) return;
    const groups = S.meta?.cameras ?? [];
    const group = groups.find((g) => g.n === cam.g);
    const key = JSON.stringify([groups.map((g) => g.n), group?.n, cam.c, cam.i, Object.keys(S.drivers).length]);
    if (key !== this.key) {
      this.key = key;
      const pick = (name, list, cur) => {
        const el = this.root.querySelector(`[data-pick="${name}"]`);
        el.innerHTML = list.map(([v, t]) => `<option value="${v}" ${v === cur ? 'selected' : ''}>${esc(t)}</option>`).join('');
      };
      pick('group', groups.map((g) => [g.n, g.name]), cam.g);
      pick('camera', (group?.cams ?? []).map((c) => [c.n, c.name]), cam.c);
      const cars = [...S.st.cars].filter((c) => S.drivers[c.i]).sort((a, b) => (a.p ?? 999) - (b.p ?? 999));
      pick('driver', cars.map((c) => [c.i, `${c.p ?? '–'}. #${S.drivers[c.i].num} ${S.drivers[c.i].name}`]), cam.i);
    }
    const tool = !!(cam.st & 4), speed = cam.speed;
    for (const b of this.root.querySelectorAll('[data-do="speed"]')) {
      b.classList.toggle('on', Number(b.dataset.n) === speed && !!b.dataset.slow === cam.slow);
    }
    this.root.querySelector('[data-tool]').classList.toggle('on', tool);
    const hide = this.root.querySelector('[data-hide]');
    hide.classList.toggle('on', !!(cam.st & 8));
    hide.disabled = !tool;
    this.box.classList.toggle('no-tool', !(cam.st & 1));
  },
};
