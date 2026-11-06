const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8');
const scripts=[...html.matchAll(/<script(?:\\s+[^>]*)?>([\\s\\S]*?)<\\/script>/g)]
 .map(m=>m[1]).filter(Boolean);
assert.equal(scripts.length,1,'Expected one inline dashboard script');
new vm.Script(scripts[0],{filename:'index.html inline script'});
for(const id of ['source','areaMode','period','gage','map','whole','wet','status']){
 assert.match(html,new RegExp('id="'+id+'"'),id+' must exist');
}
assert.match(html,/Incremental reach/);
assert.match(html,/Entire historical event/);
console.log('Dashboard script syntax and required controls passed');
