const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

class Element {
  constructor(tag = 'div', id = '') {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.dataset = {};
    this.style = {};
    this.className = '';
    this.value = '';
    this._text = '';
    this._html = '';
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  set innerHTML(value) { this._html = String(value); this.children = []; }
  get innerHTML() { return this._html; }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; }
  addEventListener(type, handler) { this.listeners[type] = handler; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name]; }
  click() { this.listeners.click?.({currentTarget: this, target: this}); }
  focus() { this.focused = true; }
}

const ids = ['hist-status', 'hist-title', 'hist-meta', 'hist-relationships', 'hist-chart', 'hist-head', 'hist-rows', 'hist-export', 'hist-retry'];
function fixture() {
  const elements = Object.fromEntries(ids.map(id => [id, new Element('div', id)]));
  const document = {
    getElementById(id) { return elements[id] || null; },
    createElement(tag) { return new Element(tag); },
    createElementNS(_ns, tag) { return new Element(tag); },
  };
  return {document, elements};
}

function mapPayload(nws, rows = []) {
  return {schema_version: 'historical-v1', nws_point_id: nws, map_events: rows,
    crest_relationships: [], quality_policy: 'B_historical_descriptive', legacy_method_status: 'unverified'};
}
function mapRow(id, map, date) {
  return {record_id: id, relationship_type: 'map_to_crest', historical_point_id: 'AMIL1', nws_point_id: 'AMIL1',
    dashboard_gage_id: '07375430', event_date: date, date_precision: 'day', map_inches: map, crest_feet: map + 10,
    tc_raw: null, tc_hours_confirmed: null, periods_rain_raw: null, source_workbook: 'study.xls', source_worksheet: 'Map',
    source_row: Number(id.slice(1)), source_file_sha256: 'abc', quality_tier: 'B', quality_limitations: ['LEGACY_DESCRIPTIVE_ONLY']};
}

