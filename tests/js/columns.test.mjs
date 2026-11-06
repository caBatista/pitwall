import test from 'node:test';
import assert from 'node:assert/strict';
import { CLASS_HEAD, FOOT, HEADER, STAND, classDefault, colName, driverName, footDefault, footFit, headerDefault, hiddenIn, migrateStand, optOf, orderOf, shownIn, standCols, standDefault, standFit, standGrid, standHead, standNeed, viewSession } from '../../web/js/columns.js';

const TODAY = 'pos,pg,make,flag,name,sr,ir,tyre,int,gap,last,best,d1,d2,d3,status';
const GRID = '72px 22px 40px 22px minmax(110px, 1fr) 52px 84px 26px 58px 58px 70px 70px 38px 38px 38px 54px';

test('by default the columns are the ones the board always had', () => {
  const cols = standCols(standDefault(), 'race');
  assert.equal(cols.join(), TODAY);
  assert.equal(standGrid(cols, standDefault(), false), GRID);
});

test('number, gained and brand take the width of the old car column', () => {
  assert.equal(32 + 6 + 22 + 6 + 40, 106);
});

test('nothing saved yet: the defaults', () => {
  assert.equal(standCols(migrateStand(undefined), 'race').join(), TODAY);
});

test('race over shows the results, and it can be changed like any session', () => {
  const cfg = standDefault();
  assert.equal(standCols(cfg, 'over').join(), 'pos,pg,make,flag,name,sr,ir,best,status');
  cfg.hide.gap = [];
  assert.ok(standCols(cfg, 'over').includes('gap'));
  assert.ok(standGrid(standCols(standDefault(), 'over'), standDefault(), true).includes('80px'));
});

test('every session can hide a column on its own', () => {
  for (const s of ['test', 'practice', 'qualify', 'race', 'out']) {
    const cfg = { ...standDefault(), hide: { tyre: [s] } };
    assert.ok(!standCols(cfg, s).includes('tyre'), s);
    assert.ok(standCols(cfg, s === 'race' ? 'out' : 'race').includes('tyre'), s);
  }
});

test('the results win over the garage, for what is shown', () => {
  assert.equal(viewSession('race', true, true), 'over');
  assert.equal(viewSession('practice', false, true), 'out');
  assert.equal(viewSession('qualify', false, false), 'qualify');
});

test('the driver name never hides', () => {
  assert.ok(standCols({ ...standDefault(), hide: { name: ['race'] } }, 'race').includes('name'));
});

test('the tags live in the driver column, they are not columns', () => {
  const cols = standCols(standDefault(), 'race');
  assert.ok(!cols.includes('pit') && !cols.includes('out'));
  assert.ok(shownIn(standDefault(), STAND, 'race').includes('pit'));
  assert.ok(hiddenIn({ hide: { pit: ['race'] } }, STAND, 'pit', 'race'));
});

test('the number tucks under the position only right after it', () => {
  assert.ok(standGrid(['pos', 'name'], standDefault(), false).startsWith('72px'));
  assert.ok(standGrid(['pos', 'name'], { ...standDefault(), opt: { pos: { num: false } } }, false).startsWith('38px'));
});

test('options: defaults, and a bad value is ignored', () => {
  assert.equal(optOf(standDefault(), STAND, 'last', 'dec'), 3);
  assert.equal(optOf({ opt: { last: { dec: 1 } } }, STAND, 'last', 'dec'), 1);
  assert.equal(optOf({ opt: { last: { dec: 9 } } }, STAND, 'last', 'dec'), 3);
  assert.equal(optOf({ opt: { gap: { dec: 0 } } }, STAND, 'gap', 'dec'), 0);
  assert.deepEqual(optOf({}, STAND, 'status', 'off'), []);
  assert.equal(optOf({ opt: { ir: { gain: false } } }, STAND, 'ir', 'gain'), false);
});

test('delta: how many laps', () => {
  const cols = (n) => standCols({ ...standDefault(), opt: { delta: { laps: n } } }, 'race').filter((k) => /^d\d/.test(k));
  assert.deepEqual(cols(1), ['d1']);
  assert.deepEqual(cols(5), ['d1', 'd2', 'd3', 'd4', 'd5']);
});

test('iRating without the gain and the tyre as text change the width', () => {
  const cfg = { ...standDefault(), opt: { ir: { gain: false }, tyre: { show: 'text' } } };
  assert.ok(standGrid(['ir', 'tyre'], cfg, false) === '52px 30px');
});

test('a file from before: car splits in three, its choices stay', () => {
  const old = { order: ['gap', 'car', 'name'], hide: { car: ['qualify'], tyre: ['race'] }, deltas: 1 };
  const cfg = migrateStand(old);
  assert.deepEqual(orderOf(cfg, STAND).slice(0, 6), ['gap', 'pg', 'make', 'name', 'out', 'pit']);
  assert.ok(hiddenIn(cfg, STAND, 'make', 'qualify') && hiddenIn(cfg, STAND, 'tyre', 'race') && hiddenIn(cfg, STAND, 'tyre', 'over'));
  assert.equal(optOf(cfg, STAND, 'delta', 'laps'), 1);
  assert.equal(migrateStand(cfg), cfg);
});

test('the tags stay under the driver name, wherever it or they were', () => {
  const order = orderOf({ order: ['out', 'gap', 'name', 'pos', 'pit'] }, STAND);
  assert.deepEqual(order.slice(0, 5), ['gap', 'name', 'out', 'pit', 'pos']);
});

