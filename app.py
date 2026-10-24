"""Streamlit UI for the versioned Austrian electrical inspection workbook."""
import base64
import copy
import datetime as dt
import hashlib
import json
import sqlite3

import streamlit as st
from domain import (new_project,new_board,new_circuit,new_point,new_rcd,new_rcd_test,
                    manual_defect,STATUSES,CLASSES,METRICS,now,uid,validate)
from engine import evaluate,sync_defects,summary,circuit_limits
from exports import (json_export,load_json,markdown_export,html_export,csv_export,
                     csv_template,safe_name,parse_measurement_csv,apply_measurements,rcd_csv_export)
import storage

st.set_page_config(page_title='Prüf-App Österreich',layout='wide')
if 'project' not in st.session_state:
    st.session_state.project = new_project()
    st.session_state.epoch = 0
p = st.session_state.project


def replace(project):
    st.session_state.project = project
    st.session_state.epoch += 1
    st.session_state.pop('saved_hash',None)
    st.rerun()


def key(row,field):
    return f"{st.session_state.epoch}:{row.get('id','row')}:{id(row)}:{field}"


def text(row,field,label,area=False):
    fn = st.text_area if area else st.text_input
    row[field] = fn(label,value=str(row.get(field,'') or ''),key=key(row,field))


def choice(row,field,label,options):
    value = row.get(field)
    row[field] = st.selectbox(label,options,index=options.index(value) if value in options else 0,key=key(row,field))


def number(row,field,label,minimum=0.0):
    value = row.get(field)
    row[field] = st.number_input(label,min_value=minimum,value=float(value) if value is not None else None,
                                 format='%.6f',key=key(row,field))


def flag(row,field,label):
    row[field] = st.checkbox(label,value=bool(row.get(field)),key=key(row,field))


def select_ref(row,field,label,records,optional=True):
    options = ([''] if optional else [])+[r['id'] for r in records]
    if not options:
        st.info(label+': zuerst einen Eintrag anlegen.')
        return
    labels = {r['id']:r.get('name',r['id']) for r in records}
    row[field] = st.selectbox(label,options,index=options.index(row.get(field)) if row.get(field) in options else 0,
                              format_func=lambda x: labels.get(x,'—'),key=key(row,field))


def checks(rows):
    for row in rows:
        with st.expander(row['criterion']+' · '+row['status']):
            choice(row,'status','Prüfstatus',STATUSES)
            text(row,'reason','Bemerkung / Begründung bei N/A')
            choice(row,'severity','Mängelklasse bei negativem Ergebnis',CLASSES)


def approval(row):
    text(row,'reference','Regel-Fundstelle / Herstellerkennlinie / Prüfverfahren')
    text(row,'approved_by','Fachlich geprüft durch (Name)')


st.title('Prüf-App Österreich')
st.caption('Anlage → Verteiler → raumweise Messpunkte · Stromkreis als Zuordnung')
st.info('Nicht geprüfte Angaben bleiben offen. Rechenhilfen gelten nur im freigegebenen Anwendungsbereich; die fachliche Abschlussprüfung bleibt erforderlich.')
with st.sidebar:
    st.subheader('Prüfung speichern / fortsetzen')
    autosave = st.checkbox('Änderungen automatisch lokal sichern',value=True)
    st.caption('Bei Serverbetrieb benötigt die Datenbank einen dauerhaften Datenträger. JSON-Backups zusätzlich herunterladen.')
    if st.button('Neue Prüfung'):
        replace(new_project())
    try:
        revisions = storage.revisions()
        if revisions:
            selected = st.selectbox('Gespeicherte Revision',revisions,
                format_func=lambda r: f'#{r[0]} · {r[2]} · {r[1][:8]} · {r[3]}')
            if st.button('Revision laden'):
                replace(storage.load(selected[0]))
    except (OSError,ValueError,sqlite3.Error) as exc:
        st.error('Speicher nicht verfügbar: '+str(exc))
    backup = st.file_uploader('JSON-Backup / bisheriges Anlagenbuch laden',type=['json'])
    if backup and st.button('JSON prüfen und laden'):
        try:
            replace(load_json(backup.getvalue()))
        except (ValueError,UnicodeError) as exc:
            st.error(str(exc))

