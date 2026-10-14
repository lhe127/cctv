// Execute the actual route dispatcher; a syntax-only check misses removed handlers.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../src/sentinel/web/app.js'), 'utf8');

async function loadRoute(route) {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      innerHTML: '', textContent: '', dataset: {},
      classList: {add() {}, toggle() {}},
      addEventListener() {}, focus() {}, append() {},
      querySelector: element, querySelectorAll: () => [],
    });
    return elements.get(id);
  }
  const cameras = [{id: 'gate', name: 'Gate', source_label: 'Webcam 0'}];
  const mounts = [];
  const sandbox = {
    document: {
      getElementById: element, querySelector: element, addEventListener() {},
      createElement: () => element('toast'),
    },
    window: {
      location: {pathname: `/${route}`, replace() { throw new Error('Unexpected redirect'); }},
      addEventListener() {}, setTimeout() {},
      SentinelResidentialMap: {async mount(canvas, options) { mounts.push({canvas, options}); }},
    },
    sessionStorage: {getItem: () => 'fixture-key'},
    CSS: {escape: value => value},
    fetch: async url => {
      assert.ok(['/api/v1/summary', '/api/v1/cameras'].includes(url), url);
      return {status: 200, ok: true, json: async () => url.endsWith('/cameras') ? cameras : {camera_count: 1}};
    },
  };
  vm.runInNewContext(source, sandbox, {filename: 'app.js'});
  await new Promise(setImmediate);
  const html = element('page-content').innerHTML;
  assert.doesNotMatch(html, /Could not load this workspace|is not defined/);
  return {html, mounts, cameras, element};
}

test('Robots route renders its existing disconnected state', async () => {
  const {html, mounts} = await loadRoute('robots');
  assert.match(html, /Robot operations/);
  assert.match(html, /No robots connected/);
  assert.equal(mounts.length, 0);
});

test('Map route mounts the renderer with camera data and updates the inspector', async () => {
  const {html, mounts, cameras, element} = await loadRoute('map');
  assert.match(html, /residential-map-canvas/);
  assert.match(html, /Site directory/);
  assert.equal(mounts.length, 1);
  assert.equal(mounts[0].canvas, element('#residential-map-canvas'));
  assert.equal(mounts[0].options.cameras, cameras);
  mounts[0].options.onSelect({id: 'pool', icon: 'P', type: 'Amenity', label: 'Swimming pool',
    description: 'Pool area', state: 'Site overview', facts: [['Label', '<unsafe>']]});
  assert.equal(element('#map-inspector-title').textContent, 'Swimming pool');
  assert.match(element('#map-inspector-facts').innerHTML, /&lt;unsafe&gt;/);
});
