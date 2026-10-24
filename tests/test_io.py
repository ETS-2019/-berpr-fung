import copy
import json
from pathlib import Path
import tempfile
import unittest
from domain import *
from exports import *
import storage
from test_engine import ready_project


class IOTests(unittest.TestCase):
    def test_roundtrip_preserves_raw_values_and_hierarchy(self):
        p=ready_project();q=load_json(json_export(p))
        self.assertEqual(p['points'],q['points']);self.assertEqual(p['boards'],q['boards'])
        self.assertEqual(p['rules'],q['rules'])

    def test_invalid_imports(self):
        p=ready_project()
        for mutation in [lambda q:q.update(schema_version=999),lambda q:q['points'][0].update(zs_ohm=-1),
                         lambda q:q['points'][0].update(circuit_id='missing'),
                         lambda q:q['boards'][0].update(parent_id=q['boards'][0]['id']),
                         lambda q:q['points'].append(copy.deepcopy(q['points'][0]))]:
            q=copy.deepcopy(p);mutation(q)
            with self.assertRaises(ValueError):load_json(json.dumps(q))
        for raw in ['[]','{"x":NaN}', '{"schema_version":2}', 'x'* (MAX_IMPORT_BYTES+1)]:
            with self.assertRaises(ValueError):load_json(raw)

    def test_legacy_positive_status_not_trusted(self):
        old=dict(anlage={'unternehmen':'Alt'},pruefung={},pruefkatalog=[{'status':'OK'}],maengel=[])
        p=load_json(json.dumps(old));self.assertEqual(p['checks'][0]['status'],'Nicht geprüft')

    def test_html_escapes_and_markdown_real_newline(self):
        p=ready_project();p['plant']['name']='<script>alert(1)</script>'
        p['defects'].append(manual_defect(p['id'],'Test','S2','Details'))
        self.assertNotIn('<script>',html_export(p));self.assertIn('&lt;script&gt;',html_export(p))
        self.assertIn('\n  - Bezug:',markdown_export(p));self.assertNotIn(')\\n  -',markdown_export(p))

    def test_csv_mapping_decimal_comma_and_no_overwrite(self):
        p=ready_project();pid=p['points'][0]['id']
        rows=parse_measurement_csv(f'ID;Zs\n{pid};0,8\n',{'point_id':'ID','zs_ohm':'Zs'})
        self.assertEqual(rows[0]['zs_ohm'],0.8)
        with self.assertRaises(ValueError):apply_measurements(p,rows,'Test')
        q=apply_measurements(p,rows,'Test',overwrite=True)
        self.assertEqual(q['points'][0]['zs_ohm'],0.8);self.assertEqual(p['points'][0]['zs_ohm'],1)
        self.assertEqual(q['points'][0]['ik_zs_a'],230)

    def test_csv_rejects_unknown_duplicate_nan(self):
        p=ready_project()
        with self.assertRaises(ValueError):apply_measurements(p,[{'point_id':'unknown'}],'Test')
        for text in ['point_id;zs_ohm\na;nan\n','point_id;zs_ohm\na;1\na;2\n']:
            with self.assertRaises(ValueError):parse_measurement_csv(text)

    def test_csv_formula_escape(self):
        p=ready_project();p['points'][0]['room']='=1+1'
        self.assertIn("'=1+1",csv_export(p))
        self.assertEqual(safe_name('../../a / b'),'a_b')

    def test_sqlite_revisions_are_restorable(self):
        p=ready_project()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db.sqlite'
            first=storage.save(p,'A',path)
            p['plant']['name']='Neue Bezeichnung';second=storage.save(p,'B',path)
            self.assertEqual(storage.load(first,path)['plant']['name'],'Anlage')
            self.assertEqual(storage.load(second,path)['plant']['name'],'Neue Bezeichnung')
            self.assertEqual(len(storage.revisions(path)),2)
            with storage.connect(path) as db:db.execute('UPDATE revisions SET content=? WHERE revision=?',('{}',first))
            with self.assertRaises(ValueError):storage.load(first,path)

if __name__=='__main__':unittest.main()


class AdditionalIOTests(unittest.TestCase):
    def test_rcd_csv_contains_individual_test(self):
        p=ready_project();r=new_rcd(p['boards'][0]['id'],'FI')
        t=new_rcd_test();r['tests'].append(t);p['rcds'].append(r)
        data=rcd_csv_export(p)
        self.assertIn(t['id'],data);self.assertIn('OFFEN',data)

    def test_malformed_nested_schema_cannot_replace_project(self):
        p=ready_project()
        for mutate in [lambda q:q['rules'].update(u0_v='230'),
                       lambda q:q['checks'].pop(),
                       lambda q:q['points'][0].update(excluded=[]),
                       lambda q:q['audit'].append(42),
                       lambda q:q['points'][0].update(derive_ik='yes')]:
            q=copy.deepcopy(p);mutate(q)
            with self.assertRaises(ValueError):load_json(json.dumps(q))

    def test_revision_logs_changed_measurement(self):
        p=ready_project()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.sqlite'
            storage.save(p,'A',path)
            p['points'][0]['zs_ohm']=2
            revision=storage.save(p,'B',path)
            q=storage.load(revision,path)
            changes=q['audit'][-1]['changes']
            self.assertTrue(any(c['field'].endswith('/zs_ohm') and c['before']==1 and c['after']==2 for c in changes))
