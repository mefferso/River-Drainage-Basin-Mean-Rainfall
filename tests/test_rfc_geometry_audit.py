import csv,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/phase4a'
class FullNetworkAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary=json.loads((OUT/'summary.json').read_text())
        with (OUT/'network_inventory.csv').open(newline='') as f:cls.rows=list(csv.DictReader(f))
        with (OUT/'rfc_candidates.csv').open(newline='') as f:cls.candidates=list(csv.DictReader(f))
        cls.geojson=json.loads((OUT/'rfc_exact_nwsli_polygons.geojson').read_text())
        cls.spatial=json.loads((OUT/'rfc_dashboard_only_spatial_candidates.geojson').read_text())
    def test_complete_accounting(self):
        s=self.summary
        self.assertEqual((s['historical_points'],s['dashboard_gages'],s['inventory_rows']) if 'inventory_rows' in s else (s['historical_points'],s['dashboard_gages'],len(self.rows)),(29,26,37))
        self.assertEqual(s['matched_historical_gages'],18)
        self.assertEqual(s['dashboard_only_gages'],8)
        self.assertEqual(len(self.rows),37)
        self.assertEqual(len([r for r in self.rows if r['historical_id']]),29)
        self.assertEqual(len([r for r in self.rows if not r['historical_id']]),8)
    def test_no_unverified_geometry_is_approved(self):
        self.assertEqual(self.summary['approved_legacy_map_masks'],0)
        self.assertTrue(all(x['legacy_map_geometry_approved']=='False' for x in self.rows))
        self.assertTrue(all('UNVERIFIED' in r['scientific_status'] or r['scientific_status']=='SPATIAL_ONLY_NO_VERIFIED_HISTORICAL_JOIN' for r in self.candidates))
    def test_crosswalk_is_fail_closed(self):
        ids={r['historical_id']:r for r in self.rows if r['historical_id']}
        self.assertNotEqual(ids['MNLM6']['dashboard_usgs'],ids['CREM6']['dashboard_usgs'])
        self.assertEqual(ids['KLNM6']['dashboard_usgs'],'')
        self.assertEqual(ids['WTPM6']['canonical_nwsli'],'WPTM6')
        self.assertEqual(ids['WTPM6']['dashboard_usgs'],'')
        self.assertEqual(ids['AMIL1']['dashboard_usgs'],'07375430')
        self.assertEqual(ids['CREM6']['dashboard_usgs'],'02492343')
    def test_rfc_exports_are_nwsli_matched_not_approved(self):
        self.assertEqual(self.geojson['type'],'FeatureCollection')
        features=self.geojson['features']
        self.assertEqual(len(features),self.summary['exact_nwsli_polygon_features'])
        self.assertTrue(all(x['properties']['scientific_status']=='UNVERIFIED_LEGACY_MAP_GEOMETRY' for x in features))
        self.assertEqual(len({x['properties']['nwsli'] for x in features}),len(features))
    def test_dashboard_only_stations_have_spatial_candidate_inventory(self):
        extra=[r for r in self.rows if not r['historical_id']]
        self.assertEqual(len(extra),8)
        self.assertTrue(all(r['review_status']=='DASHBOARD_GAGE_WITHOUT_HISTORICAL_JOIN_SPATIAL_ONLY' for r in extra))
        self.assertTrue(all(r['rfc_candidates']!='' for r in extra))
        self.assertEqual(len(self.spatial['features']),8)
        self.assertTrue(all(x['properties']['scientific_status']=='SPATIAL_ONLY_NO_VERIFIED_HISTORICAL_JOIN' for x in self.spatial['features']))
if __name__=='__main__':unittest.main()
