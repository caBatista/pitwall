import { esc, lapTime, prefs, savePrefs } from './util.js';

/**
 * Race Events: for when the driver is out of the car. Two views:
 * Events: my session, whatever car is on camera; the Focused filter follows the car on camera instead.
 * Accidents: the ones that count, loss of control and contact (2x, 4x), and the cautions. The points are
 * iRacing's; a ~ marks an estimate, for when it hasn't published them yet (see events.py).
 * Every session of the event is in the same list, a break between one and the next.
 * A click on a row takes the sim's replay there, some seconds before, chase camera on the car.
 * Newest at the bottom, under a heading per lap. Nothing runs while the card is hidden.
 */
const GROUPS = { pass: 'Battles', inc: 'Incidents', pit: 'Pits', lap: 'Laps', flag: 'Flags' };
const GROUP_OF = {
  pass: 'pass', fight: 'pass', inc: 'inc', acc: 'inc', off: 'inc', stop: 'inc', out: 'inc', pit: 'pit', fast: 'lap', pb: 'lap', q: 'lap', inv: 'lap',
  pen: 'flag', finish: 'flag',
};
const SESSIONS = { practice: 'Practice', qualify: 'Qualify', race: 'Race', test: 'Test' };
const TAG = {
  pass: 'Pass', fight: 'Fight', inc: 'Inc', acc: 'Acc', off: 'Off', stop: 'Stop', out: 'Out', pit: 'Pit', fast: 'Fast', pb: 'PB', q: 'Lap', inv: 'Inv', pen: 'Flag', finish: 'Finish',
  caution: 'Caution', clear: 'Clear', red: 'Red',
};
const isAccident = (e) => e.k === 'acc' || (e.k === 'inc' && e.n >= 2) || e.k === 'caution' || e.k === 'clear' || e.k === 'red';
const PEN = { dq: 'disqualified', black: 'black flag', repair: 'meatball flag', warn: 'slow down' };
const MAX_ROWS = 300;   // the latest ones: nobody scrolls through more, and it keeps the page light

const clock = (t) => [t / 3600, (t / 60) % 60, t % 60].map((x) => String(Math.floor(x)).padStart(2, '0')).join(':');
const stint = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;

