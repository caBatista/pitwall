import { esc, lapTime, prefs, savePrefs } from './util.js';

/**
 * Race Events: for when the driver is out of the car. Two views:
 * Events: the session of the reference driver, whoever that is at the moment.
 * Accidents: everybody's incidents as the telemetry shows them (off track, stopped, left the track, my
 * own incident points) and the cautions. iRacing gives nobody else's incident points.
 * A click on a row takes the sim's replay there, some seconds before, with the camera on the car.
 * Newest at the bottom, under a heading per lap. Nothing runs while the card is hidden.
 */
const GROUPS = { pass: 'Battles', inc: 'Incidents', pit: 'Pits', lap: 'Laps', flag: 'Flags' };
const GROUP_OF = {
  pass: 'pass', fight: 'pass', inc: 'inc', off: 'inc', stop: 'inc', out: 'inc', pit: 'pit', fast: 'lap', pb: 'lap', q: 'lap', inv: 'lap',
  pen: 'flag', finish: 'flag',
};
const TABS = { practice: 'Practice', qualify: 'Qualify', race: 'Race', test: 'Test' };
const TAG = {
  pass: 'Pass', inc: 'Inc', off: 'Off', stop: 'Stop', out: 'Out', pit: 'Pit', fast: 'Fast', pb: 'PB', q: 'Lap', inv: 'Inv', pen: 'Flag', finish: 'Finish',
  caution: 'Caution', clear: 'Clear', red: 'Red',
};
const ACCIDENT = new Set(['inc', 'off', 'stop', 'out', 'caution', 'clear', 'red']);
const PEN = { dq: 'disqualified', black: 'black flag', repair: 'meatball flag', warn: 'slow down' };
const MAX_ROWS = 300;   // the latest ones: nobody scrolls through more, and it keeps the page light

const clock = (t) => [t / 3600, (t / 60) % 60, t % 60].map((x) => String(Math.floor(x)).padStart(2, '0')).join(':');
const stint = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;

function line(S, e, ref) {
  const who = (i) => `<b>${esc(S.drivers[i]?.name ?? `Car ${i}`)}</b>`;
  switch (e.k) {
    case 'pass': return `${who(e.i)} passes ${who(e.j)}${e.p === 1 ? ' for the lead' : e.p ? ` for P${e.p}` : ''}`;
    case 'fight': return e.j === ref ? `${who(e.j)} defends from ${who(e.i)} <i>${e.d}s</i>` : `${who(e.i)} attacks ${who(e.j)} <i>${e.d}s</i>`;
    case 'inc': return `${who(e.i)} +${e.n}x incident${e.j != null ? `, near ${who(e.j)}` : ''} <i>${e.total}x</i>`;
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
    this.root = root; this.S = S; this.drawn = ''; this.tab = null; this.view = 'events'; this.solo = !!new URLSearchParams(location.search).get('w');
    prefs.evOff ??= [];   // groups switched off
    root.innerHTML = `
      <div class="card-h"><div class="ttl">Race events</div><div class="ctl">
        <div class="ev-tabs seg" hidden></div>
        <div class="seg ev-view"><button data-view="events">Events</button><button data-view="accidents">Accidents</button></div>
      </div></div>
      <div class="ev-kinds">${Object.entries(GROUPS).map(([k, n]) => `<button data-group="${k}">${n}</button>`).join('')}</div>
      <div class="ev-body"></div>
      <div class="ev-live" hidden><span>Replay <b></b> behind live</span><button class="ghost-btn" data-live>Back to live</button></div>`;
    this.body = root.querySelector('.ev-body');
    this.tabs = root.querySelector('.ev-tabs');
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
      if (d.tab) this.tab = Number(d.tab);
      else if (d.view) this.view = d.view;
      else if (d.group) { prefs.evOff = prefs.evOff.includes(d.group) ? prefs.evOff.filter((g) => g !== d.group) : [...prefs.evOff, d.group]; savePrefs(); } else return;
      this.update(S);
    });
  },

  list(S, ref) {
    const pick = this.view === 'accidents'
      ? (e) => ACCIDENT.has(e.k)
      : (e) => (e.i === ref || e.j === ref) && !prefs.evOff.includes(GROUP_OF[e.k]);
    return S.events.filter((e) => e.sn === this.shown && pick(e)).sort((a, b) => a.t - b.t || a.id - b.id).slice(-MAX_ROWS);
  },

  rows(S, ref) {
    let html = '', lap = null;
    for (const e of this.list(S, ref)) {
      if (e.lap > (lap ?? 0)) { lap = e.lap; html += `<div class="ev-lap">Lap ${lap}</div>`; }
      const color = S.classMap.get(S.drivers[e.i]?.cls)?.color;
      html += `<button id="ev${e.id}" class="ev ${tone(e, ref)} g-${GROUP_OF[e.k] || 'flag'} k-${e.k}${`ev${e.id}` === this.on ? ' on' : ''}" data-id="${e.id}"${color ? ` style="--cc:${color}"` : ''}>
        <em>${TAG[e.k] || ''}</em><span>${line(S, e, ref)}</span><time>${clock(e.t)}</time></button>`;
    }
    return html;
  },

  update(S) {
    if (!S.st?.session || (!this.solo && !document.body.hasAttribute('data-out'))) return;
    const s = S.st.session, ref = S.st.me?.i;
    const sessions = new Map(S.events.map((e) => [e.sn, e.sk]));
    sessions.set(s.num, s.kind);
    if (this.current !== s.num) { this.current = s.num; this.tab = null; }   // a new session: follow it
    this.shown = this.tab ?? s.num;

    const tabs = sessions.size > 1 ? [...sessions].sort((a, b) => a[0] - b[0]) : [];
    const tabKey = tabs.join() + this.shown;
    if (tabKey !== this.tabKey) {
      this.tabKey = tabKey;
      this.tabs.hidden = !tabs.length;
      this.tabs.innerHTML = tabs.map(([n, k]) => `<button data-tab="${n}" class="${n === this.shown ? 'on' : ''}">${TABS[k] || k}</button>`).join('');
    }
    const acc = this.view === 'accidents';
    for (const b of this.root.querySelectorAll('[data-view]')) b.classList.toggle('on', b.dataset.view === this.view);
    for (const b of this.root.querySelectorAll('[data-group]')) b.classList.toggle('on', !prefs.evOff.includes(b.dataset.group));
    this.kinds.hidden = acc;
    const behind = s.behind > 3 ? s.behind : 0;
    this.live.hidden = !behind;
    if (behind) this.live.querySelector('b').textContent = clock(behind);

    const key = [S.eventsVer, this.shown, this.view, prefs.evOff, ref].join('|');
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
