import { esc, lapTime, prefs, savePrefs } from './util.js';
import { camera } from './camera.js';
import { driverMenu } from './drivers.js';

/**
 * Race Events: for when the driver is out of the car. My session, whatever car is on camera; the
 * Focused filter follows the car on camera instead.
 * Every session of the event is in the same list, a break between one and the next.
 * A click on a row takes the sim's replay there, some seconds before, chase camera on the car.
 * Newest at the bottom, under a heading per lap. Nothing runs while the card is hidden.
 * The races of the last 30 days can be read again (a click only goes to the replay of the race in the sim).
 */
const GROUPS = { pass: 'Battles', inc: 'Incidents', pit: 'Pits', lap: 'Bests', laps: 'Laps', flag: 'Flags' };
const GROUP_OF = {
  pass: 'pass', fight: 'pass', inc: 'inc', off: 'inc', stop: 'inc', out: 'inc', pit: 'pit', lapx: 'laps', fast: 'lap', pb: 'lap', q: 'lap',
  pen: 'flag', finish: 'flag',
};
const SESSIONS = { practice: 'Practice', qualify: 'Qualify', race: 'Race', test: 'Test' };
const TAG = {
  pass: 'Pass', fight: 'Fight', inc: 'Inc', off: 'Off', stop: 'Stop', out: 'Out', pit: 'Pit', lapx: 'Lap', fast: 'Fast', pb: 'PB', q: 'Lap', pen: 'Flag', finish: 'Finish',
  caution: 'Caution', clear: 'Clear', red: 'Red',
};
const INC = (n) => (n >= 4 ? 'car contact' : n >= 2 ? 'lost control or contact' : 'off track');
const PEN = { dq: 'disqualified', black: 'black flag', repair: 'meatball flag', warn: 'slow down' };
const MAX_ROWS = 300;   // the latest ones: nobody scrolls through more, and it keeps the page light

const clock = (t) => [t / 3600, (t / 60) % 60, t % 60].map((x) => String(Math.floor(x)).padStart(2, '0')).join(':');
const stint = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;

function line(C, e, ref) {
  const who = (i) => `<b>${esc(C.drivers[i]?.name ?? `Car ${i}`)}</b>`;
  switch (e.k) {
    case 'pass': return `${who(e.i)} passes ${who(e.j)}${e.p === 1 ? ' for the lead' : e.p ? ` for P${e.p}` : ''}`;
    case 'fight': return e.j === ref ? `${who(e.j)} defends from ${who(e.i)} <i>${e.d}s</i>` : `${who(e.i)} attacks ${who(e.j)} <i>${e.d}s</i>`;
    case 'inc': return `${who(e.i)} ${e.n0 != null ? `${INC(e.n0)}, then ${INC(e.n)}` : INC(e.n)}${e.n >= 2 && e.j != null ? ` with ${who(e.j)}` : ''} <i>${e.n}x</i>`;
    case 'off': return `${who(e.i)} off track`;
    case 'stop': return `${who(e.i)} stopped on track`;
    case 'out': return `${who(e.i)} left the track`;
    case 'pen': return `${who(e.i)} ${PEN[e.f] || e.f}`;
    case 'lapx': return `${who(e.i)} lap ${e.cl}${e.d ? ` <i>${lapTime(e.d)}</i>` : ''}`;
    case 'pit': return `${who(e.i)} pit stop <i>${stint(e.d)}</i>`;
    case 'fast': return `${who(e.i)} fastest lap of the class <i>${lapTime(e.v)}</i>`;
    case 'pb': return `${who(e.i)} personal best <i>${lapTime(e.v)}</i>`;
    case 'q': return `${who(e.i)} ${e.pole ? 'takes pole' : `P${e.p}`} <i>${lapTime(e.v)}</i>`;
    case 'finish': return `${who(e.i)} takes the flag${e.p ? ` in P${e.p}` : ''}`;
    case 'caution': return 'Caution';
    case 'clear': return 'Caution over';
    case 'red': return 'Red flag';
    default: return esc(e.k);
  }
}

// green when it is good news for the reference driver, red when it is bad
const tone = (e, car) => (e.k === 'pass' ? (e.i === car ? 'gain' : 'loss') : e.k === 'fight' ? (e.j === car ? 'gain' : '') : '');

