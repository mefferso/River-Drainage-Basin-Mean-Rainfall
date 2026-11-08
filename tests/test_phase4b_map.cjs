const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const html=fs.readFileSync('reports/phase4b/geometry_review.html','utf8');
const scripts=[html.split('<script>')[1]?.split('</script>')[0]].filter(Boolean);
assert.equal(scripts.length,1,'expected one inline review script');
new vm.Script(scripts[0],{filename:'phase4b-geometry-review.html'});
for(const asset of [
 'historical/relationships/v1/source/Phase2_Forecast_Point_Crosswalk.json',
 'reports/phase4b/rfc_single_segments.geojson',
 'reports/phase4b/candidate_aggregates.geojson',
 'reports/phase4b/nldi_reference_geometries.geojson',
 'reports/phase4b/station_reconciliation.json',
 'reports/phase4b/station_reconciliation.csv',
 'reports/phase4b/topology_snapshot.json',
 'docs/PHASE4B_HISTORICAL_MAP_RECONSTRUCTION.md',
]) {
  if(asset.startsWith('historical/') || asset.startsWith('docs/'))
    assert.equal(fs.existsSync(asset),true,'missing map source '+asset);
}
for(const label of [
 '2018 RFC source segment','Routed RFC aggregate candidate',
 'Verified NLDI full upstream','Verified NLDI incremental',
  'All 543 RFC source segments',
 'Modern MRMS MAP is not interchangeable with legacy RFC MAP',
 'NOT ESTABLISHED','29 historical forecast points',
]) assert.ok(html.includes(label),'missing scientific map label: '+label);
for(const path of [
 'station_reconciliation.json','rfc_single_segments.geojson',
 'candidate_aggregates.geojson','nldi_reference_geometries.geojson',
]) assert.ok(html.includes(path),'missing map layer path '+path);
const crosswalk=JSON.parse(fs.readFileSync('historical/relationships/v1/source/Phase2_Forecast_Point_Crosswalk.json','utf8'));
assert.equal(crosswalk.length,29,'Phase 4B map must support all historical forecast points');
assert.ok(html.includes('source')&&html.includes('candidate')&&html.includes('incremental'));
console.log('Phase 4B review map syntax, 29-point inventory path, layers, and warnings OK');
