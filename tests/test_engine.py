import copy
import unittest
from domain import *
from engine import *


def ready_project():
    p=new_project()
    p['plant'].update(company='Betreiber',site='Wien',name='Anlage',asset_id='AT-1')
    p['inspection'].update(inspector='Prüfer',device='Gerät 1',calibration='2026-01',scope='Vollprüfung',next_due='2030-01-01',interval_basis='Prüfplan')
    p['rules'].update(reference='Fachlich bestätigtes Testprofil',approved_by='Test',approved_at='2026-01-01',scope_note='TN Testfall',legal_basis='Testgrundlage')
    b=new_board('HV');p['boards'].append(b)
    c=new_circuit(b['id'],'Q1');c.update(reference='Testkennlinie',approved_by='Test',zi_ia_a=80,zi_required_time_s=0.4,zi_reference='Testkennlinie Zi');p['circuits'].append(c)
    m=new_point(b['id'],'Steckdose','Raum 1',c['id'])
    m.update(zs_ohm=1,zi_ohm=1,ik_zs_a=230,ik_zi_a=230,riso_mohm=10,rpe_ohm=0.1,
             riso_min_mohm=1,rpe_max_ohm=1,insulation_test_v=500,method='Testverfahren',reference='Testgrenzen',approved_by='Test')
    p['points'].append(m)
    for row in p['checks']+b['checks']:
        row['status']='OK'
    return p


class EngineTests(unittest.TestCase):
    def test_empty_never_green(self):
        p=new_project(); result=summary(p,evaluate(p))
        self.assertFalse(result['complete']);self.assertFalse(result['positive']);self.assertEqual(result['traffic'],'GRAU')

    def test_complete_baseline(self):
        p=ready_project();self.assertTrue(summary(p,evaluate(p))['positive'])

    def test_manual_medium_blocks_green(self):
        p=ready_project();p['defects'].append(manual_defect(p['id'],'Mangel','S2'))
        self.assertEqual(summary(p,evaluate(p))['traffic'],'ROT')

    def test_single_critical_check_is_red(self):
        p=ready_project();p['checks'][0].update(status='Mangel',severity='S3')
        self.assertEqual(summary(p,evaluate(p))['traffic'],'ROT')

    def test_na_requires_reason_and_all_na_not_positive(self):
        p=ready_project()
        for c in p['checks']:c['status']='N/A'
        self.assertFalse(summary(p,evaluate(p))['complete'])
        for c in p['checks']:c['reason']='Nicht anwendbar'
        for m in p['points']:
            m['excluded']={k:'Nicht anwendbar' for k in METRICS}
        self.assertFalse(summary(p,evaluate(p))['positive'])

    def test_circuit_factors_and_reserve(self):
        p=ready_project();c=p['circuits'][0]
        for curve,factor in [('B',5),('C',10),('D',20)]:
            c['curve']=curve;l=circuit_limits(c,p['rules'])
            self.assertEqual(l['ia_a'],16*factor)
            c['mode']='Mit 2/3 Reserve';r=circuit_limits(c,p['rules'])
            self.assertAlmostEqual(r['z_max_ohm'],l['z_max_ohm']*2/3)
            self.assertAlmostEqual(r['ik_min_a'],l['ik_min_a']*1.5)
            c['mode']='Normal'

    def test_mccb_needs_ia(self):
        p=ready_project();c=p['circuits'][0];c['device']='MCCB'
        self.assertIsNone(circuit_limits(c,p['rules']))
        c['ia_a']=100;self.assertEqual(circuit_limits(c,p['rules'])['ia_a'],100)

    def test_exact_limit(self):
        self.assertEqual(compare(2,2),'FEHLER')
        self.assertEqual(compare(2,2,strict=False),'OK')
        self.assertEqual(compare(80,80,False),'FEHLER')
        self.assertEqual(compare(None,2),'OFFEN')

    def test_ik_preserved_and_derived_labeled(self):
        p=ready_project();m=p['points'][0];m.update(derive_ik=True,ik_zs_a=300)
        before=copy.deepcopy(m);fs=evaluate(p)
        self.assertEqual(m,before)
        f=next(f for f in fs if f['rule']=='ik_zs_a')
        self.assertEqual(f['evidence']['value'],300);self.assertFalse(f['evidence']['derived'])
        m['ik_zs_a']=None
        f=next(f for f in evaluate(p) if f['rule']=='ik_zs_a')
        self.assertEqual(f['evidence']['value'],230);self.assertTrue(f['evidence']['derived']);self.assertIsNone(m['ik_zs_a'])

    def test_plausibility_generates_defect(self):
        p=ready_project();p['points'][0]['ik_zs_a']=1000
        sync_defects(p,evaluate(p))
        self.assertTrue(any(d['rule']=='zs_ohm_plausibility' for d in p['defects']))

    def test_automatic_defect_lifecycle(self):
        p=ready_project();m=p['points'][0];m['zs_ohm']=4
        sync_defects(p,evaluate(p));sync_defects(p,evaluate(p))
        defects=[d for d in p['defects'] if d['rule']=='zs_ohm'];self.assertEqual(len(defects),1)
        d=defects[0];m['zs_ohm']=None;sync_defects(p,evaluate(p));self.assertEqual(d['state'],'Offen')
        m['zs_ohm']=1;sync_defects(p,evaluate(p));self.assertEqual(d['state'],'Behoben')
        m['zs_ohm']=4;sync_defects(p,evaluate(p));self.assertEqual(d['state'],'Offen')
        self.assertEqual([r['state'] for r in d['history']],['Offen','Behoben','Offen'])

    def test_tt_and_unapproved_remain_open(self):
        p=ready_project();p['plant']['network']='TT'
        self.assertFalse(summary(p,evaluate(p))['complete'])
        p['plant']['network']='TN';p['rules']['approved_by']=''
        self.assertFalse(summary(p,evaluate(p))['complete'])

    def test_rcd_type_ac_new_vs_existing(self):
        p=ready_project();r=new_rcd(p['boards'][0]['id'],'FI');r['type']='AC'
        self.assertFalse(any(f['rule']=='type_ac' for f in evaluate_rcd(r,p['rules'],p['plant'])))
        p['plant']['scope']='Neuanlage'
        self.assertTrue(any(f['rule']=='type_ac' for f in evaluate_rcd(r,p['rules'],p['plant'])))

    def test_rcd_boundaries_and_coverage(self):
        p=ready_project();r=new_rcd(p['boards'][0]['id'],'FI');r.update(reference='Test',approved_by='Test')
        t=new_rcd_test();t.update(reference='Test',approved_by='Test',tripped=True,time_ms=40,max_time_ms=100,
                                current_ma=20,min_current_ma=15,max_current_ma=30)
        r['tests']=[t]
        self.assertTrue(any(f['rule']=='coverage' for f in evaluate_rcd(r,p['rules'],p['plant'])))
        t2=copy.deepcopy(t);t2.update(id=uid(),waveform='A');r['tests'].append(t2)
        self.assertTrue(all(f['status']=='OK' for f in evaluate_rcd(r,p['rules'],p['plant'])))
        t['time_ms']=100
        self.assertTrue(any(f['status']=='FEHLER' for f in evaluate_rcd(r,p['rules'],p['plant'])))
        t.update(expected='Keine Auslösung',tripped=False)
        self.assertTrue(all(f['status']=='OK' for f in evaluate_rcd(r,p['rules'],p['plant'])))

    def test_duplicate_measurements(self):
        p=ready_project();m=copy.deepcopy(p['points'][0]);m['id']=uid();p['points'].append(m)
        self.assertTrue(any(f['rule']=='duplicate' for f in evaluate(p)))