tabs = st.tabs(['Stammdaten','Normen & Regeln','Verteiler & Stromkreise','Messpunkte','RCD','Prüfkatalog','Mängel & Fotos','Import','Ergebnis & Export'])
with tabs[0]:
    c1,c2=st.columns(2)
    with c1:
        st.subheader('Anlage')
        for field,label in [('company','Unternehmen / Betreiber'),('site','Standort'),('name','Anlage'),('asset_id','Anlagen-ID')]:
            text(p['plant'],field,label)
        number(p['plant'],'installation_year','Errichtungsjahr (falls bekannt)')
        choice(p['plant'],'scope','Umfang',['Bestand','Neuanlage','Änderung/Erweiterung'])
        choice(p['plant'],'network','Netzsystem',['TN','TT','IT'])
        text(p['plant'],'special_conditions','Besondere Räume / Einflüsse',True)
    with c2:
        st.subheader('Prüfung')
        for field,label in [('inspector','Prüfer:in'),('date','Prüfdatum (JJJJ-MM-TT)'),('next_due','Nächster Prüftermin (JJJJ-MM-TT)'),
                            ('interval_basis','Grundlage für Prüffrist'),('device','Messgerät / Seriennummer'),('calibration','Kalibrierung / Überprüfungsnachweis'),
                            ('scope','Prüfumfang'),('exclusions','Einschränkungen / nicht zugängliche Bereiche')]:
            text(p['inspection'],field,label)
        choice(p['inspection'],'kind','Prüfart',['Erstprüfung','Wiederkehrende Prüfung','Anlassbezogene Prüfung'])
with tabs[1]:
    st.subheader('Versionierte Regelgrundlage')
    st.warning('Vollständige normative Grenzwerttabellen sind nicht mitgeliefert. Freigaben und Fundstellen müssen sich auf die tatsächlich anwendbaren Unterlagen beziehen.')
    r=p['rules']
    for field,label in [('edition','Normausgabe'),('legal_basis','Rechtliche Grundlage / ETV-Fassung'),('scope_note','Anwendbarkeit: Errichtung, Bestand, Änderungen'),
                        ('reference','Fundstellen / Regelprofil'),('approved_by','Regelprofil fachlich geprüft durch'),('approved_at','Freigabedatum (JJJJ-MM-TT)')]:
        text(r,field,label)
    number(r,'u0_v','U0 [V]')
    number(r,'plausibility_tolerance','Relative Z/Ik-Plausibilitätstoleranz (0,2 = 20 %)')
    flag(r,'strict_limits','Strenge Grenzen: Messwert < Zmax / Ik > Ikmin')
    st.caption('Die B/C/D-Faktoren 5/10/20 und die optionale 2/3-Reserve sind Rechenhilfen. Automatische Abschaltbewertung derzeit nur für freigegebene TN-Profile. TT/IT bleiben offen.')
    st.json(r['sources'])
with tabs[2]:
    with st.form('add_board'):
        name=st.text_input('Neuer Verteiler')
        if st.form_submit_button('Verteiler anlegen') and name.strip():
            p['boards'].append(new_board(name.strip()))
            st.rerun()
    for board in p['boards']:
        with st.expander('Verteiler: '+board['name']):
            text(board,'name','Bezeichnung')
            # Only offer ancestors that cannot make a cycle.
            def descendant(candidate):
                seen=set()
                while candidate and candidate not in seen:
                    if candidate==board['id']:
                        return True
                    seen.add(candidate)
                    candidate=next((b['parent_id'] for b in p['boards'] if b['id']==candidate),'')
                return False
            select_ref(board,'parent_id','Übergeordneter Verteiler',[b for b in p['boards'] if not descendant(b['id'])])
            checks(board['checks'])
    if p['boards']:
        with st.form('add_circuit'):
            bid=st.selectbox('Verteiler',p['boards'],format_func=lambda b:b['name'])
            name=st.text_input('Neuer Stromkreis')
            if st.form_submit_button('Stromkreis anlegen') and name.strip():
                p['circuits'].append(new_circuit(bid['id'],name.strip()))
                st.rerun()
    for circuit in p['circuits']:
        with st.expander('Stromkreis: '+circuit['name']):
            text(circuit,'name','Stromkreisbezeichnung')
            choice(circuit,'device','Schutzorgan',['LS','FI/LS','D02','NH','MCCB','Abgang'])
            choice(circuit,'curve','Kennlinie',['B','C','D','Herstellerkennlinie'])
            number(circuit,'in_a','Nennstrom [A]')
            number(circuit,'ia_a','Ia [A] – leer: B/C/D-Rechenhilfe')
            number(circuit,'required_time_s','Erforderliche Abschaltzeit Zs [s]')
            number(circuit,'zi_ia_a','Ia für Zi / Kurzschlussschutz [A]')
            number(circuit,'zi_required_time_s','Zulässige Zeit für Zi / Kurzschlussschutz [s]')
            text(circuit,'zi_reference','Fundstelle für Zi / Kurzschlussschutz')
            number(circuit,'breaking_capacity_a','Ausschaltvermögen [A] (Dokumentation)')
            choice(circuit,'mode','Grenzwertmodus',['Normal','Mit 2/3 Reserve'])
            select_ref(circuit,'rcd_id','Zugeordneter RCD',[r for r in p['rcds'] if r['board_id']==circuit['board_id']])
            approval(circuit)
            st.write('Berechnete Grenzen:',circuit_limits(circuit,p['rules']) or 'Parameter fehlen')