async function main() {
  const source = fs.readFileSync('historical-ui.js', 'utf8');
  new vm.Script(source, {filename: 'historical-ui.js'});
  const ui = require('../historical-ui.js');
  const html = fs.readFileSync('index.html', 'utf8');
  assert.match(html, /historical-ui\.js/);
  assert.match(html, /renderHistoricalForUsGsGage/);
  assert.match(html, /historical-analysis/);
  assert.match(html, /@media\s*\(max-width:750px\)/);
  assert.match(html, /const retained=state\.latest\.gages\.some\(g=>g\.id===state\.selected\)/);
  assert.match(html, /\$\('period'\)\.addEventListener\('change',render\)/);
  assert.match(html, /\$\('wetThreshold'\)\.addEventListener\('change',render\)/);

  const crosswalk = [
    {usgs_site_id: '07375430', nws_point_id: 'AMIL1', display_name: 'Tangipahoa River near Amite'},
    {usgs_site_id: '02492343', nws_point_id: 'CREM6', display_name: 'East Hobolochitto Creek near Caesar'}
  ];
  const rows = [mapRow('R1', 1, '2001-01-01'), mapRow('R2', 3, '2002-02-02'), mapRow('R3', 1, '2003-03-03')];
  const pair = {relationship_id: 'OSYM6__KENL1', source_point_id_nws: 'OSYM6', target_point_id_nws: 'KENL1',
    source_point_name: 'Tangipahoa River at Osyka', target_point_name: 'Tangipahoa River near Kentwood',
    records: [{record_id: 'P1', event_date: '2004-04-04', date_precision: 'day', source_crest_feet: 8, target_crest_feet: 12,
      source_point_id_raw: 'OSYM6', target_point_id_raw: 'KENL1', quality_tier: 'B', lag_raw: null,
      source_workbook: 'pair.xls', source_worksheet: 'Pair', source_row: 4, quality_limitations: ['LEGACY_DESCRIPTIVE_ONLY']} ]};
  const f = fixture();
  const calls = [];
  const fetchFn = async url => {
    calls.push(url);
    return {ok: true, json: async () => url.includes('crosswalk') ? crosswalk : url.includes('CREM6') ? mapPayload('CREM6') : {...mapPayload('AMIL1', rows), crest_relationships: [pair]}};
  };
  const controller = ui.create({document: f.document, fetch: fetchFn, baseUrl: 'historical/relationships/v1/'});
  await controller.renderForGage('07375430');
  assert.match(f.elements['hist-status'].textContent, /3 historical descriptive records/);
  assert.match(f.elements['hist-title'].textContent, /Tangipahoa River near Amite/);
  assert.match(f.elements['hist-title'].textContent, /USGS 07375430 · NWS AMIL1/);
  assert.equal(f.elements['hist-rows'].children.length, 3);
  assert.equal(calls.filter(url => url.includes('/points/')).length, 1);
  assert.equal(f.elements['hist-relationships'].children.length, 2);
  const overlapping = f.elements['hist-chart'].children[0].children.filter(node => ['R1', 'R3'].includes(node.dataset.recordId));
  assert.deepEqual(overlapping.map(node => node.getAttribute('r')).sort(), ['10', '6']);

  const mapHeader = f.elements['hist-head'].children[0].children.find(node => node.dataset.sort === 'map_inches');
  mapHeader.children[0].click();
  assert.deepEqual(f.elements['hist-rows'].children.map(row => row.dataset.recordId), ['R1', 'R3', 'R2']);
  const point = f.elements['hist-chart'].children[0].children.find(node => node.dataset.recordId === 'R2');
  point.click();
  assert.equal(f.elements['hist-rows'].children.find(row => row.dataset.recordId === 'R2').className, 'selected');
  f.elements['hist-rows'].children.find(row => row.dataset.recordId === 'R1').click();
  assert.match(f.elements['hist-chart'].children[0].children.find(node => node.dataset.recordId === 'R1').getAttribute('class'), /selected/);
  const csv = ui.csvForRecords(rows, 'map');
  assert.match(csv, /record_id,event_date,date_precision,map_inches,crest_feet/);
  assert.match(csv, /R2,2002-02-02,day,3,13/);

  const pairButton = f.elements['hist-relationships'].children.find(button => button.textContent.includes('OSYM6') && button.textContent.includes('KENL1'));
  pairButton.click();
  assert.match(f.elements['hist-title'].textContent, /OSYM6/);
  assert.match(f.elements['hist-title'].textContent, /KENL1/);
  assert.match(f.elements['hist-status'].textContent, /1 historical descriptive records/);
  assert.equal(f.elements['hist-rows'].children[0].dataset.recordId, 'P1');
  assert.equal(f.elements['hist-chart'].children[0].children.some(node => node.textContent.includes('Source crest')) , true);
  assert.equal(f.elements['hist-chart'].children[0].children.some(node => node.textContent.includes('Target crest')) , true);
  await controller.refresh();
  assert.equal(f.elements['hist-rows'].children[0].dataset.recordId, 'P1');
  assert.match(f.elements['hist-title'].textContent, /OSYM6/);

  await controller.renderForGage('02492343');
  assert.match(f.elements['hist-status'].textContent, /No approved historical relationships/);
  assert.equal(f.elements['hist-rows'].children.length, 0);
  await controller.renderForGage('not-a-dashboard-gage');
  assert.match(f.elements['hist-status'].textContent, /No verified historical station match/);

  const stale = fixture();
  let finishFirst;
  let pointCalls = 0;
  const staleFetch = url => {
    if (url.includes('crosswalk')) return Promise.resolve({ok: true, json: async () => crosswalk});
    if (url.includes('AMIL1') && pointCalls++ === 0) return new Promise(resolve => { finishFirst = resolve; });
    return Promise.resolve({ok: true, json: async () => mapPayload('AMIL1', [mapRow('NEW', 4, '2004-04-04')])});
  };
  const staleController = ui.create({document: stale.document, fetch: staleFetch, baseUrl: 'historical/relationships/v1/'});
  const oldRequest = staleController.renderForGage('07375430');
  await new Promise(resolve => setImmediate(resolve));
  const newRequest = staleController.renderForGage('07375430');
  await newRequest;
  finishFirst({ok: true, json: async () => mapPayload('AMIL1', [mapRow('OLD', 1, '2001-01-01')])});
  await oldRequest;
  assert.deepEqual(stale.elements['hist-rows'].children.map(row => row.dataset.recordId), ['NEW']);

  console.log('Historical UI syntax and selection, sorting, synchronization, export, and stale-fetch tests passed');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
