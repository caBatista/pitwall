// Run with: node --test tests/js   (pytest runs it too, see tests/test_calc_js.py)
import test from 'node:test';
import assert from 'node:assert/strict';
import { pitPlan } from '../../web/js/calc.js';

test('enough fuel: no stop', () => {
  const p = pitPlan(40, 2, 10, 1, 100, 5, 0.5);
  assert.equal(p.stops, 0);
  assert.equal(p.toGo, 20);
  assert.equal(p.spare, 20);
});

test('reserve can force a stop', () => {
  assert.equal(pitPlan(20, 2, 10, 0, 100, 5).stops, 0);
  assert.equal(pitPlan(20, 2, 10, 0.5, 100, 5).stops, 1);
});

test('the window ends on the last lap the tank completes', () => {
  // 2 laps of fuel from the start of lap 5: laps 5 and 6 complete, lap 7 doesn't
  assert.equal(pitPlan(4, 2, 30, 0, 100, 5, 0).last, 6);
  // halfway through lap 5, 2 laps of fuel: lap 6 completes, half of lap 7 doesn't
  assert.equal(pitPlan(4, 2, 30, 0, 100, 5, 0.5).last, 6);
  // 1.6 laps from 0.5: end of lap 5, end of lap 6 (2.1 reached)
  assert.equal(pitPlan(3.2, 2, 30, 0, 100, 5, 0.5).last, 6);
  // 0.4 laps of fuel from 0.5: this lap is the last one possible
  assert.equal(pitPlan(0.8, 2, 30, 0, 100, 5, 0.5).last, 5);
});

test('stopping on first still gets there with a full tank, one lap earlier does not', () => {
  const level = 20, avg = 2, laps = 30, tank = 45, lap = 3, pct = 0.25;
  const p = pitPlan(level, avg, laps, 0, tank, lap, pct);
  assert.equal(p.stops, 1);
  const after = (stopLap) => laps - (stopLap - lap + 1 - pct);   // laps still to do after that stop
  assert.ok(after(p.first) * avg <= tank + 1e-9);
  assert.ok(after(p.first - 1) * avg > tank);
  assert.ok((p.last - lap + 1 - pct) * avg <= level);
  assert.ok((p.last - lap + 2 - pct) * avg > level);
});

test('never before the next lap, unless it is the only one', () => {
  assert.equal(pitPlan(20, 2, 11, 0, 100, 5, 0).first, 6);
  assert.equal(pitPlan(1, 2, 11, 0, 100, 5, 0.5).first, 5);
});

test('a long race needs more stops', () => {
  const p = pitPlan(10, 2, 100, 0, 60, 1, 0);
  assert.equal(p.stops, 4);
  assert.ok(p.first <= p.last);
  assert.ok(p.add <= 60);
});

test('no average, no plan', () => {
  assert.equal(pitPlan(10, null, 10, 1, 60, 1), null);
  assert.equal(pitPlan(null, 2, 10, 1, 60, 1), null);
  assert.equal(pitPlan(10, 2, null, 1, 60, 1), null);
});