function line(S, e, ref) {
  const who = (i) => `<b>${esc(S.drivers[i]?.name ?? `Car ${i}`)}</b>`;
  switch (e.k) {
    case 'pass': return `${who(e.i)} passes ${who(e.j)}${e.p === 1 ? ' for the lead' : e.p ? ` for P${e.p}` : ''}`;
    case 'fight': return e.j === ref ? `${who(e.j)} defends from ${who(e.i)} <i>${e.d}s</i>` : `${who(e.i)} attacks ${who(e.j)} <i>${e.d}s</i>`;
    case 'inc': return `${who(e.i)} ${e.n >= 4 ? 'car contact' : e.n >= 2 ? 'lost control or contact' : 'off track'}${e.n >= 2 && e.j != null ? ` with ${who(e.j)}` : ''} <i>${e.n}x</i>`;
    case 'acc': {
      const what = e.est ? (e.j != null ? 'contact' : 'lost control') : e.x >= 4 ? 'car contact' : 'lost control or contact';
      return `${who(e.i)} ${what}${e.j != null ? ` with ${who(e.j)}` : ''} <i>${e.est ? '~' : ''}${e.x}x</i>`;
    }
    case 'off': return `${who(e.i)} off track`;
    case 'stop': return `${who(e.i)} stopped on track`;
    case 'out': return `${who(e.i)} left the track`;
    case 'pen': return `${who(e.i)} ${PEN[e.f] || e.f}`;
    case 'pit': return `${who(e.i)} pit stop <i>${stint(e.d)}</i>`;
    case 'fast': return `${who(e.i)} fastest lap of the class <i>${lapTime(e.v)}</i>`;
    case 'pb': return `${who(e.i)} personal best <i>${lapTime(e.v)}</i>`;
    case 'q': return `${who(e.i)} ${e.pole ? 'takes pole' : `P${e.p}`} <i>${lapTime(e.v)}</i>`;
    case 'inv': return `${who(e.i)} invalid lap`;
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
    this.root = root; this.S = S; this.drawn = ''; this.view = 'events'; this.solo = !!new URLSearchParams(location.search).get('w');
    prefs.evOff ??= [];   // groups switched off
    prefs.evWho ??= 'me';   // me | focus
    root.innerHTML = `
      <div class="card-h"><div class="ttl">Race events</div><div class="ctl">
        <div class="seg ev-view"><button data-view="events">Events</button><button data-view="accidents">Accidents</button></div>
      </div></div>
      <div class="ev-kinds"><div class="seg ev-who"><button data-who="me">Me</button><button data-who="focus">Focused</button></div>${Object.entries(GROUPS).map(([k, n]) => `<button data-group="${k}">${n}</button>`).join('')}</div>
      <div class="ev-body"></div>
      <div class="ev-live" hidden><span>Replay <b></b> behind live</span><button class="ghost-btn" data-live>Back to live</button></div>`;
    this.body = root.querySelector('.ev-body');
    this.live = root.querySelector('.ev-live');
    this.kinds = root.querySelector('.ev-kinds');
    root.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      const d = b.dataset;
      if (d.id) {
        this.on = b.id;
        S.send({ cmd: 'replay', id: Number(d.id) });
        this.body.querySelector('.ev.on')?.classList.remove('on');
        b.classList.add('on');
        return;
      }
      if ('live' in d) { this.on = null; S.send({ cmd: 'replay_live' }); return; }
      if (d.view) this.view = d.view;
      else if (d.who) { prefs.evWho = d.who; savePrefs(); }
      else if (d.group) { prefs.evOff = prefs.evOff.includes(d.group) ? prefs.evOff.filter((g) => g !== d.group) : [...prefs.evOff, d.group]; savePrefs(); } else return;
      this.update(S);
    });
  },

  list(S, ref) {
    const pick = this.view === 'accidents'
      ? isAccident
      : (e) => (e.i === ref || e.j === ref) && !prefs.evOff.includes(GROUP_OF[e.k]);
    return S.events.filter(pick).sort((a, b) => a.sn - b.sn || a.t - b.t || a.id - b.id).slice(-MAX_ROWS);
  },

  rows(S, ref) {
    let html = '', lap = null, sn = null;
    const acc = this.view === 'accidents';
    const list = this.list(S, ref);
    const several = new Set(list.map((e) => e.sn)).size > 1;
    for (const e of list) {
      if (e.sn !== sn) {
        sn = e.sn; lap = null;
        if (several) html += `<div class="ev-sess">${SESSIONS[e.sk] || esc(e.sk ?? '')}</div>`;
      }
      // the lap of the driver in the filter; lists saved before each car had its own only know mine (lap)
      const own = (who, lap) => lap ?? (who === S.st?.session?.player ? e.lap : null) ?? null;
      const mine = e.i === ref ? own(e.i, e.cl) : e.j === ref ? own(e.j, e.cj) : null;
      const at = acc ? own(e.i, e.cl) : mine ?? own(e.i, e.cl);
      if (!acc && mine > (lap ?? 0)) { lap = mine; html += `<div class="ev-lap">Lap ${lap}</div>`; }
      const color = S.classMap.get(S.drivers[e.i]?.cls)?.color;
      html += `<button id="ev${e.id}" class="ev ${tone(e, ref)} g-${GROUP_OF[e.k] || 'flag'} k-${e.k}${`ev${e.id}` === this.on ? ' on' : ''}" data-id="${e.id}"${color ? ` style="--cc:${color}"` : ''}>
        <em>${TAG[e.k] || ''}</em><span>${line(S, e, ref)}</span><time title="${clock(e.t)}">${at ? `L${at}` : clock(e.t)}</time></button>`;
    }
    return html;
  },

  update(S) {
    if (!S.st?.session || (!this.solo && !document.body.hasAttribute('data-out'))) return;
    const s = S.st.session;
    const ref = prefs.evWho === 'focus' ? S.st.me?.i : s.player ?? S.st.me?.i;
    const acc = this.view === 'accidents';
    for (const b of this.root.querySelectorAll('[data-view]')) b.classList.toggle('on', b.dataset.view === this.view);
    for (const b of this.root.querySelectorAll('[data-who]')) b.classList.toggle('on', b.dataset.who === prefs.evWho);
    for (const b of this.root.querySelectorAll('[data-group]')) b.classList.toggle('on', !prefs.evOff.includes(b.dataset.group));
    this.kinds.hidden = acc;
    const behind = s.behind > 3 ? s.behind : 0;
    this.live.hidden = !behind;
    if (behind) this.live.querySelector('b').textContent = clock(behind);

    const key = [S.eventsVer, this.view, prefs.evOff, ref].join('|');
    if (key === this.drawn) return;
    this.drawn = key;
    const atEnd = this.body.scrollHeight - this.body.scrollTop - this.body.clientHeight < 30;
    const html = this.rows(S, ref);
    const none = acc ? 'No incidents yet. They show up as they happen.'
      : `Nothing yet for ${esc(S.drivers[ref]?.name ?? 'this driver')}. Events show up as they happen.`;
    this.body.innerHTML = html || `<div class="ev-none">${none}</div>`;
    if (atEnd) this.body.scrollTop = this.body.scrollHeight;
  },
};
