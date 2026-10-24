import os
from pathlib import Path
import tempfile
import unittest
from streamlit.testing.v1 import AppTest
from domain import new_project,new_board,new_circuit,new_point,new_rcd,new_rcd_test


class AppTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.previous=os.environ.get('INSPECTION_DB')
        os.environ['INSPECTION_DB']=str(Path(self.folder.name)/'test.sqlite3')

    def tearDown(self):
        if self.previous is None:os.environ.pop('INSPECTION_DB',None)
        else:os.environ['INSPECTION_DB']=self.previous
        self.folder.cleanup()

    def app(self,project=None):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'))
        if project is not None:
            app.session_state['project']=project
            app.session_state['epoch']=0
        return app.run(timeout=30)

    def test_empty_start_and_autosave(self):
        app=self.app()
        self.assertFalse(app.exception)
        self.assertTrue(any('GRAU' in h.value for h in app.subheader))
        self.assertTrue(Path(os.environ['INSPECTION_DB']).exists())
        app.run()
        self.assertFalse(app.exception)

    def test_nested_ui_and_phase_copy(self):
        p=new_project();b=new_board('HV');p['boards'].append(b)
        c=new_circuit(b['id'],'Q1');p['circuits'].append(c)
        m=new_point(b['id'],'Steckdose','Raum',c['id']);p['points'].append(m)
        r=new_rcd(b['id'],'FI');r['tests'].append(new_rcd_test());p['rcds'].append(r)
        app=self.app(p)
        self.assertFalse(app.exception)
        button=next(b for b in app.button if b.label=='Für weitere Phasen kopieren')
        button.click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['project']['points']),3)
        self.assertEqual({p['phase'] for p in app.session_state['project']['points']},{'L1','L2','L3'})

    def test_create_board_and_manual_defect(self):
        app=self.app()
        next(t for t in app.text_input if t.label=='Neuer Verteiler').input('HV')
        next(b for b in app.button if b.label=='Verteiler anlegen').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['project']['boards'][0]['name'],'HV')
        next(t for t in app.text_input if t.label=='Mangelbeschreibung').input('Defektes Gehäuse')
        next(b for b in app.button if b.label=='Mangel erfassen').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(d['title']=='Defektes Gehäuse' for d in app.session_state['project']['defects']))
        self.assertTrue(any('ROT' in h.value for h in app.subheader))
