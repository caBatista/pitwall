import { lapTime, fmt } from './util.js';

/**
 * Laptime log (test sessions, in place of the standings): my laps, newest first,
 * with the delta to the previous lap and to my session best, the track
 * temperature and the fuel left / used on that lap. Same look as the standings.
 */
export const laplog = {
  id: 'w-laplog',
  mount(root) {
    root.innerHTML = `
      <div class="card-h"><div class="ttl"><i></i>Lap times</div></div>
      <div class="ll-best"><small>Personal session best</small><b id="ll-pb">-:--.---</b><span id="ll-tt"></span></div>
      <div class="s-body" id="ll-body"></div>`;
    this.body = root.querySelector('#ll-body');
    this.pb = root.querySelector('#ll-pb');
    this.tt = root.querySelector('#ll-tt');
    this.last = '';
  },

  update(S) {
    const st = S.st;
    if (!st || st.session.kind !== 'test') return;
    const laps = st.me.laps || [];
    const best = laps.reduce((m, l) => (l.time && (!m || l.time < m) ? l.time : m), null);
    this.pb.textContent = best ? lapTime(best) : '-:--.---';
    this.tt.textContent = st.wx.track != null ? `Track ${fmt.temp(st.wx.track).toFixed(1)}${fmt.tempU()}` : '';

    const sgn = (d, digits = 3) => (d == null ? '–' : (d > 0 ? '+' : '') + d.toFixed(digits));
    const cls = (d) => (d == null ? '' : d < 0 ? 'good' : d > 0 ? 'bad' : '');   // my own laps: quicker is good
    const head = `<div class="ghead lrow"><div class="r">Lap</div><div class="r">Time</div><div class="r">Delta</div>
      <div class="r">PS best</div><div class="r">Temp</div><div class="r">Fuel left</div><div class="r">Fuel used</div></div>`;
    const rows = laps.map((l, k) => {
      const prev = laps[k + 1];
      const d = l.time && prev?.time ? l.time - prev.time : null;
      const pb = l.time && best ? l.time - best : null;
      return `<div class="rrow lrow ${l.time === best ? 'pbrow' : ''}">
        <div class="rpos">${l.lap}</div>
        <div class="t ${l.time === best ? 'cb' : ''}">${l.time ? lapTime(l.time) : '-:--.---'}</div>
        <div class="dl ${cls(d)}">${sgn(d)}</div>
        <div class="dl ${pb > 0 ? 'bad' : ''}">${l.time === best ? '–' : sgn(pb)}</div>
        <div class="t">${l.temp == null ? '–' : fmt.temp(l.temp).toFixed(1) + fmt.tempU()}</div>
        <div class="t">${l.fuel == null ? '–' : fmt.vol(l.fuel).toFixed(1) + ' ' + fmt.volU()}</div>
        <div class="t">${l.used == null ? '–' : fmt.vol(l.used).toFixed(2) + ' ' + fmt.volU()}</div>
      </div>`;
    }).join('');
    const html = head + (rows || '<div class="map-note"><b>No laps yet</b>Complete a lap to start the log.</div>');
    if (html !== this.last) { this.body.innerHTML = html; this.last = html; }
  },
};
