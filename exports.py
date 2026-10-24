"""Lossless backup plus escaped human-readable and tabular projections."""
import copy
import csv
import html
import io
import json
import re
from domain import validate, migrate_legacy, now, METRICS, nonnegative
from engine import evaluate, sync_defects, summary

MAX_IMPORT_BYTES = 10 * 1024 * 1024


def snapshot(project):
    p = copy.deepcopy(project)
    findings = evaluate(p)
    sync_defects(p,findings)
    findings = evaluate(p)
    return dict(project=p, result=summary(p,findings), findings=findings, exported_at=now(),
                compatibility='Internes Schema v2; keine bestätigte E-Attest-Schnittstelle')


def json_export(project):
    return json.dumps(snapshot(project),ensure_ascii=False,indent=2,allow_nan=False)


def load_json(raw):
    if len(raw) > MAX_IMPORT_BYTES:
        raise ValueError('Import ist größer als 10 MiB.')
    def no_constant(value):
        raise ValueError('Nicht endliche Zahl: '+value)
    try:
        data = json.loads(raw,parse_constant=no_constant)
        if not isinstance(data,dict):
            raise ValueError('JSON-Objekt erwartet.')
        p = data.get('project',data)
        if isinstance(p,dict) and 'anlage' in p:
            p = migrate_legacy(p)
        return validate(p)
    except (KeyError,TypeError,AttributeError,OverflowError) as exc:
        raise ValueError('Ungültige Projektstruktur.') from exc


def safe_name(asset_id):
    return re.sub(r'[^\w.-]+','_',asset_id,flags=re.UNICODE).strip('._')[:80] or 'anlage'


def md(value):
    return str(value).replace('\\','\\\\').replace('\n',' / ').replace('\r','').replace('|','\\|').replace('<','&lt;').replace('>','&gt;').replace('*','\\*').replace('[','\\[').replace(']','\\]')


def markdown_export(project):
    data = snapshot(project)
    p, result = data['project'],data['result']
    lines = ['# Prüfbericht / Anlagenbuch', '',
             '**'+('ENTWURF – Prüfung unvollständig' if not result['complete'] else 'Prüfung vollständig erfasst')+'**',
             '', 'Dieser Bericht dokumentiert die Bewertung; er ist keine digitale Signatur.', '',
             '## Anlage', '']
    for key,value in p['plant'].items():
        lines.append(f'- **{md(key)}:** {md(value)}')
    lines += ['', '## Prüfung', '']
    for key,value in p['inspection'].items():
        lines.append(f'- **{md(key)}:** {md(value)}')
    lines += ['', f"Gesamtbewertung: **{result['traffic']}**; offene Prüfschritte: {result['open_checks']}",
              '', '## Regelgrundlage', '', '```json', json.dumps(p['rules'],ensure_ascii=False,indent=2), '```',
              '', '## Verteiler / Stromkreise / Messpunkte', '']
    for group in ['boards','circuits','points','rcds']:
        lines += [f'### {group}', '', '```json',json.dumps(p[group],ensure_ascii=False,indent=2),'```','']
    lines += ['## Einzelbewertungen', '']
    for f in data['findings']:
        lines.append(f"- [{f['status']}] {md(f['target_id'])}: {md(f['title'])} — {md(json.dumps(f['evidence'],ensure_ascii=False))}")
    lines += ['', '## Mängel', '']
    if not p['defects']:
        lines.append('Keine Mängel erfasst. Dies bestätigt keine vollständige Prüfung.')
    for d in p['defects']:
        lines += [f"- **{md(d['title'])}** ({d['severity']}, {d['state']}, Frist: {md(d['due'])})",
                  f"  - Bezug: {md(d['target_id'])}; {md(d['details'])}",
                  f"  - Verlauf: {md(json.dumps(d['history'],ensure_ascii=False))}"]
    lines += ['', '## Anhänge', '']
    lines += [f"- {md(a.get('name',''))} ({md(a.get('target_id',''))}); Bilddaten im JSON-Backup" for a in p['attachments']]
    return '\n'.join(lines)


