import { esc } from './util.js';

/**
 * Camera control, a compact take on iRacing's replay bar: the transport, then lap, camera and driver, with
 * the moves of the camera at the side. The SDK picks cameras and drives the replay; moving one is keys in
 * iRacing's camera tool, which the first push on a stick opens and which are held for as long as the stick
 * is pushed (see pitwall/camera.py). Only with the driver out of the car.
 */
const SEND_MS = 90;
const SHOWN_MS = 500;   // a click shows at once; the sim's answer takes a moment and mustn't flip it back meanwhile
const SLOW = [2, 4, 8];   // 1/2, 1/4, 1/8

/** Pushed this far, the camera goes at this share of its speed: gentle near the centre. */
const curve = (v) => Math.round(v * v * 100) / 100;

const icon = (d) => `<svg viewBox="0 0 16 16" aria-hidden="true">${d}</svg>`;
const wide = (d) => `<svg class="wide" viewBox="0 0 20 16" aria-hidden="true">${d}</svg>`;
const line = (d) => icon(`<path d="${d}" fill="none" stroke="currentColor" stroke-width="2"/>`);
const ICONS = {
  back: icon('<path d="M3.6 8a4.6 4.6 0 1 0 1.6-3.5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M6.6 1.8 3.4 4.6l3.8 1.2z"/><circle cx="8.2" cy="8" r="1.5"/>'),
  slow: icon('<rect x="3" y="3" width="1.8" height="10" rx=".5"/><path d="m7 3.4 6.4 4.6L7 12.6z"/>'),
  start: icon('<rect x="2" y="3" width="1.8" height="10" rx=".5"/><path d="M8.6 3.4 3.8 8l4.8 4.6zM14 3.4 9.2 8l4.8 4.6z"/>'),
  frameBack: icon('<rect x="4" y="3" width="1.8" height="10" rx=".5"/><path d="M12.4 3.4 6 8l6.4 4.6z"/>'),
  rew: icon('<path d="M8 3 1.6 8 8 13zM14.4 3 8 8l6.4 5z"/>'),
  pause: icon('<rect x="4" y="2.8" width="3" height="10.4" rx=".6"/><rect x="9" y="2.8" width="3" height="10.4" rx=".6"/>'),
  play: icon('<path d="M4.4 2.6 13 8l-8.6 5.4z"/>'),
  ff: icon('<path d="M8 3l6.4 5L8 13zM1.6 3 8 8l-6.4 5z"/>'),
  frame: icon('<path d="M3.6 3.4 10 8l-6.4 4.6z"/><rect x="10.2" y="3" width="1.8" height="10" rx=".5"/>'),
  end: icon('<path d="M2 3.4 6.8 8 2 12.6zM7.4 3.4 12.2 8l-4.8 4.6z"/><rect x="12.2" y="3" width="1.8" height="10" rx=".5"/>'),
  incBack: wide('<path d="M5 4 1.5 8 5 12" fill="none" stroke="currentColor" stroke-width="1.8"/><path fill-rule="evenodd" d="M13 2.4 19.4 13.6H6.6zM12.2 6.2v4h1.6v-4zm0 4.8v1.4h1.6V11z"/>'),
  incNext: wide('<path d="M15 4 18.5 8 15 12" fill="none" stroke="currentColor" stroke-width="1.8"/><path fill-rule="evenodd" d="M7 2.4 13.4 13.6H.6zM6.2 6.2v4h1.6v-4zm0 4.8v1.4h1.6V11z"/>'),
  reset: icon('<path d="M3.2 8a4.8 4.8 0 1 0 1.5-3.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M6.8 1.4 3.2 4.6l4.2 1.3z"/>'),
  live: icon('<circle cx="8" cy="8" r="2"/><path d="M4.6 11.4a4.8 4.8 0 0 1 0-6.8M11.4 4.6a4.8 4.8 0 0 1 0 6.8M2.6 13.4a7.6 7.6 0 0 1 0-10.8M13.4 2.6a7.6 7.6 0 0 1 0 10.8" fill="none" stroke="currentColor" stroke-width="1.4"/>'),
  hide: icon('<path d="M1.4 8S3.8 3.8 8 3.8 14.6 8 14.6 8 12.2 12.2 8 12.2 1.4 8 1.4 8z" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="1.9"/><path d="M2.6 13.4 13.4 2.6" stroke="currentColor" stroke-width="1.6"/>'),
  move: icon('<path d="M8 1 5.8 3.6h4.4zM8 15l-2.2-2.6h4.4zM1 8l2.6-2.2v4.4zM15 8l-2.6-2.2v4.4z"/><rect x="7.2" y="3.4" width="1.6" height="9.2"/><rect x="3.4" y="7.2" width="9.2" height="1.6"/>'),
  height: icon('<path d="M8 1 4.8 4.8h6.4zM8 15l-3.2-3.8h6.4z"/><rect x="7.1" y="4.4" width="1.8" height="7.2"/>'),
  zoom: icon('<circle cx="6.8" cy="6.8" r="4.6" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="m10.2 10.2 4 4" stroke="currentColor" stroke-width="2"/><path d="M6.8 4.6V9M4.6 6.8H9" stroke="currentColor" stroke-width="1.4"/>'),
};
const LEFT = line('M10 3 5 8l5 5'), RIGHT = line('m6 3 5 5-5 5'), UP = line('m3 10 5-5 5 5');