export const events = {
  id: 'w-events',
  mount(root, S) {
    this.root = root; this.S = S; this.drawn = ''; this.solo = !!new URLSearchParams(location.search).get('w');
    prefs.evOff ??= [];   // groups switched off
    prefs.evWho ??= 'me';   // me | focus
    root.innerHTML = `
      <div class="card-h"><div class="ttl">Race events</div></div>
      <div class="ev-kinds"><div class="seg ev-who"><button data-who="me">Me</button><button data-who="focus">Focused</button></div>${Object.entries(GROUPS).map(([k, n]) => `<button data-group="${k}">${n}</button>`).join('')}</div>
      <div class="ev-body"></div>
      <div class="ev-live" hidden><span>Replay <b></b> behind live</span><button class="ghost-btn" data-live>Back to live</button></div>`;
    this.body = root.querySelector('.ev-body');
    this.live = root.querySelector('.ev-live');
    this.kinds = root.querySelector('.ev-kinds');
    // right click: message the other driver of the event, as on the standings
    root.addEventListener('contextmenu', (e) => {
      const ev = S.events?.find((x) => `ev${x.id}` === e.target.closest('.ev')?.id);
      if (!ev) return;
      const me = S.st?.session?.player, who = [ev.j, ev.i].find((i) => i != null && i !== me);
      if (who == null) return;
      e.preventDefault();
      driverMenu(e, S, who, () => camera.showPanel());
    });
    root.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      const d = b.dataset;
      if (d.id) {
        this.on = b.id;
        const [, sn, t] = /^L(\d+)-/.test(d.id) ? [0, Number(d.sn), Number(d.t)] : [];
        if (sn != null) S.send({ cmd: 'replay_lap', sn, t, i: Number(d.i) });   // a lap: from its start
        else S.send({ cmd: 'replay', id: Number(d.id) });
        this.body.querySelector('.ev.on')?.classList.remove('on');
        b.classList.add('on');
        return;
      }
      if ('live' in d) { this.on = null; S.send({ cmd: 'replay_live' }); return; }
      if (d.who) { prefs.evWho = d.who; savePrefs(); }
      else if (d.group) { prefs.evOff = prefs.evOff.includes(d.group) ? prefs.evOff.filter((g) => g !== d.group) : [...prefs.evOff, d.group]; savePrefs(); } else return;
      this.update(S);
    });
  },

  /** Every lap of the driver, from when each began (the start of the next one gives its time): a row each. */
  laps(C, ref) {
    if (prefs.evOff.includes('laps')) return [];
    const out = [];
    for (const [sn, cars] of Object.entries(C.evLaps || {})) {
      const starts = Object.entries(cars?.[ref] || {}).map(([n, t]) => [Number(n), t]).sort((a, b) => a[0] - b[0]);
      starts.forEach(([n, t], k) => {
        const next = starts[k + 1];
        out.push({ id: `L${sn}-${n}`, k: 'lapx', sn: Number(sn), t, i: ref, cl: n, d: next && next[0] === n + 1 ? next[1] - t : null });
      });
    }
    return out;
  },

  list(C, ref) {
    const pick = (e) => (e.i === ref || e.j === ref) && !prefs.evOff.includes(GROUP_OF[e.k]);
    return [...C.events, ...this.laps(C, ref)].filter(pick).sort((a, b) => a.sn - b.sn || a.t - b.t || a.id - b.id).slice(-MAX_ROWS);
  },

  // nothing happened, or something did and the filters leave it out: not the same thing to say
  empty(C, ref) {
    const name = esc(C.drivers[ref]?.name ?? 'this driver');
    const hidden = C.events.filter((e) => e.i === ref || e.j === ref).length;
    if (!hidden) return `Nothing yet for ${name}. Events show up as they happen.`;
    return `No events with these filters. ${hidden} ${hidden === 1 ? 'event' : 'events'} of ${name} hidden.`;
  },

  rows(S, ref) {
    let html = '', lap = null, sn = null;
    const player = S.st?.session?.player;
    const list = this.list(S, ref);
    const several = new Set(list.map((e) => e.sn)).size > 1;
    for (const e of list) {
      if (e.sn !== sn) {
        sn = e.sn; lap = null;
        if (several) html += `<div class="ev-sess">${SESSIONS[e.sk] || esc(e.sk ?? '')}</div>`;
      }
      // the lap of the driver in the filter; lists saved before each car had its own only know mine (lap)
      const own = (who, lap) => lap ?? (who === player ? e.lap : null) ?? null;
      const mine = e.i === ref ? own(e.i, e.cl) : e.j === ref ? own(e.j, e.cj) : null;
      const at = mine ?? own(e.i, e.cl);
      if (mine > (lap ?? 0)) { lap = mine; html += `<div class="ev-lap">Lap ${lap}</div>`; }
      const color = S.classMap.get(S.drivers[e.i]?.cls)?.color;
      html += `<button id="ev${e.id}" class="ev ${tone(e, ref)} g-${GROUP_OF[e.k] || 'flag'} k-${e.k}${`ev${e.id}` === this.on ? ' on' : ''}" data-id="${e.id}"${e.k === 'lapx' ? ` data-sn="${e.sn}" data-t="${e.t}" data-i="${e.i}"` : ''}${color ? ` style="--cc:${color}"` : ''}>
        <em>${TAG[e.k] || ''}</em><span>${line(S, e, ref)}</span><time title="${clock(e.t)}">${at ? `L${at}` : clock(e.t)}</time></button>`;
    }
    return html;
  },

  update(S) {
    if (!S.st?.session || (!this.solo && !document.body.hasAttribute('data-out'))) return;
    const s = S.st.session;
    const ref = prefs.evWho === 'focus' ? S.st.me?.i : s.player ?? S.st.me?.i;
    for (const b of this.root.querySelectorAll('[data-who]')) b.classList.toggle('on', b.dataset.who === prefs.evWho);
    for (const b of this.root.querySelectorAll('[data-group]')) b.classList.toggle('on', !prefs.evOff.includes(b.dataset.group));
    const behind = s.behind > 3 ? s.behind : 0;
    this.live.hidden = !behind;
    if (behind) this.live.querySelector('b').textContent = clock(behind);

    const key = [S.eventsVer, prefs.evOff, ref].join('|');
    if (key === this.drawn) return;
    this.drawn = key;
    const atEnd = this.body.scrollHeight - this.body.scrollTop - this.body.clientHeight < 30;
    const html = this.rows(S, ref);
    this.body.innerHTML = html || `<div class="ev-none">${this.empty(S, ref)}</div>`;
    if (atEnd) this.body.scrollTop = this.body.scrollHeight;
  },
};
