const assert = require('node:assert/strict');
const HistoricalUI = require('../historical-ui.js');

class Element {
  constructor(tag='div', id='') {
    this.tagName=tag.toUpperCase(); this.id=id; this.children=[]; this.attributes={};
    this.listeners={}; this.dataset={}; this.className=''; this.disabled=false;
    this.value=''; this.style={}; this._text='';
  }
  set textContent(v) { this._text=String(v); this.children=[]; }
  get textContent() { return this._text+this.children.map(x=>x.textContent).join(''); }
  appendChild(c) { this.children.push(c); return c; }
  replaceChildren(...children) { this.children=children; }
  setAttribute(k,v) { this.attributes[k]=String(v); }
  getAttribute(k) { return this.attributes[k]; }
  addEventListener(type,fn) { this.listeners[type]=fn; }
  click() { this.listeners.click?.({target:this,currentTarget:this}); }
}

function fixture() {
  const ids=['hist-status','hist-title','hist-meta','hist-relationships','hist-source-choices',
    'hist-chart','hist-head','hist-rows','hist-export','hist-retry'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element('div',id)]));
  const document={getElementById:id=>elements[id]||null,
    createElement:tag=>new Element(tag),
    createElementNS:(_,tag)=>new Element(tag)};
  return {elements,document};
}
const legacy={
  schema_version:'historical-v1',nws_point_id:'AMIL1',crest_relationships:[],
  map_events:[{record_id:'L1',quality_tier:'B',event_date:'2026-01-01',
    date_precision:'day',map_inches:2.1,crest_feet:12.1,
    source_workbook:'legacy.xls',source_worksheet:'Sheet1',source_row:4}]
};
const crosswalk=[{nws_point_id:'AMIL1',usgs_site_id:'07375430',display_name:'Tangipahoa River near Amite'}];
const approved={schema_version:1,events:[
  {event_id:'R1',nwsli:'AMIL1',map_inches:2.7,crest_feet:12.3,
    validation_status:'SCIENCE_APPROVED',qpe_product:'MRMS Pass2',
    crest_time_utc:'2026-01-02T14:00:00Z',rain_start_utc:'2026-01-01T00:00:00Z',
    rain_end_utc:'2026-01-02T00:00:00Z',source_url:'https://example.invalid/source'},
  {event_id:'R2',nwsli:'AMIL1',map_inches:3.5,crest_feet:15.6,
    validation_status:'PROVISIONAL_NOT_SCIENCE_APPROVED',qpe_product:'MRMS Pass2',
    crest_time_utc:'2026-01-04T14:00:00Z',rain_start_utc:'2026-01-03T00:00:00Z',
    rain_end_utc:'2026-01-04T00:00:00Z'}
]};

async function scenario(sourceData) {
  const f=fixture();
  const fetcher=async url=>{
    if(url.includes('crosswalk'))return {ok:true,json:async()=>crosswalk};
    if(url.includes('/points/'))return {ok:true,json:async()=>legacy};
    if(sourceData)return {ok:true,json:async()=>sourceData};
    return {ok:false,status:404};
  };
  const app=HistoricalUI.create({document:f.document,fetch:fetcher});
  await app.renderForGage('07375430');
  return f.elements;
}
(async()=>{
  const onlyLegacy=await scenario(null);
  const controls=onlyLegacy['hist-source-choices'].children;
  const buttons=controls.filter(x=>x.tagName==='BUTTON');
  assert.equal(buttons.length,3);
  assert.equal(buttons[0].disabled,false);
  assert.equal(buttons[1].disabled,true);
  assert.equal(buttons[2].disabled,true);
  assert.equal(onlyLegacy['hist-rows'].children.length,1);
  buttons[2].click();
  assert.equal(onlyLegacy['hist-rows'].children.length,1,'disabled both must do nothing');

  const withApproved=await scenario(approved);
  const toggles=withApproved['hist-source-choices'].children.filter(x=>x.tagName==='BUTTON');
  assert.ok(toggles.every(x=>!x.disabled));
  toggles[2].click();
  assert.equal(withApproved['hist-rows'].children.length,2,'both contains only legacy and approved');
  const circles=withApproved['hist-chart'].children[0].children.filter(x=>x.tagName==='CIRCLE');
  assert.equal(circles.length,2);
  assert.equal(circles.filter(x=>x.getAttribute('class').includes('reconstructed')).length,1);
  const table=withApproved['hist-rows'].children.map(x=>x.dataset.recordId);
  assert.deepEqual(table.sort(),['L1','reconstruction:R1']);
  toggles[1].click();
  assert.equal(withApproved['hist-rows'].children.length,1);
  assert.equal(withApproved['hist-rows'].children[0].dataset.recordId,'reconstruction:R1');
  console.log('Approved/provisional reconstruction source gate, source toggle and scatterplot tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