def html_export(project):
    data = snapshot(project)
    p, result = data['project'], data['result']
    esc = lambda value: html.escape('' if value is None else str(value))
    def table(rows):
        if not rows:
            return '<p>Keine Einträge.</p>'
        fields = list(dict.fromkeys(k for row in rows for k in row))
        return '<table><thead><tr>'+''.join('<th>'+esc(k)+'</th>' for k in fields)+'</tr></thead><tbody>'+''.join(
            '<tr>'+''.join('<td>'+esc(json.dumps(row.get(k),ensure_ascii=False) if isinstance(row.get(k),(dict,list)) else row.get(k))+'</td>' for k in fields)+'</tr>' for row in rows)+'</tbody></table>'
    out = ['<!doctype html><html lang="de"><meta charset="utf-8"><title>Prüfbericht</title>',
           '<style>body{font:14px system-ui;margin:2rem;color:#172b38}table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:11px}td,th{border:1px solid #ccd4da;padding:6px;text-align:left;overflow-wrap:anywhere}th{background:#edf1f4}h2{margin-top:2rem}img{max-width:360px;max-height:280px}@media print{body{margin:0;font-size:10pt}table{font-size:8pt}tr{break-inside:avoid}}</style>',
           '<h1>Prüfbericht / Anlagenbuch</h1>',
           '<p><strong>'+('ENTWURF – Prüfung unvollständig' if not result['complete'] else 'Prüfung vollständig erfasst')+'</strong></p>',
           '<p>Gesamtbewertung: '+esc(result['traffic'])+' · Offene Prüfschritte: '+str(result['open_checks'])+'</p>',
           '<p>Dokumentation der Bewertung; keine digitale Signatur.</p>',
           '<h2>Anlage</h2>'+table([{'Feld':k,'Angabe':v} for k,v in p['plant'].items()]),
           '<h2>Prüfung</h2>'+table([{'Feld':k,'Angabe':v} for k,v in p['inspection'].items()]),
           '<h2>Regelgrundlage</h2>'+table([{'Feld':k,'Angabe':v} for k,v in p['rules'].items()])]
    for title,group in [('Verteiler','boards'),('Stromkreise','circuits'),('Messpunkte','points'),('RCD','rcds')]:
        out += ['<h2>'+title+'</h2>']
        for row in p[group]:
            out += ['<h3>'+esc(row['name'])+'</h3>',table([{'Feld':k,'Angabe':v} for k,v in row.items() if k not in ['checks','tests']])]
            for nested in ['checks','tests']:
                if nested in row:
                    out.append(table(row[nested]))
    out += ['<h2>Einzelbewertungen</h2>',table(data['findings']),'<h2>Mängel</h2>',table(p['defects']),'<h2>Fotos / Nachweise</h2>']
    for a in p['attachments']:
        if a['mime'] in ['image/png','image/jpeg']:
            out += ['<figure><img src="data:'+a['mime']+';base64,'+esc(a['base64'])+'"><figcaption>'+esc(a['name'])+' · '+esc(a['target_id'])+'</figcaption></figure>']
    out += ['<h2>Änderungsverlauf / Importe</h2>',table(p['audit']),'<p>'+esc(data['compatibility'])+'</p></html>']
    return ''.join(out)


def spreadsheet_safe(value):
    s = '' if value is None else str(value)
    return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s


def csv_export(project):
    data = snapshot(project)
    p = data['project']
    board_names = {b['id']:b['name'] for b in p['boards']}
    circuit_names = {c['id']:c['name'] for c in p['circuits']}
    fields = ['point_id','board_id','board','room','name','circuit_id','circuit','phase']+METRICS+[
        'rotation','measurement_source','measured_at','evaluation_json']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream,fieldnames=fields,delimiter=';')
    writer.writeheader()
    for point in p['points']:
        row = {f:point.get(f,'') for f in fields}
        row.update(point_id=point['id'],board=board_names.get(point['board_id'],''),
                   circuit=circuit_names.get(point['circuit_id'],''),
                   evaluation_json=json.dumps([f for f in data['findings'] if f['target_id']==point['id']],ensure_ascii=False))
        writer.writerow({k:spreadsheet_safe(v) for k,v in row.items()})
    return '\ufeff'+stream.getvalue()


