#!/usr/bin/env python3
"""Full-network IHABBS-vs-NLDI inventory. Spatial associations are NOT legacy MAP approval."""
import csv,hashlib,json,tarfile,tempfile
from datetime import datetime,timezone
from pathlib import Path
import geopandas as gpd
from shapely.geometry import shape,Point
from pyproj import Geod
GEOD=Geod(ellps='WGS84'); SQMI=2589988.110336
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/phase4a'
OUT.mkdir(parents=True,exist_ok=True)
def area(g):
    return abs(GEOD.geometry_area_perimeter(g)[0])/SQMI if g is not None and not g.is_empty else 0.0
def geo(path):
    f=json.loads(path.read_text())['features']
    assert len(f)==26,(path,len(f))
    result={str(x['properties']['id']):shape(x['geometry']) for x in f}
    assert len(result)==26 and all(v.is_valid for v in result.values())
    return result
def writetable(path,rows):
    if not rows:return
    with path.open('w',newline='',encoding='utf-8') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
up=geo(ROOT/'data/basins.geojson'); inc=geo(ROOT/'data/reaches.geojson')
gages=json.loads((ROOT/'config/gages.json').read_text())
cross=json.loads((ROOT/'historical/relationships/v1/source/Phase2_Forecast_Point_Crosswalk.json').read_text())
assert len(gages)==26 and len(cross)==29
archive=ROOT/'b_lmrfc.tar.gz'
if not archive.exists():raise FileNotFoundError('Official LMRFC archive required; no synthetic RFC comparisons')
with tempfile.TemporaryDirectory() as tmp:
    target=Path(tmp)
    with tarfile.open(archive,'r:gz') as tar:
        for x in tar.getmembers():
            if not (target/x.name).resolve().is_relative_to(target.resolve()) or x.issym() or x.islnk():
                raise ValueError('Unsafe NOAA archive')
        tar.extractall(target,filter='data')
    shp=list(target.rglob('*.shp'))
    if len(shp)!=1:raise ValueError(f'Expected one shapefile, got {shp}')
    source_frame=gpd.read_file(shp[0])
    source_crs=source_frame.crs.to_string() if source_frame.crs else None
    frame=source_frame.to_crs('EPSG:4326')
    attrs=[str(c) for c in frame.columns if c!='geometry']
    rows=[]; candidates=[]; used=set()
    for item in cross:
        token=item['canonical_nws_id']
        sid=str(item.get('existing_dashboard_usgs_id') or '')
        confirmed=str(item.get('usgs_site_id_confirmed') or '')
        verified=bool(sid and sid==confirmed and sid in up)
        a=up[sid] if verified else None;b=inc[sid] if verified else None
        if verified:used.add(sid)
        lat=item.get('latitude');lon=item.get('longitude')
        pt=Point(float(lon),float(lat)) if lat is not None and lon is not None else None
        matching=[]
        for index,row in frame.iterrows():
            g=row.geometry
            if g is None or g.is_empty:continue
            props={name:str(row[name]) for name in attrs}
            exact=token in [value.strip().upper() for value in props.values()]
            contains=bool(pt is not None and g.covers(pt))
            intersects=bool(a is not None and g.intersects(a))
            if not (exact or contains or intersects):continue
            same=area(g.intersection(a)) if a is not None else 0
            union=area(g.union(a)) if a is not None else 0
            incr_i=area(g.intersection(b)) if b is not None else 0
            incr_u=area(g.union(b)) if b is not None else 0
            r={'nwsli':token,'rfc_feature':str(index),'exact_nwsli_attribute':exact,'outlet_inside':contains,
                'overlap_upstream':intersects,'rfc_area_sqmi':round(area(g),3),
                'upstream_intersection_sqmi':round(same,3),
                'full_iou_pct':round(100*same/union,3) if union else '',
                'incremental_iou_pct':round(100*incr_i/incr_u,3) if incr_u else '',
                'rfc_minus_full_sqmi':round(area(g.difference(a)),3) if a is not None else '',
                'full_minus_rfc_sqmi':round(area(a.difference(g)),3) if a is not None else '',
                'attributes_json':json.dumps(props,sort_keys=True),
                'scientific_status':'UNVERIFIED_CANDIDATE'}
            matching.append(r)
        matching.sort(key=lambda x:(not x['exact_nwsli_attribute'],not x['outlet_inside'],-(x['full_iou_pct'] or 0)))
        candidates.extend(matching)
        top=matching[0] if matching else None
        rows.append({'historical_id':item['historical_point_id'],'canonical_nwsli':token,
            'station':item.get('official_nws_name',''),'dashboard_usgs':sid if verified else '',
            'verified_dashboard_join':verified,'lat':lat or '','lon':lon or '',
            'upstream_sqmi':round(area(a),3) if a is not None else '',
            'incremental_sqmi':round(area(b),3) if b is not None else '',
            'incremental_fraction_pct':round(100*area(b)/area(a),2) if a is not None and area(a) else '',
            'rfc_candidates':len(matching),'rfc_exact_attribute_matches':sum(x['exact_nwsli_attribute'] for x in matching),
            'rfc_outlet_containing':sum(x['outlet_inside'] for x in matching),
            'leading_rfc_feature':top['rfc_feature'] if top else '',
            'leading_rfc_sqmi':top['rfc_area_sqmi'] if top else '',
            'leading_full_iou_pct':top['full_iou_pct'] if top else '',
            'leading_incremental_iou_pct':top['incremental_iou_pct'] if top else '',
            'legacy_map_geometry_approved':False,
            'review_status':'NO_RFC_CANDIDATE' if not matching else 'CANDIDATES_REQUIRING_MODEL_DEFINITION'})
    for x in gages:
        sid=str(x['id'])
        if sid in used:continue
        a=up[sid];b=inc[sid]
        spatial=[]
        for index, row in frame.iterrows():
            geom=row.geometry
            if geom is None or geom.is_empty or not geom.intersects(a):continue
            props={name:str(row[name]) for name in attrs}
            intersection=area(geom.intersection(a)); total=area(geom.union(a))
            int_inc=area(geom.intersection(b)); total_inc=area(geom.union(b))
            contains=geom.covers(Point(float(x['lon']),float(x['lat'])))
            spatial.append({'nwsli':'UNMAPPED_USGS:'+sid,'rfc_feature':str(index),
                'exact_nwsli_attribute':False,'outlet_inside':contains,'overlap_upstream':True,
                'rfc_area_sqmi':round(area(geom),3),'upstream_intersection_sqmi':round(intersection,3),
                'full_iou_pct':round(100*intersection/total,3) if total else '',
                'incremental_iou_pct':round(100*int_inc/total_inc,3) if total_inc else '',
                'rfc_minus_full_sqmi':round(area(geom.difference(a)),3),
                'full_minus_rfc_sqmi':round(area(a.difference(geom)),3),
                'attributes_json':json.dumps(props,sort_keys=True),
                'scientific_status':'SPATIAL_ONLY_NO_VERIFIED_HISTORICAL_JOIN'})
        spatial.sort(key=lambda item:(not item['outlet_inside'],-(item['full_iou_pct'] or 0)))
        candidates.extend(spatial)
        top=spatial[0] if spatial else None
        rows.append({'historical_id':'','canonical_nwsli':'','station':x['name'],
            'dashboard_usgs':sid,'verified_dashboard_join':False,'lat':x['lat'],'lon':x['lon'],
            'upstream_sqmi':round(area(a),3),'incremental_sqmi':round(area(b),3),
            'incremental_fraction_pct':round(100*area(b)/area(a),2) if area(a) else '',
            'rfc_candidates':len(spatial),'rfc_exact_attribute_matches':0,
            'rfc_outlet_containing':sum(v['outlet_inside'] for v in spatial),
            'leading_rfc_feature':top['rfc_feature'] if top else '',
            'leading_rfc_sqmi':top['rfc_area_sqmi'] if top else '',
            'leading_full_iou_pct':top['full_iou_pct'] if top else '',
            'leading_incremental_iou_pct':top['incremental_iou_pct'] if top else '',
            'legacy_map_geometry_approved':False,'review_status':'DASHBOARD_GAGE_WITHOUT_HISTORICAL_JOIN_SPATIAL_ONLY'})
    exact_features=[]
    for index, feature in frame.iterrows():
        values={k:str(feature[k]).strip().upper() for k in attrs}
        matching=[x for x in cross if x['canonical_nws_id']==values.get('NWSID')]
        if not matching:continue
        from shapely.geometry import mapping
        exact_features.append({'type':'Feature','properties':{
            'nwsli':values['NWSID'],'rfc_index':str(index),
            'rfc_name':str(feature.get('DESCRIPT','')),
            'rfc_fcstgroup':str(feature.get('FCSTGROUP','')),
            'area_sqmi':round(area(feature.geometry),3),
            'scientific_status':'UNVERIFIED_LEGACY_MAP_GEOMETRY'},
            'geometry':mapping(feature.geometry)})
    (OUT/'rfc_exact_nwsli_polygons.geojson').write_text(json.dumps({
        'type':'FeatureCollection','features':exact_features},separators=(',',':')))
    spatial_features=[]
    for entry in rows:
        if entry['historical_id'] or not entry['leading_rfc_feature']:continue
        idx=int(entry['leading_rfc_feature'])
        feature=frame.loc[idx]
        spatial_features.append({'type':'Feature','properties':{
            'usgs':entry['dashboard_usgs'],'rfc_index':str(idx),
            'rfc_nwsid':str(feature.get('NWSID','')),
            'rfc_name':str(feature.get('DESCRIPT','')),
            'area_sqmi':round(area(feature.geometry),3),
            'scientific_status':'SPATIAL_ONLY_NO_VERIFIED_HISTORICAL_JOIN'},
            'geometry':mapping(feature.geometry)})
    (OUT/'rfc_dashboard_only_spatial_candidates.geojson').write_text(json.dumps({
        'type':'FeatureCollection','features':spatial_features},separators=(',',':')))
    writetable(OUT/'network_inventory.csv',rows)
    writetable(OUT/'rfc_candidates.csv',candidates)
    summary={'archive_url':'https://www.nohrsc.noaa.gov/data/vector/master/b_lmrfc.tar.gz',
        'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_crs':source_crs,'export_crs':'EPSG:4326',
        'rfc_features':len(frame),'rfc_fields':attrs,'exact_nwsli_polygon_features':len(exact_features),'dashboard_only_candidate_polygons':len(spatial_features),'historical_points':len(cross),
        'dashboard_gages':len(gages),'matched_historical_gages':len(used),
        'dashboard_only_gages':len(gages)-len(used),'inventory_rows':len(rows),
        'candidate_rows':len(candidates),'with_candidates':sum(bool(x['rfc_candidates']) for x in rows[:29]),
        'with_exact_nwsli_attributes':sum(bool(x['rfc_exact_attribute_matches']) for x in rows[:29]),
        'approved_legacy_map_masks':0,'warning':'RFC feature overlap is not proof of legacy MAP geometry.'}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('PHASE4A_SUMMARY='+json.dumps(summary,sort_keys=True))
    print('PHASE4A_INVENTORY_BEGIN')
    print((OUT/'network_inventory.csv').read_text())
    print('PHASE4A_INVENTORY_END')
