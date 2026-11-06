import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULTS, DEFAULTS_PORTRAIT, WIDGETS, addItem, boardLayout, gridArea, gridOf, layoutFor, moveItem, resizeItem, rowTracks, saveLayout, savedLayout, sessionKey, shapeOf } from '../../web/js/layout.js';

const { cols: COLS, rows: ROWS } = gridOf('landscape');

const at = (items, id) => items.find((i) => i.id === id);
const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
const clean = (items) => items.every((a, n) => a.x >= 0 && a.y >= 0 && a.x + a.w <= COLS && a.y + a.h <= ROWS && items.slice(n + 1).every((b) => !overlap(a, b)));

test('the default of every session is a valid board', () => {
  for (const list of Object.values(DEFAULTS)) assert.ok(clean(list));
});

test('nothing saved: no layout, the board keeps its CSS', () => {
  assert.equal(savedLayout({}, 'race'), null);
  assert.equal(savedLayout(undefined, 'race'), null);
  assert.deepEqual(layoutFor({}, 'race'), DEFAULTS.race);
});

test('the shape of the screen', () => {
  assert.equal(shapeOf(1920, 1080), 'landscape');
  assert.equal(shapeOf(3440, 1440), 'landscape');
  assert.equal(shapeOf(1080, 1920), 'portrait');
});

test('portrait: every session has a valid board of its own', () => {
  const g = gridOf('portrait');
  for (const list of Object.values(DEFAULTS_PORTRAIT)) {
    assert.ok(list.every((a, n) => a.x + a.w <= g.cols && a.y + a.h <= g.rows && list.slice(n + 1).every((b) => !overlap(a, b))));
    assert.equal(savedLayout({ 'race:portrait': list }, 'race', 'portrait').length, list.length);   // none under its smallest size
  }
});

test('each shape keeps its own layouts', () => {
  const saved = {};
  saveLayout(saved, 'race', 'portrait', [{ id: 'map', x: 0, y: 0, w: 6, h: 8 }]);
  assert.equal(savedLayout(saved, 'race', 'landscape'), null);
  assert.equal(savedLayout(saved, 'race', 'portrait').length, 1);
});

test('landscape without a layout stays with the CSS, portrait has none to stay with', () => {
  assert.equal(boardLayout({}, 'race', 'landscape'), null);
  assert.deepEqual(boardLayout({}, 'race', 'portrait'), DEFAULTS_PORTRAIT.race);
});

test('portrait: moves and sizes inside its own grid', () => {
  const next = moveItem([{ id: 'fuel', x: 0, y: 0, w: 3, h: 6 }], 'fuel', 99, 99, 'portrait');
  assert.deepEqual([next[0].x, next[0].y], [9, 18]);
  const big = resizeItem([{ id: 'map', x: 0, y: 0, w: 6, h: 6 }], 'map', 99, 99, 'portrait');
  assert.deepEqual([big[0].w, big[0].h], [12, 24]);
  const added = addItem([], 'standings', 'portrait');
  assert.ok(added[0].x + added[0].w <= 12 && added[0].y + added[0].h <= 24);
});

test('race over is a session of its own', () => {
  assert.equal(sessionKey('race', true), 'over');
  assert.equal(sessionKey('race', false), 'race');
});

test('out of the car is one screen, whatever the session', () => {
  assert.equal(sessionKey('practice', false, true), 'out');
  assert.equal(sessionKey('race', true, true), 'out');
});

test('an empty board is a choice, not a missing one', () => {
  assert.deepEqual(savedLayout({ race: [] }, 'race'), []);
});

test('moving onto another widget: it makes room and nothing overlaps', () => {
  const next = moveItem(DEFAULTS.race, 'fuel', 19, 8);
  assert.deepEqual([at(next, 'fuel').x, at(next, 'fuel').y], [19, 8]);
  assert.ok(clean(next));
  assert.deepEqual([at(next, 'weather').x, at(next, 'weather').y], [14, 8]);
});

test('moving past the edge stops at the edge', () => {
  const next = moveItem([{ id: 'fuel', x: 0, y: 0, w: 5, h: 4 }], 'fuel', 99, 99);
  assert.deepEqual([at(next, 'fuel').x, at(next, 'fuel').y], [COLS - 5, ROWS - 4]);
});

