"""Versioned inspection model. No Streamlit dependency and no implicit approvals."""
from __future__ import annotations

import datetime as dt
import math
import uuid

SCHEMA_VERSION = 2
STATUSES = ['Nicht geprüft', 'OK', 'Mangel', 'N/A']
CLASSES = ['S1', 'S2', 'S3']
CHECKS = [
    ('visual', 'Sichtprüfung / Kennzeichnung / thermische Schäden'),
    ('shock', 'Schutz gegen elektrischen Schlag / Abschaltbedingungen'),
    ('rcd', 'RCD-Auswahl, Zuordnung und Funktionsprüfung'),
    ('bonding', 'Erdung / Schutz- und Potentialausgleich'),
    ('overcurrent', 'Überstromschutz / Vorsicherung / Selektivität'),
    ('measurements', 'Messabdeckung / Isolations- und Schutzleiterprüfung'),
    ('installation', 'Verteiler / Leitungen / Betriebsmittel'),
    ('documentation', 'Pläne / Beschriftung / Dokumentation'),
]
METRICS = ['zs_ohm', 'zi_ohm', 'ik_zs_a', 'ik_zi_a', 'riso_mohm', 'rpe_ohm']


def uid():
    return str(uuid.uuid4())


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def new_project():
    return {
        'schema_version': SCHEMA_VERSION, 'id': uid(), 'created_at': now(),
        'plant': dict(company='', site='', name='', asset_id='', installation_year=None,
                      scope='Bestand', network='TN', special_conditions=''),
        'inspection': dict(inspector='', date=dt.date.today().isoformat(), next_due='',
                           interval_basis='', kind='Wiederkehrende Prüfung',
                           device='', calibration='', scope='', exclusions=''),
        'rules': {
            'edition': 'OVE E 8101:2025-10-01', 'legal_basis': '',
            'reference': '', 'approved_by': '', 'approved_at': '',
            'scope_note': '', 'u0_v': 230.0, 'strict_limits': True,
            'plausibility_tolerance': 0.2,
            'sources': [
                {'title': 'OVE E 8101:2025-10-01 – Teil 6 Prüfung',
                 'url': 'https://www.ove.at/ove-standardization/normen-produkte/ove-e-8101/'},
                {'title': 'ETV 2020 – konsolidierte Fassung, Anwendbarkeit prüfen',
                 'url': 'https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=20011222'},
            ],
        },
        'checks': [dict(id=k, criterion=t, status='Nicht geprüft', reason='', severity='S2') for k,t in CHECKS],
        'boards': [], 'circuits': [], 'points': [], 'rcds': [], 'defects': [],
        'attachments': [], 'audit': [], 'catalog': [],
    }


def new_board(name):
    return dict(id=uid(), name=name, parent_id='', checks=[
        dict(id=k, criterion=t, status='Nicht geprüft', reason='', severity='S2') for k,t in CHECKS])


def new_circuit(board_id, name):
    return dict(id=uid(), board_id=board_id, name=name, device='LS', curve='B',
                in_a=16.0, ia_a=None, zi_ia_a=None, zi_required_time_s=None, zi_reference='',
                breaking_capacity_a=None, required_time_s=0.4,
                mode='Normal', rcd_id='', reference='', approved_by='')


def new_point(board_id, name, room='', circuit_id=''):
    return dict(id=uid(), board_id=board_id, circuit_id=circuit_id, name=name, room=room,
                phase='L1', zs_ohm=None, zi_ohm=None, ik_zs_a=None, ik_zi_a=None,
                riso_mohm=None, rpe_ohm=None, rotation='Nicht geprüft',
                required_rotation=False, riso_min_mohm=None, rpe_max_ohm=None,
                insulation_test_v=None, method='', reference='', approved_by='',
                derive_ik=False, excluded={}, measurement_source='', measured_at='')