const STICKS = {
  move: { x: ['lat-', 'lat+'], y: ['lon+', 'lon-'] },
  height: { y: ['alt+', 'alt-'] },
  zoom: { y: ['fov-', 'fov+'] },
};

const tbtn = (name, title, data) => `<button class="cam-t" title="${title}" ${data}>${ICONS[name]}</button>`;
const search = (n) => `data-do="search" data-n="${n}"`;
const arrow = (svg, title, data) => `<button class="cam-a" title="${title}" ${data}>${svg}</button>`;
const pick = (name) => `<button class="cam-pick" data-menu="${name}"><b data-shown="${name}">–</b>${UP}</button>`;
const pad = (id, kind, title) => `<div class="cam-pad" title="${title}"><div class="${kind}" data-stick="${id}"><i></i></div>${ICONS[id]}</div>`;

/** The next speed for << and >>: 1, 2, 4, 8, 16 each way, through paused and backwards. */
function nextSpeed(speed, dir) {
  if (!speed) return 2 * dir;
  if (Math.sign(speed) === dir) return Math.min(16, Math.abs(speed) * 2) * dir;
  return Math.abs(speed) > 1 ? speed / 2 : dir;
}

export const camera = {
  /** The chat is part of iRacing's panel: brings it back if it was hidden. True if it had to. */
  showPanel() {
    const cam = this.S?.st?.cam;
    if (this.bar && !(cam?.st & 8)) return false;
    this.S.send({ cmd: 'cam', do: 'tap', n: 'hide' });
    if (!(cam?.st & 8)) this.bar = true;
    return true;
  },
  id: 'w-camera',
  mount(root, S) {
    this.root = root; this.S = S; this.key = ''; this.shown = 0; this.bar = true;
    root.innerHTML = `
      <div class="card-h"><div class="ttl">Camera control</div></div>
      <div class="cam" hidden>
        <div class="cam-main">
          <div class="cam-trans">
            ${tbtn('back', 'Play backwards', 'data-do="speed" data-n="-1"')}
            ${tbtn('slow', 'Slow motion', 'data-slow-step')}
            <i></i>
            ${tbtn('start', 'Start of the replay', search(0))}
            ${tbtn('frameBack', 'Previous frame', search(6))}
            ${tbtn('rew', 'Rewind', 'data-step="-1"')}
            <button class="cam-t big" title="Pause / play" data-pause>${ICONS.pause}</button>
            ${tbtn('ff', 'Fast forward', 'data-step="1"')}
            ${tbtn('frame', 'Next frame', search(7))}
            ${tbtn('end', 'End of the replay', search(1))}
            <i></i>
            ${tbtn('incBack', 'Last incident', search(8))}
            ${tbtn('incNext', 'Next incident', search(9))}
            <i></i>
            ${tbtn('live', 'Back to live', 'data-live')}
            ${tbtn('hide', 'Hide the panel in iRacing', 'data-hide')}
            ${tbtn('reset', 'Reset camera', 'data-do="reset" data-n="0"')}
          </div>
          <div class="cam-picks">
            <div class="cam-chip lap">${arrow(LEFT, 'Previous lap', 'data-lap-step="-1"')}${pick('lap')}${arrow(RIGHT, 'Next lap', 'data-lap-step="1"')}</div>
            <div class="cam-chip">${arrow(LEFT, 'Previous camera', 'data-group="-1"')}${pick('group')}${arrow(RIGHT, 'Next camera', 'data-group="1"')}</div>
            <div class="cam-chip driver">${arrow(LEFT, 'Car behind on track', 'data-car="-1"')}${pick('driver')}${arrow(RIGHT, 'Car ahead on track', 'data-car="1"')}</div>
          </div>
        </div>
        <div class="cam-pads">
          ${pad('move', 'thumb', 'Move the camera')}${pad('height', 'fader', 'Height')}${pad('zoom', 'fader', 'Zoom')}
        </div>
      </div>
      <div class="cam-off">Camera control works with the driver out of the car.</div>`;
    this.box = root.querySelector('.cam');
    this.off = root.querySelector('.cam-off');
    this.pause = root.querySelector('[data-pause]');
    const send = (o) => S.send({ cmd: 'cam', ...o });

    // our own list, not a <select>: the system's can't take the look of the rest. On the body, so no card cuts it
    this.lists = {};
    this.menu = document.createElement('div');
    this.menu.className = 'cam-menu';
    this.menu.hidden = true;
    document.body.append(this.menu);
    this.menu.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      send({ do: this.menu.dataset.name, n: Number(b.dataset.v) });
      this.close();
    });
    addEventListener('pointerdown', (e) => { if (!e.target.closest('.cam-menu, .cam-pick')) this.close(); });
    addEventListener('keydown', (e) => { if (e.key === 'Escape') this.close(); });
    root.addEventListener('click', (e) => this.click(e.target.closest('button'), send));
    for (const el of root.querySelectorAll('[data-stick]')) this.stick(el, send);
  },

  click(b, send) {
    if (!b) return;
    if ('menu' in b.dataset) { this.open(b); return; }
    const S = this.S, d = b.dataset, cam = S.st?.cam ?? {}, speed = cam.speed ?? 0;
    const go = (n, slow = false) => {
      send({ do: 'speed', n, slow });
      this.paintSpeed(n, slow);
      this.shown = performance.now() + SHOWN_MS;
    };
    if ('do' in d) {
      if (d.do === 'speed') go(Number(d.n));
      else send({ do: d.do, n: Number(d.n) });
    } else if ('pause' in d) go(speed ? 0 : 1);
    else if ('step' in d) go(nextSpeed(cam.slow ? 1 : speed, Number(d.step)));
    else if ('slowStep' in d) {
      const next = cam.slow ? SLOW[SLOW.indexOf(speed) + 1] : SLOW[0];
      if (next) go(next, true); else go(1);
    } else if ('lapStep' in d) {
      if (!cam.race) send({ do: 'search', n: Number(d.lapStep) > 0 ? 5 : 4 });
      else if (cam.lap) send({ do: 'lap', n: cam.lap + Number(d.lapStep) });
    } else if ('live' in d) S.send({ cmd: 'replay_live' });
    else if ('hide' in d) {   // a key: iRacing doesn't say whether its panel is showing, so this is what was asked
      send({ do: 'tap', n: 'hide' });
      if (!(cam.st & 8)) this.bar = !this.bar;
    } else if ('group' in d) {
      const list = S.meta?.cameras ?? [], at = list.findIndex((g) => g.n === cam.g);
      const to = list[(at + Number(d.group) + list.length) % list.length];
      if (to) send({ do: 'group', n: to.n });
    } else if ('car' in d) {
      send({ do: 'tap', n: Number(d.car) > 0 ? 'car+' : 'car-' });   // iRacing's own: it goes by the track
    }
  },

  close() { this.menu.hidden = true; },

  open(b) {
    const name = b.dataset.menu, m = this.menu;
    if (!m.hidden && m.dataset.name === name) { this.close(); return; }
    const { list = [], cur } = this.lists[name] ?? {};
    m.dataset.name = name;
    m.innerHTML = list.map(([v, t]) => `<button data-v="${v}" class="${v === cur ? 'on' : ''}">${esc(t)}</button>`).join('');
    m.hidden = false;
    // body has `zoom`: the box comes in screen pixels, fixed positions are in zoomed ones
    const z = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--zoom')) || 1;
    const r = b.getBoundingClientRect(), high = m.offsetHeight * z, up = r.top - high - 4 >= 0;
    m.style.left = `${r.left / z}px`;
    m.style.top = `${(up ? r.top - high - 4 : r.bottom + 4) / z}px`;
    m.querySelector('.on')?.scrollIntoView({ block: 'center' });
  },

  cars() {
    const S = this.S;
    return [...S.st.cars].filter((c) => S.drivers[c.i]).sort((a, b) => (a.p ?? 999) - (b.p ?? 999));
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
      const rx = Math.max(1, (b.width - knob.offsetWidth) / 2), ry = Math.max(1, (b.height - knob.offsetHeight) / 2);
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

  paintSpeed(speed, slow) {
    const paused = !speed;
    if (this.paused !== paused) {
      this.paused = paused;
      this.pause.innerHTML = paused ? ICONS.play : ICONS.pause;
    }
    this.root.querySelector('[data-do="speed"]').classList.toggle('on', speed < 0);
    // how fast, in the button that does it: the icon gives way to the speed
    const show = (sel, name, text) => {
      const b = this.root.querySelector(sel);
      if (b.dataset.txt === text) return;
      b.dataset.txt = text;
      b.innerHTML = text ? `<span>${text}</span>` : ICONS[name];
      b.classList.toggle('on', !!text);
    };
    show('[data-step="1"]', 'ff', !slow && speed > 1 ? `${speed}×` : '');
    show('[data-step="-1"]', 'rew', !slow && speed < 0 ? `${-speed}×` : '');
    show('[data-slow-step]', 'slow', slow ? `1/${speed}` : '');
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
    const last = Math.max(cam.lap ?? 1, cam.total ?? 0);
    const key = JSON.stringify([groups.map((g) => g.n), group?.n, cam.i, cam.lap, cam.race, last, Object.keys(S.drivers).length]);
    if (key !== this.key) {
      this.key = key;
      const fill = (name, list, cur) => {
        this.lists[name] = { list, cur };
      };
      fill('group', groups.map((g) => [g.n, g.name]), cam.g);
      fill('driver', this.cars().map((c) => [c.i, `#${S.drivers[c.i].num} ${S.drivers[c.i].name}`]), cam.i);
      fill('lap', Array.from({ length: last }, (_, k) => [k + 1, `Lap ${k + 1}`]), cam.lap);
      this.root.querySelector('[data-shown="lap"]').textContent = !cam.race ? 'Lap' : cam.lap ? `Lap ${cam.lap}` : 'Lap –';   // outside a race iRacing's number isn't in the telemetry
      this.root.querySelector('[data-shown="group"]').textContent = group?.name ?? '–';
      this.root.querySelector('[data-shown="driver"]').textContent = S.drivers[cam.i] ? `#${S.drivers[cam.i].num} ${S.drivers[cam.i].name}` : '–';
    }
    if (performance.now() < this.shown) return;
    this.root.querySelector('[data-menu="lap"]').disabled = !cam.race;   // elsewhere each driver has laps of their own: only the arrows
    this.box.classList.toggle('scenic', !!(cam.st & 2));   // iRacing holds the view there: only the replay moves
    this.paintSpeed(cam.speed, cam.slow);
    this.root.querySelector('[data-hide]').classList.toggle('on', !this.bar || !!(cam.st & 8));
  },
};