if __name__=='__main__':unittest.main()


class AdditionalEngineTests(unittest.TestCase):
    def test_zero_impedance_not_pass(self):
        p=ready_project();p['points'][0]['zs_ohm']=0
        self.assertEqual(next(f['status'] for f in evaluate(p) if f['rule']=='zs_ohm'),'FEHLER')

    def test_zi_needs_own_short_circuit_basis(self):
        p=ready_project();p['circuits'][0]['zi_ia_a']=None
        self.assertEqual(next(f['status'] for f in evaluate(p) if f['rule']=='zi_ohm'),'OFFEN')

    def test_exceeded_breaking_capacity_is_critical(self):
        p=ready_project();p['circuits'][0]['breaking_capacity_a']=200
        self.assertTrue(any(f['rule']=='breaking_capacity' and f['severity']=='S3' for f in evaluate(p)))

    def test_zero_rcd_time_is_not_pass(self):
        p=ready_project();r=new_rcd(p['boards'][0]['id'],'FI');r.update(reference='Test',approved_by='Test')
        t=new_rcd_test();t.update(reference='Test',approved_by='Test',tripped=True,time_ms=0,max_time_ms=100)
        r['tests']=[t]
        self.assertEqual(next(f['status'] for f in evaluate_rcd(r,p['rules'],p['plant']) if f['rule']=='rcd_'+t['id']),'FEHLER')

    def test_rcd_ramp_without_time(self):
        p=ready_project();r=new_rcd(p['boards'][0]['id'],'FI');r.update(reference='Test',approved_by='Test')
        t=new_rcd_test();t.update(mode='Rampenprüfung',reference='Test',approved_by='Test',tripped=True,
                                current_ma=20,min_current_ma=15,max_current_ma=30)
        r['tests']=[t]
        self.assertEqual(next(f['status'] for f in evaluate_rcd(r,p['rules'],p['plant']) if f['rule']=='rcd_'+t['id']),'OK')
        t['current_ma']=31
        self.assertEqual(next(f['status'] for f in evaluate_rcd(r,p['rules'],p['plant']) if f['rule']=='rcd_'+t['id']),'FEHLER')