with tabs[3]:
    if p['boards']:
        with st.form('add_point'):
            bid=st.selectbox('Verteiler für Messpunkt',p['boards'],format_func=lambda b:b['name'])
            room=st.text_input('Raum')
            name=st.text_input('Neuer Messpunkt')
            if st.form_submit_button('Messpunkt anlegen') and name.strip():
                p['points'].append(new_point(bid['id'],name.strip(),room.strip()))
                st.rerun()
    else:
        st.info('Zuerst einen Verteiler anlegen.')
    for point in sorted(p['points'],key=lambda q:(q['room'],q['name'],q['phase'])):
        with st.expander(f"{point['room']} · {point['name']} · {point['phase']}"):
            text(point,'name','Messpunkt')
            text(point,'room','Raum')
            select_ref(point,'circuit_id','Stromkreiszuordnung',[c for c in p['circuits'] if c['board_id']==point['board_id']])
            choice(point,'phase','Phase',['L1','L2','L3'])
            if st.button('Für weitere Phasen kopieren',key='phases'+point['id']):
                existing={(q['name'],q['room'],q['board_id'],q['phase']) for q in p['points']}
                for phase in ['L1','L2','L3']:
                    if (point['name'],point['room'],point['board_id'],phase) not in existing:
                        q=copy.deepcopy(point)
                        q.update(id=uid(),phase=phase,**{k:None for k in METRICS},rotation='Nicht geprüft',measurement_source='',measured_at='')
                        p['points'].append(q)
                st.rerun()
            for metric,label in [('zs_ohm','Zs L–PE [Ω]'),('zi_ohm','Zi L–N [Ω]'),('ik_zs_a','Ik Zs gemessen [A]'),('ik_zi_a','Ik Zi gemessen [A]'),
                                 ('riso_mohm','Riso [MΩ]'),('rpe_ohm','RPE [Ω]')]:
                number(point,metric,label)
                text(point['excluded'],metric,'Ausnahmebegründung '+metric)
            flag(point,'derive_ik','Ik nur bei leerem Messfeld rechnerisch ergänzen (im Ergebnis)')
            number(point,'riso_min_mohm','Riso Mindestwert [MΩ]')
            number(point,'rpe_max_ohm','RPE Höchstwert [Ω]')
            number(point,'insulation_test_v','Isolations-Prüfspannung [V]')
            text(point,'method','Messverfahren / Randbedingungen')
            approval(point)
            flag(point,'required_rotation','Drehfeld erforderlich')
            choice(point,'rotation','Drehfeld',['Nicht geprüft','Rechts','Links'])
            text(point,'measurement_source','Messquelle / Gerätedatei')
            text(point,'measured_at','Messzeitpunkt')