test('no room for the one pushed: the move does not happen', () => {
  assert.equal(moveItem(DEFAULTS.race, 'map', 0, 0), null);
});

test('resizing respects the smallest size and the grid', () => {
  const small = resizeItem([{ id: 'map', x: 0, y: 0, w: 10, h: 4 }], 'map', 1, 1);
  assert.deepEqual([at(small, 'map').w, at(small, 'map').h], [WIDGETS.map.mw, WIDGETS.map.mh]);
  const big = resizeItem([{ id: 'map', x: 4, y: 6, w: 10, h: 4 }], 'map', 99, 99);
  assert.deepEqual([at(big, 'map').w, at(big, 'map').h], [COLS - 4, ROWS - 6]);
});

test('resizing over a neighbour moves it', () => {
  const next = resizeItem([{ id: 'map', x: 0, y: 0, w: 10, h: 4 }, { id: 'fuel', x: 10, y: 0, w: 5, h: 4 }], 'map', 12, 4);
  assert.ok(clean(next));
  assert.equal(at(next, 'map').w, 12);
});

test('a new widget goes where it fits, at the smallest size if it must', () => {
  const free = addItem([{ id: 'standings', x: 0, y: 0, w: 14, h: 12 }], 'relative');
  assert.deepEqual(at(free, 'relative'), { id: 'relative', x: 14, y: 0, w: 10, h: 4 });
  const tight = addItem([{ id: 'standings', x: 0, y: 0, w: 20, h: 12 }], 'map');
  assert.equal(at(tight, 'map').w, WIDGETS.map.mw);
  assert.equal(addItem([{ id: 'standings', x: 0, y: 0, w: 24, h: 12 }], 'map'), null);
});

test('a damaged file loses only what makes no sense', () => {
  const list = savedLayout({ race: [
    { id: 'map', x: 0, y: 0, w: 10, h: 4 },
    { id: 'map', x: 12, y: 0, w: 10, h: 4 },      // twice
    { id: 'gone', x: 0, y: 6, w: 10, h: 4 },      // no longer exists
    { id: 'fuel', x: 2, y: 2, w: 5, h: 4 },       // on top of the map
    { id: 'weather', x: 22, y: 0, w: 5, h: 4 },   // off the grid
    { id: 'relative', x: 0, y: 6, w: 1, h: 1 },   // too small
  ] }, 'race');
  assert.deepEqual(list.map((i) => i.id), ['map']);
});

test('grid area', () => {
  assert.equal(gridArea({ x: 14, y: 4, w: 10, h: 4 }), '5 / 15 / span 4 / span 10');
});

test('camera control: half the screen, at the lower right out of the car, and it only moves', () => {
  assert.equal(WIDGETS.camera.name, 'Camera control');
  assert.deepEqual(at(DEFAULTS.out, 'camera'), { id: 'camera', x: 12, y: 10, w: 12, h: 2 });
  assert.ok(!at(DEFAULTS.race, 'camera'));
  const free = [{ id: 'standings', x: 0, y: 0, w: 12, h: 12 }];
  const items = addItem(free, 'camera');
  assert.deepEqual(at(items, 'camera'), { id: 'camera', x: 12, y: 0, w: 12, h: 2 });
  assert.equal(resizeItem(items, 'camera', 20, 8, 'landscape'), items);
  assert.deepEqual(at(savedLayout({ out: [{ id: 'camera', x: 14, y: 9, w: 10, h: 3 }] }, 'out', 'landscape'), 'camera'), { id: 'camera', x: 12, y: 9, w: 12, h: 2 });
});

test('the rows of a fixed widget add up to its height, the others share the rest', () => {
  const tracks = rowTracks([{ id: 'standings', x: 0, y: 0, w: 12, h: 12 }, { id: 'camera', x: 12, y: 10, w: 12, h: 2 }], gridOf('landscape')).split(' 3');
  assert.equal(tracks.length, 3);
  assert.ok(rowTracks([{ id: 'standings', x: 0, y: 0, w: 12, h: 12 }], gridOf('landscape')).endsWith('minmax(0, 1fr)'));
  assert.ok(rowTracks([{ id: 'camera', x: 12, y: 10, w: 12, h: 2 }], gridOf('landscape')).endsWith('33.5px 33.5px'));
});