test('every way of writing a name', () => {
  const n = 'Caio Araujo Batista';
  assert.equal(driverName(n, 'full'), 'Caio Araujo Batista');
  assert.equal(driverName(n, 'first-last'), 'Caio Batista');
  assert.equal(driverName(n, 'FIRST-LAST'), 'CAIO BATISTA');
  assert.equal(driverName(n, 'f-last'), 'C. Batista');
  assert.equal(driverName(n, 'first-l'), 'Caio B.');
  assert.equal(driverName(n, 'f-LAST'), 'C. BATISTA');
  assert.equal(driverName(n, 'FIRST-l'), 'CAIO B.');
  assert.equal(driverName(n, 'first-m-last'), 'Caio A Batista');
});

test('the number iRacing adds goes away unless asked for', () => {
  assert.equal(driverName('Laurent Vidal2', 'first-last'), 'Laurent Vidal');
  assert.equal(driverName('Laurent Vidal2', 'full', true), 'Laurent Vidal2');
  assert.equal(driverName('Laurent Vidal2', 'f-last', true), 'L. Vidal2');
});

test('a name of one word or a car has nothing to shorten', () => {
  assert.equal(driverName('Laurent', 'f-last'), 'Laurent');
  assert.equal(driverName('Laurent', 'FIRST-LAST'), 'LAURENT');
  assert.equal(driverName('Laurent', 'first-m-last'), 'Laurent');
  assert.equal(driverName('', 'full'), '');
});

test('name format: the default is the name as it comes, a bad value too', () => {
  assert.equal(optOf({}, STAND, 'name', 'format'), 'full');
  assert.equal(optOf({ opt: { name: { format: 'nope' } } }, STAND, 'name', 'format'), 'full');
  assert.equal(optOf({ opt: { name: { format: 'f-last' } } }, STAND, 'name', 'format'), 'f-last');
});

test('an old or damaged order keeps working', () => {
  const order = orderOf({ order: ['gap', 'gone', 'gap', 'pos'] }, STAND);
  assert.deepEqual(order.slice(0, 2), ['gap', 'pos']);
  assert.equal(order.length, Object.keys(STAND).length);
});

test('it all fits in a 1080p panel, nothing is dropped', () => {
  const cols = standCols(standDefault(), 'race');
  assert.equal(standNeed(cols, standDefault(), false), 948);
  assert.deepEqual(standFit(cols, standDefault(), false, 978).dropped, []);
});

test('too narrow: the least important go first, position and name stay', () => {
  const cols = standCols(standDefault(), 'race');
  const a = standFit(cols, standDefault(), false, 910);
  assert.deepEqual(a.dropped, ['d3']);
  assert.ok(standNeed(a.cols, standDefault(), false) <= 910);
  const b = standFit(cols, standDefault(), false, 100);
  assert.deepEqual(b.cols, ['pos', 'name']);
});

test('no measure yet: nothing dropped', () => {
  assert.deepEqual(standFit(standCols(standDefault(), 'race'), standDefault(), false, 0).dropped, []);
});

test('names of what did not fit', () => {
  assert.equal(colName('d3'), 'Delta 3');
  assert.equal(colName('tyre'), 'Tyre');
});

test('class header: name over the first columns, deltas under one title', () => {
  const h = standHead(standCols(standDefault(), 'race'));
  assert.equal(h.lead, 7);
  assert.deepEqual(h.titles.map((t) => [t.title, t.span]), [['Tyre', 1], ['Int', 1], ['Gap', 1], ['Last', 1], ['Fastest', 1], ['Delta', 3], ['Flag', 1]]);
});

test('class header: a column moved to the right gets its own title', () => {
  const h = standHead(['pos', 'name', 'gap', 'ir']);
  assert.equal(h.lead, 2);
  assert.deepEqual(h.titles.map((t) => t.title), ['Gap', 'iR']);
});

test('class header default: drivers and SOF, as always', () => {
  assert.deepEqual(shownIn(classDefault(), CLASS_HEAD, 'race'), ['drivers', 'sof']);
});

test('footer default: what it always showed in each session', () => {
  const six = ['pos', 'lap', 'last', 'best', 'ir', 'inc'];
  assert.deepEqual(shownIn(footDefault(), FOOT, 'race'), six);
  assert.deepEqual(shownIn(footDefault(), FOOT, 'practice'), ['pos', 'lap', 'last', 'best']);
  assert.deepEqual(shownIn(footDefault(), FOOT, 'over'), ['pos', 'lap', 'best', 'ir', 'inc']);
});

test('footer: what does not fit goes from the end', () => {
  const f = footFit(['pos', 'lap', 'last', 'best'], 300);
  assert.deepEqual(f.items, ['pos', 'lap', 'last']);
  assert.deepEqual(f.dropped, ['best']);
  assert.deepEqual(footFit(['pos'], 0).dropped, []);
});

test('header default: as it always was, the SOF out of a test session', () => {
  assert.deepEqual(orderOf(headerDefault(), HEADER), ['brand', 'series', 'track', 'clock', 'gap', 'sof', 'conn']);
  assert.ok(hiddenIn(headerDefault(), HEADER, 'sof', 'test') && !hiddenIn(headerDefault(), HEADER, 'sof', 'race'));
});