with tabs[4]:
    if p['boards']:
        with st.form('add_rcd'):
            bid=st.selectbox('Verteiler für RCD',p['boards'],format_func=lambda b:b['name'])
            name=st.text_input('Neuer RCD')
            if st.form_submit_button('RCD anlegen') and name.strip():
                p['rcds'].append(new_rcd(bid['id'],name.strip()))
                st.rerun()
    for rcd in p['rcds']:
        with st.expander('RCD: '+rcd['name']):
            text(rcd,'name','RCD-Bezeichnung')
            choice(rcd,'type','RCD-Typ',['AC','A','F','B','B+'])
            choice(rcd,'delay','Zeitverhalten',['unverzögert','G','S','Herstellerangabe'])
            number(rcd,'idn_ma','IΔN [mA]')
            approval(rcd)
            checks(rcd['checks'])
            if st.button('Prüfschritt ergänzen',key='step'+rcd['id']):
                rcd['tests'].append(new_rcd_test())
                st.rerun()
            for test in rcd['tests']:
                st.markdown('**Prüfschritt '+test['id'][:8]+'**')
                choice(test,'mode','Messart',['Zeitprüfung','Rampenprüfung'])
                choice(test,'waveform','Prüfstromform',['AC','A','F','B/DC'])
                number(test,'factor','Prüfstromfaktor × IΔN')
                choice(test,'polarity','Polarität',['0°','180°','Herstellerverfahren'])
                choice(test,'expected','Erwartetes Verhalten',['Auslösung','Keine Auslösung'])
                choice(test,'tripped','Ausgelöst?',[None,True,False])
                for field,label in [('time_ms','Auslösezeit [ms]'),('current_ma','Auslösestrom [mA]'),('max_time_ms','Zulässige Zeit [ms]'),
                                    ('min_current_ma','Zulässiger Mindeststrom [mA]'),('max_current_ma','Zulässiger Höchststrom [mA]')]:
                    number(test,field,label)
                approval(test)
                choice(test,'severity','Mängelklasse',CLASSES)
            st.caption('Typ F und zusätzliche Herstellerprüfungen: Prüfschritte erfassen; automatische Gesamtfreigabe bleibt bis zu einem belegten Typ-F-Regelprofil offen.')
with tabs[5]:
    st.subheader('Anlagenprüfkatalog')
    checks(p['checks'])
with tabs[6]:
    st.subheader('Mängel und Nachweise')
    targets=[dict(id=p['id'],name='Anlage')]+p['boards']+p['points']+p['rcds']
    with st.form('manual_defect'):
        target=st.selectbox('Bezug',targets,format_func=lambda t:t['name'])
        title=st.text_input('Mangelbeschreibung')
        severity=st.selectbox('Klasse',['S1','S2','S3'],index=1)
        st.caption('S1 leichter Mangel · S2 erheblicher Mangel · S3 kritisch; fachlich begründet zuordnen.')
        details=st.text_area('Maßnahme / Begründung')
        due=st.text_input('Behebungsfrist (JJJJ-MM-TT)')
        catalog=st.selectbox('Optionaler Katalogeintrag',[None]+p['catalog'],format_func=lambda c: '—' if c is None else c['id']+' · '+c['title']+' · '+c['severity'])
        if st.form_submit_button('Mangel erfassen') and (title.strip() or catalog):
            defect=manual_defect(target['id'],title.strip() or catalog['title'],catalog['severity'] if catalog else severity,details,due)
            if catalog:
                defect['catalog_id']=catalog['id']
            p['defects'].append(defect)
            st.rerun()
    sync_defects(p,evaluate(p))
    for defect in p['defects']:
        with st.expander(defect['title']+' · '+defect['severity']+' · '+defect['state']):
            st.caption('Automatisch' if defect['automatic'] else 'Manuell')
            if not defect['automatic']:
                text(defect,'title','Beschreibung')
                choice(defect,'severity','Klasse',CLASSES)
                old=defect['state']
                choice(defect,'state','Bearbeitungsstatus',['Offen','Behoben'])
                if old!=defect['state']:
                    defect['history'].append(dict(at=now(),state=defect['state']))
                text(defect,'details','Maßnahme / Details',True)
            else:
                st.write(defect['details'])
                st.caption('Automatisch behoben erst bei positivem Wiederholungsnachweis.')
            text(defect,'due','Behebungsfrist')
            st.json(defect['history'])
    photo=st.file_uploader('Foto hinzufügen (PNG/JPEG, höchstens 2 MiB)',type=['png','jpg','jpeg'])
    photo_target=st.selectbox('Foto-Bezug',targets,format_func=lambda t:t['name'],key='photo_target')
    if photo and st.button('Foto übernehmen'):
        raw=photo.getvalue()
        if len(raw)>2*1024*1024 or sum(len(a.get('base64','')) for a in p['attachments'])+len(raw)*4/3>6*1024*1024:
            st.error('Fotolimit überschritten (2 MiB je Bild / 6 MiB kodiert insgesamt).')
        elif not (raw.startswith(b'\x89PNG\r\n\x1a\n') or raw.startswith(b'\xff\xd8\xff')):
            st.error('Datei ist kein unterstütztes Bild.')
        else:
            p['attachments'].append(dict(id=uid(),target_id=photo_target['id'],name=photo.name,
                mime='image/png' if raw.startswith(b'\x89PNG') else 'image/jpeg',base64=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest()))
            st.rerun()
    for a in p['attachments']:
        st.image(base64.b64decode(a['base64']),caption=a['name'],width=240)
