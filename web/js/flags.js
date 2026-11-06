import { prefs } from './util.js';
import { FLAGS as NAMES, flagCfg } from './flagcfg.js';

/**
 * The flag the driver is under, as the colour of the background behind the whole board.
 * How long each one shows comes from Settings > Race flags (flagcfg.js); the checkered counts from the driver's
 * own line. The pulse is a step every 50 ms and not a CSS
 * animation, which would run at the monitor's rate (see Desempenho in CLAUDE.md).
 */
const TEST_CHECKERED = 6000;
const SLOW = 2400, FAST = 900;   // ms a pulse
const PULSE = { black: FAST, white: SLOW, meatball: SLOW, blue: SLOW, checkered: SLOW, debris: SLOW, green: FAST, yellow: FAST };
const STEP = 50, LOW = 0.45, FADE_IN = 300;

const bg = document.getElementById('flag-bg'), bar = document.getElementById('flag-test');
let real = null, testing = null, timer = 0, pulse = 0, shown = null, ending = false;

function hide() {
  clearTimeout(timer);
  clearInterval(pulse);
  shown = null;
  bg.style.opacity = '';   // the transition in app.css fades it out
  bg.classList.remove('on');
  if (testing) { testing = null; paint(); }
}

function show(flag) {
  if (!flag) { hide(); return; }
  clearTimeout(timer);
  clearInterval(pulse);
  shown = flag;
  bg.dataset.f = flag;
  bg.classList.add('on');
  const period = PULSE[flag], t0 = performance.now();
  const level = () => {
    const t = performance.now() - t0, wave = period ? LOW + (1 - LOW) * (0.5 + 0.5 * Math.cos((2 * Math.PI * t) / period)) : 1;
    bg.style.opacity = (Math.min(1, t / FADE_IN) * wave).toFixed(3);
  };
  level();
  if (period) pulse = setInterval(level, STEP);
  else setTimeout(level, FADE_IN);
  const lasts = flag === 'checkered' ? (testing ? TEST_CHECKERED : 0) : flagCfg(prefs).items[flag].secs * 1000;
  if (lasts) timer = setTimeout(hide, lasts);
}

function paint() {
  for (const b of bar.children) b.classList.toggle('on', b.dataset.flag === testing);
}

/** The flag in this frame; home: the driver has taken their checkered. */
export function setFlag(flag, home) {
  const cfg = flagCfg(prefs);   // Settings > Race flags; the test buttons still work
  if (!cfg.on || (flag && !cfg.items[flag].on)) flag = null;
  if (flag !== real) {
    real = flag;
    ending = false;
    if (!testing) show(flag);
  }
  if (flag === 'checkered' && home && !ending && !testing && shown === 'checkered') {
    ending = true;
    clearTimeout(timer);
    if (cfg.items.checkered.secs) timer = setTimeout(hide, cfg.items.checkered.secs * 1000);
  }
}

/** Buttons to see each one: on the simulator and in dev mode. */
export function flagButtons(on) {
  bar.hidden = !on;
  if (bar.children.length) return;
  bar.innerHTML = Object.entries(NAMES).map(([k, f]) => `<button data-flag="${k}" title="${f.name}"><i></i></button>`).join('');
  bar.addEventListener('click', (e) => {
    const k = e.target.closest('[data-flag]')?.dataset.flag;
    if (!k) return;
    testing = testing === k ? null : k;
    paint();
    show(testing ?? real);
  });
}