def csv_template():
    return 'point_id;zs_ohm;zi_ohm;ik_zs_a;ik_zi_a;riso_mohm;rpe_ohm;rotation\n'


def parse_measurement_csv(text, mapping=None):
    """Explicit column mapping supports vendor CSVs, without claiming a native vendor parser."""
    if len(text.encode('utf-8')) > MAX_IMPORT_BYTES:
        raise ValueError('CSV zu groß.')
    try:
        dialect = csv.Sniffer().sniff(text[:4096],delimiters=';,\t')
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ';'
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')),dialect=dialect)
    mapping = mapping or {k:k for k in ['point_id']+METRICS+['rotation']}
    if not reader.fieldnames or mapping.get('point_id') not in reader.fieldnames:
        raise ValueError('Spalte für point_id fehlt; Zuordnung erforderlich.')
    rows = []
    ids = set()
    for line,row in enumerate(reader,start=2):
        point_id = str(row.get(mapping['point_id']) or '').strip()
        if not point_id or point_id in ids:
            raise ValueError(f'Zeile {line}: fehlende / doppelte point_id.')
        ids.add(point_id)
        result = dict(point_id=point_id)
        for key in METRICS:
            raw = str(row.get(mapping.get(key,'')) or '').strip()
            if raw:
                try:
                    value = float(raw.replace(',','.'))
                except ValueError as exc:
                    raise ValueError(f'Zeile {line}: ungültiger Wert {key}.') from exc
                if not nonnegative(value):
                    raise ValueError(f'Zeile {line}: ungültiger Wert {key}.')
                result[key] = value
        rotation = str(row.get(mapping.get('rotation','')) or '').strip()
        if rotation:
            if rotation not in ['Rechts','Links','Nicht geprüft']:
                raise ValueError(f'Zeile {line}: ungültiges Drehfeld.')
            result['rotation'] = rotation
        rows.append(result)
    return rows


def apply_measurements(project, rows, source, overwrite=False):
    p = copy.deepcopy(project)
    points = {point['id']:point for point in p['points']}
    for row in rows:
        if row['point_id'] not in points:
            raise ValueError('Unbekannte point_id: '+row['point_id'])
        point = points[row['point_id']]
        for key,value in row.items():
            if key == 'point_id':
                continue
            occupied = point.get(key) not in (None,'','Nicht geprüft')
            if occupied and not overwrite:
                raise ValueError(f'Vorhandener Wert wird nicht überschrieben: {key} / {point["id"]}')
            point[key] = value
        point.update(measurement_source=source,measured_at=now())
    p['audit'].append(dict(at=now(),action='Messwerte importiert',source=source,rows=len(rows)))
    return validate(p)


def rcd_csv_export(project):
    data = snapshot(project)
    fields = ['rcd_id','name','type','delay','idn_ma','test_id','mode','waveform','factor','polarity','expected','tripped',
              'time_ms','current_ma','max_time_ms','min_current_ma','max_current_ma','reference','approved_by','status']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream,fieldnames=fields,delimiter=';')
    writer.writeheader()
    for rcd in data['project']['rcds']:
        for test in rcd['tests']:
            row = {k:rcd.get(k,'') for k in fields}
            row.update({k:v for k,v in test.items() if k in fields})
            row.update(rcd_id=rcd['id'],test_id=test['id'],status=next(
                f['status'] for f in data['findings'] if f['target_id']==rcd['id'] and f['rule']=='rcd_'+test['id']))
            writer.writerow({k:spreadsheet_safe(v) for k,v in row.items()})
    return '\ufeff'+stream.getvalue()
