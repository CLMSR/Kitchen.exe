const test = require('node:test');
const assert = require('node:assert/strict');

global.window = global;
require('../recipe-core.js');
require('../storage-core.js');

const core = global.KitchenRecipeCore;

test('normalizes case, accents, punctuation and common preparation words', () => {
  assert.equal(core.normalizeIngredient('  CHICKEN, freshly chopped! '), 'chicken');
  assert.equal(core.normalizeIngredient('PIMIENTÓN'), 'pimienton');
});

test('canonical URL strips tracking parameters and fragments', () => {
  assert.equal(core.canonicalUrl('https://Example.com/recipe/?utm_source=ig#steps'), 'https://example.com/recipe');
  assert.equal(core.canonicalUrl('javascript:alert(1)'), '');
});

test('ingredient matching uses word boundaries', () => {
  assert.equal(core.ingredientMatches('chicken breast with rice', 'chicken'), true);
  assert.equal(core.ingredientMatches('chickpeas and rice', 'chicken'), false);
});

test('invalid dates do not throw or produce invalid ISO values', () => {
  assert.equal(core.safeDateIso('not-a-date'), '');
  assert.equal(core.safeDateIso('2026-10-10T12:00:00Z'), '2026-10-10T12:00:00.000Z');
});

test('storage gracefully falls back on corrupt data and storage failures', () => {
  const values = new Map([['broken', '{not json'], ['kitchenExeTheme', 'dark']]);
  global.localStorage = {
    getItem: key => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, value)
  };
  assert.deepEqual(global.KitchenStorage.read('broken', []), []);
  assert.equal(global.KitchenStorage.read('kitchenExeTheme', 'light'), 'dark');
  assert.equal(global.KitchenStorage.write('kitchenExeSaved', [{ title: 'Soup' }]), true);
  assert.deepEqual(JSON.parse(values.get('kitchenExeSaved')), [{ title: 'Soup' }]);
});


test('parses recipe durations in ISO and human-readable formats', () => {
  assert.equal(core.durationToMinutes('PT1H30M'), 90);
  assert.equal(core.durationToMinutes('25 min'), 25);
  assert.equal(core.durationToMinutes('1h 15m'), 75);
  assert.equal(core.durationToMinutes('unknown'), 0);
});