with tabs[7]:
    st.subheader('Messgeräte-CSV / Metrel-CSV mit Spaltenzuordnung')
    st.caption('Kein proprietärer Metrel-Dateiparser. CSV-Spalten werden ausdrücklich auf bestehende Messpunkt-IDs abgebildet. Bestehende Messwerte bleiben standardmäßig erhalten.')
    st.download_button('CSV-Importvorlage',csv_template(),file_name='messwerte_vorlage.csv')
    upload=st.file_uploader('Messwerte-CSV',type=['csv'])
    mapping_text=st.text_area('Optionale Spaltenzuordnung als JSON',value='{}',help='Beispiel: {"point_id":"Messpunkt-ID","zs_ohm":"Zs"}')
    overwrite=st.checkbox('Bestehende Messwerte beim Import ausdrücklich ersetzen',value=False)
    if upload:
        try:
            mapping=json.loads(mapping_text)
            if not isinstance(mapping,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in mapping.items()):
                raise ValueError('Spaltenzuordnung muss ein Objekt aus Textwerten sein.')
            rows=parse_measurement_csv(upload.getvalue().decode('utf-8-sig'),mapping or None)
            st.dataframe(rows)
            if st.button('Vorschau übernehmen'):
                replace(apply_measurements(p,rows,upload.name,overwrite))
        except (ValueError,UnicodeError) as exc:
            st.error(str(exc))
    st.subheader('Eigenen Mängelkatalog importieren')
    st.caption('JSON-Liste mit id, title, severity (S1/S2/S3). Der frühere 467er-Katalog liegt im Repository nicht vor.')
    cat=st.file_uploader('Mängelkatalog JSON',type=['json'],key='catalog_upload')
    if cat and st.button('Katalog laden'):
        try:
            if cat.size>1024*1024:
                raise ValueError('Katalog zu groß.')
            data=json.loads(cat.getvalue())
            if not isinstance(data,list) or not all(isinstance(c,dict) and isinstance(c.get('id'),str) and isinstance(c.get('title'),str) and c.get('severity') in CLASSES for c in data):
                raise ValueError('Ungültiger Katalog.')
            if len({c['id'] for c in data})!=len(data):
                raise ValueError('Doppelte Katalog-IDs.')
            p['catalog']=data
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

findings=evaluate(p)
sync_defects(p,findings)
findings=evaluate(p)
result=summary(p,findings)

try:
    validate(p)
    digest=hashlib.sha256(json.dumps(p,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    if autosave and digest!=st.session_state.get('saved_hash'):
        revision=storage.save(p,p['inspection']['inspector'] or 'Entwurf')
        st.session_state.saved_hash=hashlib.sha256(json.dumps(p,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        st.sidebar.success(f'Gesichert: Revision {revision}')
except (OSError,ValueError,sqlite3.Error) as exc:
    st.sidebar.error('Nicht gesichert: '+str(exc))


with tabs[8]:
    st.subheader('Gesamtbewertung: '+result['traffic'])
    st.write('Prüfung vollständig:',result['complete'],'· Positive Gesamtbewertung:',result['positive'])
    st.write('Offene Prüfschritte:',result['open_checks'],'· Offene Mängel:',result['open_defects'])
    if not result['complete']:
        st.warning('ENTWURF – unvollständige Prüfung. Ein Export dient dem Arbeitsstand und ist kein positiver Abschlussbefund.')
    st.dataframe(findings)
    name=safe_name(p['plant']['asset_id'])
    st.download_button('Vollständiges JSON-Backup',json_export(p),file_name=f'anlagenbuch_{name}.json',mime='application/json')
    st.download_button('Markdown-Bericht',markdown_export(p),file_name=f'pruefbericht_{name}.md',mime='text/markdown')
    st.download_button('HTML-Bericht (druckbar)',html_export(p),file_name=f'pruefbericht_{name}.html',mime='text/html')
    st.download_button('Messwerte-CSV',csv_export(p),file_name=f'messwerte_{name}.csv',mime='text/csv')
    st.download_button('RCD-Messwerte-CSV',rcd_csv_export(p),file_name=f'rcd_{name}.csv',mime='text/csv')
    st.caption('E-Attest: Die CSV ist eine interne Vorbereitung. Zielvorlage und bestätigter Importtest fehlen; deshalb keine bestätigte Schnittstellenkompatibilität.')
