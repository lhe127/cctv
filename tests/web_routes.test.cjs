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
      innerHTML: '', textContent: '', dataset: {},value:'all',
      classList: {add() {}, toggle() {}},
      addEventListener() {}, focus() {}, append() {},scrollIntoView() {},
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
      location: {pathname: `/${route}`,hash:'', replace() { throw new Error('Unexpected redirect'); }},
      addEventListener() {}, setTimeout() {},setInterval() {return 1;},clearInterval() {},
      SentinelResidentialMap: {async mount(canvas, options) { mounts.push({canvas, options});return {setAlerts() {},select() {}}; }},
    },
    sessionStorage: {getItem: () => 'fixture-key'},
    CSS: {escape: value => value},
    fetch: async url => {
      assert.ok(['/api/v1/summary', '/api/v1/cameras', '/api/v1/settings', '/api/v1/findings', '/api/v1/alerts', '/api/v1/alerts?status=pending'].includes(url), url);
      if(url.startsWith('/api/v1/alerts'))return {status:200,ok:true,json:async()=>[{id:'test-alert',status:'pending',description:'<unsafe>',camera_name:'Gate',created_at:'2026-10-15T00:00:00Z',start_seconds:0,end_seconds:3.5,map_position:null}]};
      if(url==='/api/v1/findings')return {status:200,ok:true,json:async()=>[]};
      if(url.endsWith('/settings'))return {status:200,ok:true,json:async()=>({prompt:'<safe prompt>',sample_fps:2,window_frames:8,max_new_tokens:96,preview_fps:5})};
      return {status: 200, ok: true, json: async () => url.endsWith('/cameras') ? cameras : {camera_count: 1}};
    },
  };
  vm.runInNewContext(source, sandbox, {filename: 'app.js'});
  await new Promise(setImmediate);
  const html = element('page-content').innerHTML;
  assert.doesNotMatch(html, /Could not load this workspace|is not defined/);
  return {html, mounts, cameras, element};
}

test('Robots route clearly identifies the virtual patrol', async () => {
  const {html, mounts} = await loadRoute('robots');
  assert.match(html, /Robot operations/);
  assert.match(html, /Simulation only/);
  assert.match(html, /No physical robot/);
  assert.equal(mounts.length, 0);
});

test('Map route mounts the renderer with camera data and updates the inspector', async () => {
  const {html, mounts, cameras, element} = await loadRoute('map');
  assert.match(html, /residential-map-canvas/);
  assert.match(html, /Site directory/);
  assert.match(html, /Not placed/);
  assert.match(html, /Plan coordinates/);
  assert.match(element('#map-pending-alerts').innerHTML,/&lt;unsafe&gt;/);
  assert.match(element('#map-pending-alerts').innerHTML,/Unplaced/);
  assert.equal(mounts.length, 1);
  assert.equal(mounts[0].canvas, element('#residential-map-canvas'));
  assert.equal(mounts[0].options.cameras, cameras);
  mounts[0].options.onSelect({id: 'pool', icon: 'P', type: 'Amenity', label: 'Swimming pool',
    description: 'Pool area', state: 'Site overview', facts: [['Label', '<unsafe>']]});
  assert.equal(element('#map-inspector-title').textContent, 'Swimming pool');
  assert.match(element('#map-inspector-facts').innerHTML, /&lt;unsafe&gt;/);
});

test('Alerts route renders escaped pending alerts and status actions', async () => {
  const {html,element}=await loadRoute('alerts');
  assert.match(html,/Danger alerts/);
  assert.match(element('#danger-alert-list').innerHTML,/&lt;unsafe&gt;/);
  assert.match(element('#danger-alert-list').innerHTML,/Mark resolved/);
  assert.match(element('#danger-alert-list').innerHTML,/Unplaced/);
});

test('Settings route loads escaped prompt and bounded analysis controls', async () => {
  const {html,element}=await loadRoute('settings');
  assert.match(html,/Administrator access/);
  assert.match(element('#settings-editor').innerHTML,/&lt;safe prompt&gt;/);
  assert.match(element('#settings-editor').innerHTML,/setting-sample_fps/);
  assert.match(element('#settings-editor').innerHTML,/setting-window_frames/);
});