def new_rcd(board_id, name):
    return dict(id=uid(), board_id=board_id, name=name, type='A', delay='unverzögert',
                idn_ma=30.0, reference='', approved_by='', tests=[],
                checks=[dict(id=k, criterion=t, status='Nicht geprüft', reason='', severity='S2')
                        for k,t in [('neutral', 'N-Zuordnung'), ('backup', 'Vorsicherungsfestigkeit'),
                                    ('selectivity', 'Selektivität'), ('plan', 'Prüfplan vollständig')]])


def new_rcd_test():
    return dict(id=uid(), mode='Zeitprüfung', waveform='AC', factor=1.0, polarity='0°', expected='Auslösung',
                tripped=None, time_ms=None, current_ma=None, max_time_ms=None,
                min_current_ma=None, max_current_ma=None, reference='', approved_by='',
                severity='S2')


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def nonnegative(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def validate(project):
    """Reject malformed imports before they can replace the working inspection."""
    if not isinstance(project, dict) or project.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Nicht unterstützte Schemaversion (erwartet: 2).')
    template = new_project()
    for key, default in template.items():
        if key not in project or not isinstance(project[key], type(default)):
            raise ValueError(f'Ungültiges Feld: {key}')
    for key in ('plant', 'inspection', 'rules'):
        if set(template[key]) - set(project[key]):
            raise ValueError(f'Fehlende Felder in {key}')
    groups = ('boards', 'circuits', 'points', 'rcds', 'defects', 'attachments')
    ids = []
    for group in groups:
        for row in project[group]:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
                raise ValueError(f'Ungültige ID in {group}')
            ids.append(row['id'])
    if len(ids) != len(set(ids)):
        raise ValueError('Doppelte IDs sind nicht erlaubt.')
    boards = {r['id']: r for r in project['boards']}
    circuits = {r['id']: r for r in project['circuits']}
    rcds = {r['id']: r for r in project['rcds']}
    for group, factory in [('boards', lambda: new_board('')), ('circuits', lambda: new_circuit('', '')),
                           ('points', lambda: new_point('', '')), ('rcds', lambda: new_rcd('', ''))]:
        required = set(factory())
        for row in project[group]:
            if required - set(row):
                raise ValueError(f'Fehlende Felder in {group}: {required - set(row)}')
    for board in boards.values():
        seen = {board['id']}
        parent = board['parent_id']
        while parent:
            if parent not in boards or parent in seen:
                raise ValueError('Ungültige oder zyklische Verteilerhierarchie.')
            seen.add(parent)
            parent = boards[parent]['parent_id']
    for row in list(circuits.values()) + project['points'] + list(rcds.values()):
        if row['board_id'] not in boards:
            raise ValueError('Verteilerzuordnung fehlt.')
    for circuit in circuits.values():
        rid = circuit['rcd_id']
        if rid and (rid not in rcds or rcds[rid]['board_id'] != circuit['board_id']):
            raise ValueError('Ungültige RCD-Zuordnung.')
    for point in project['points']:
        cid = point['circuit_id']
        if cid and (cid not in circuits or circuits[cid]['board_id'] != point['board_id']):
            raise ValueError('Ungültige Stromkreiszuordnung.')
        for metric in METRICS:
            if point[metric] is not None and not nonnegative(point[metric]):
                raise ValueError(f'Ungültiger Messwert: {metric}')
    for checks in [project['checks']] + [b['checks'] for b in boards.values()] + [r['checks'] for r in rcds.values()]:
        if not isinstance(checks, list):
            raise ValueError('Ungültiger Prüfkatalog.')
        for row in checks:
            if not isinstance(row, dict) or not {'id','criterion','status','reason','severity'} <= set(row):
                raise ValueError('Ungültiger Prüfpunkt.')
            if row['status'] not in STATUSES or row['severity'] not in CLASSES:
                raise ValueError('Ungültiger Prüfstatus / Mängelklasse.')
    for rcd in rcds.values():
        for test in rcd['tests']:
            if set(new_rcd_test()) - set(test):
                raise ValueError('Unvollständiger RCD-Prüfschritt.')
    for defect in project['defects']:
        if not {'target_id','rule','title','severity','state','automatic','history','details','due'} <= set(defect):
            raise ValueError('Unvollständiger Mangel.')
        if defect['severity'] not in CLASSES or defect['state'] not in ['Offen','Behoben']:
            raise ValueError('Ungültige Mängelklasse / Status.')
    def numeric(row, keys, nullable=True):
        for key in keys:
            value = row.get(key)
            if value is None and nullable:
                continue
            if not nonnegative(value):
                raise ValueError('Ungültiger Zahlenwert: '+key)
    def strings(row, keys):
        if any(not isinstance(row.get(k),str) for k in keys):
            raise ValueError('Textfeld hat ungültigen Typ.')
    strings(project['plant'],['company','site','name','asset_id','scope','network','special_conditions'])
    strings(project['inspection'],list(template['inspection']))
    strings(project['rules'],['edition','legal_basis','reference','approved_by','approved_at','scope_note'])
    numeric(project['rules'],['u0_v','plausibility_tolerance'],False)
    if not isinstance(project['rules']['strict_limits'],bool):
        raise ValueError('Ungültiger Grenzwertmodus.')
    numeric(project['plant'],['installation_year'])
    if project['plant']['network'] not in ['TN','TT','IT'] or project['plant']['scope'] not in ['Bestand','Neuanlage','Änderung/Erweiterung']:
        raise ValueError('Unbekanntes Netzsystem / Anlagenumfang.')
    for circuit in circuits.values():
        numeric(circuit,['in_a','ia_a','zi_ia_a','zi_required_time_s','breaking_capacity_a','required_time_s'])
        strings(circuit,['name','device','curve','mode','reference','approved_by','zi_reference'])
    for point in project['points']:
        strings(point,['name','room','phase','rotation','method','reference','approved_by','measurement_source','measured_at'])
        numeric(point,['riso_min_mohm','rpe_max_ohm','insulation_test_v'])
        if not isinstance(point['derive_ik'],bool) or not isinstance(point['required_rotation'],bool):
            raise ValueError('Ungültige Messoption.')
        if point['phase'] not in ['L1','L2','L3'] or point['rotation'] not in ['Nicht geprüft','Rechts','Links']:
            raise ValueError('Ungültige Phase / Drehfeld.')
        if not isinstance(point['excluded'],dict) or any(k not in METRICS or not isinstance(v,str) for k,v in point['excluded'].items()):
            raise ValueError('Ungültige Ausnahmebegründung.')
    for rcd in rcds.values():
        if not isinstance(rcd['tests'],list) or len({t['id'] for t in rcd['tests']}) != len(rcd['tests']):
            raise ValueError('Doppelte / ungültige RCD-Prüfschritte.')
        strings(rcd,['name','type','delay','reference','approved_by'])
        numeric(rcd,['idn_ma'])
        for test in rcd['tests']:
            numeric(test,['factor','time_ms','current_ma','max_time_ms','min_current_ma','max_current_ma'])
            strings(test,['id','mode','waveform','polarity','expected','reference','approved_by','severity'])
            if test['tripped'] is not None and not isinstance(test['tripped'],bool):
                raise ValueError('Ungültiges RCD-Auslöseergebnis.')
            if test['mode'] not in ['Zeitprüfung','Rampenprüfung']:
                raise ValueError('Unbekannte RCD-Messart.')
            if test['severity'] not in CLASSES or test['expected'] not in ['Auslösung','Keine Auslösung']:
                raise ValueError('Ungültiger RCD-Prüfschritt.')
    for board in boards.values():
        strings(board,['name','parent_id'])
    check_sets = [project['checks']] + [b['checks'] for b in boards.values()] + [r['checks'] for r in rcds.values()]
    for index, checks in enumerate(check_sets):
        expected = {k for k,t in CHECKS} if index <= len(boards) else {'neutral','backup','selectivity','plan'}
        check_ids = [c['id'] for c in checks]
        if len(check_ids) != len(set(check_ids)) or not expected <= set(check_ids):
            raise ValueError('Prüfkatalog ist unvollständig / enthält doppelte IDs.')
        for check in checks:
            strings(check,['id','criterion','status','reason','severity'])
    if not all(isinstance(event,dict) for event in project['audit']):
        raise ValueError('Ungültiger Änderungsverlauf.')
    known = set(ids) | {project['id']}
    for defect in project['defects']:
        strings(defect,['target_id','rule','title','severity','state','details','due'])
        if defect['target_id'] not in known or not isinstance(defect['automatic'],bool) or not isinstance(defect['history'],list):
            raise ValueError('Ungültiger Mangelbezug / Verlauf.')
        if not all(isinstance(event,dict) and isinstance(event.get('at'),str) and event.get('state') in ['Offen','Behoben'] for event in defect['history']):
            raise ValueError('Ungültiger Mängelverlauf.')
    import base64
    import hashlib
    total = 0
    for attachment in project['attachments']:
        strings(attachment,['target_id','name','mime','base64','sha256'])
        if attachment['target_id'] not in known or attachment['mime'] not in ['image/png','image/jpeg']:
            raise ValueError('Ungültiger Foto-Anhang.')
        try:
            raw = base64.b64decode(attachment['base64'],validate=True)
        except ValueError as exc:
            raise ValueError('Ungültige Bildkodierung.') from exc
        total += len(attachment['base64'])
        if len(raw)>2*1024*1024 or total>6*1024*1024:
            raise ValueError('Fotolimit überschritten.')
        header = b'\x89PNG\r\n\x1a\n' if attachment['mime']=='image/png' else b'\xff\xd8\xff'
        if not raw.startswith(header) or hashlib.sha256(raw).hexdigest()!=attachment['sha256']:
            raise ValueError('Ungültige Bilddaten / Prüfsumme.')
    if not isinstance(project['rules']['sources'],list) or not all(isinstance(v,dict) and isinstance(v.get('title'),str) and isinstance(v.get('url'),str) for v in project['rules']['sources']):
        raise ValueError('Ungültige Regelquellen.')
    if not all(isinstance(c,dict) and isinstance(c.get('id'),str) and isinstance(c.get('title'),str) and c.get('severity') in CLASSES for c in project['catalog']):
        raise ValueError('Ungültiger Mängelkatalog.')
    return project


def migrate_legacy(old):
    if not isinstance(old, dict) or not {'anlage','pruefung','pruefkatalog','maengel'} <= set(old):
        raise ValueError('Kein unterstütztes Altformat.')
    p = new_project()
    for src, dest in [('unternehmen','company'),('standort','site'),('bezeichnung','name'),('anlagen_id','asset_id')]:
        p['plant'][dest] = str(old['anlage'].get(src, ''))
    for src, dest in [('pruefer','inspector'),('pruefdatum','date'),('naechster_termin','next_due'),('pruefart','kind')]:
        p['inspection'][dest] = str(old['pruefung'].get(src, ''))
    for row, previous in zip(p['checks'], old['pruefkatalog']):
        row['reason'] = 'Altimport – erneut prüfen: ' + str(previous.get('bemerkung',''))
    for d in old['maengel']:
        p['defects'].append(manual_defect(p['id'], str(d.get('titel','Altimport')),
            {'niedrig':'S1','mittel':'S2','hoch':'S3'}.get(d.get('prioritaet'), 'S2'),
            str(d.get('details','')), str(d.get('behebungsfrist',''))))
    p['audit'].append(dict(at=now(), action='Altformat importiert; positive Bewertungen zurückgesetzt'))
    return p


def manual_defect(target, title, severity='S2', details='', due=''):
    return dict(id=uid(), target_id=target, rule='', title=title, severity=severity,
                details=details, due=due, state='Offen', automatic=False,
                history=[dict(at=now(), state='Offen')])
