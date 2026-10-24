"""Conservative rule evaluation: missing evidence is never a pass."""
from domain import positive, nonnegative, now


def finding(target, rule, title, status='OFFEN', severity='S2', **evidence):
    return dict(target_id=target, rule=rule, title=title, status=status,
                severity=severity, evidence=evidence)


def approved(row):
    return bool(str(row.get('reference','')).strip() and str(row.get('approved_by','')).strip())


def circuit_limits(circuit, rules):
    """B/C/D instantaneous factors are calculation aids, not blanket norm approvals."""
    if not positive(rules.get('u0_v')) or not positive(circuit.get('required_time_s')):
        return None
    ia = circuit.get('ia_a')
    if ia is None and circuit.get('device') in ('LS','FI/LS'):
        factor = {'B':5, 'C':10, 'D':20}.get(circuit.get('curve'))
        if factor and positive(circuit.get('in_a')):
            ia = factor * circuit['in_a']
    if not positive(ia) or circuit.get('mode') not in ['Normal','Mit 2/3 Reserve']:
        return None
    reserve = 2/3 if circuit['mode'] == 'Mit 2/3 Reserve' else 1
    return dict(ia_a=ia, z_max_ohm=reserve * rules['u0_v'] / ia,
                ik_min_a=ia / reserve, reserve=reserve,
                required_time_s=circuit['required_time_s'],
                zi_max_ohm=(reserve * rules['u0_v'] / circuit['zi_ia_a']) if positive(circuit.get('zi_ia_a')) else None,
                ik_zi_min_a=circuit['zi_ia_a'] / reserve if positive(circuit.get('zi_ia_a')) else None)


def compare(value, limit, maximum=True, strict=True):
    if not nonnegative(value) or not positive(limit):
        return 'OFFEN'
    ok = (value < limit if strict else value <= limit) if maximum else (value > limit if strict else value >= limit)
    return 'OK' if ok else 'FEHLER'


def evaluate_point(point, circuit, rules, network):
    target = point['id']
    output = []
    limits = circuit_limits(circuit, rules) if circuit else None
    for zkey, ikkey in [('zs_ohm','ik_zs_a'), ('zi_ohm','ik_zi_a')]:
        z, ik = point.get(zkey), point.get(ikkey)
        # The raw measurement is never changed by an optional derivation.
        calculated = bool(ik is None and point.get('derive_ik') and positive(z))
        if calculated:
            ik = rules['u0_v'] / z if positive(rules.get('u0_v')) else None
        for key, value, maximum in [(zkey,z,True),(ikkey,ik,False)]:
            reason = str(point.get('excluded',{}).get(key,'')).strip()
            if reason:
                output.append(finding(target,key,'Ausgenommen: '+reason,'N/A'))
                continue
            usable = limits and approved(circuit) and approved(rules) and network == 'TN'
            if zkey == 'zi_ohm':
                usable = usable and positive(circuit.get('zi_required_time_s')) and bool(circuit.get('zi_reference','').strip())
            limit = ((limits['z_max_ohm'] if maximum else limits['ik_min_a']) if zkey=='zs_ohm'
                     else (limits['zi_max_ohm'] if maximum else limits['ik_zi_min_a'])) if limits else None
            status = compare(value, limit, maximum, rules['strict_limits']) if usable else 'OFFEN'
            if maximum and value is not None and not positive(value):
                status = 'FEHLER'
            output.append(finding(target,key,key,status, value=value,
                limit=limit,
                derived=calculated if key == ikkey else False,
                reference=circuit.get('reference','') if circuit else '',
                note='Automatischer Abschaltnachweis nur für freigegebenes TN-Regelprofil'))
        if positive(z) and positive(point.get(ikkey)) and positive(rules.get('u0_v')):
            expected = rules['u0_v'] / z
            deviation = abs(point[ikkey] - expected) / expected
            output.append(finding(target,zkey+'_plausibility','Z/Ik-Plausibilität',
                'WARNUNG' if deviation > rules['plausibility_tolerance'] else 'OK',
                measured=point[ikkey], calculated=expected, deviation=deviation))
        if ik is not None and not positive(ik):
            output.append(finding(target,ikkey+'_invalid','Ik muss positiv sein','FEHLER'))
    capacity = circuit.get('breaking_capacity_a') if circuit else None
    if positive(capacity) and any(positive(point.get(k)) and point[k] > capacity for k in ['ik_zs_a','ik_zi_a']):
        output.append(finding(target,'breaking_capacity','Gemessener Ik über Ausschaltvermögen','FEHLER','S3',capacity=capacity))
    for key, limit_key, maximum in [('riso_mohm','riso_min_mohm',False), ('rpe_ohm','rpe_max_ohm',True)]:
        reason = str(point.get('excluded',{}).get(key,'')).strip()
        ready = approved(point) and approved(rules) and bool(point.get('method','').strip())
        if key == 'riso_mohm':
            ready = ready and positive(point.get('insulation_test_v'))
        status = 'N/A' if reason else (compare(point.get(key),point.get(limit_key),maximum,rules['strict_limits']) if ready else 'OFFEN')
        output.append(finding(target,key,key,status,value=point.get(key),limit=point.get(limit_key),
                              reference=point.get('reference',''), exclusion=reason))
    if point.get('required_rotation'):
        status = {'Rechts':'OK', 'Links':'FEHLER'}.get(point.get('rotation'), 'OFFEN')
        output.append(finding(target,'rotation','Drehfeld',status))
    return output


def evaluate_rcd(rcd, rules, plant):
    out = []
    if rcd['type'] == 'AC' and plant['scope'] in ['Neuanlage','Änderung/Erweiterung'] and rules['edition'] == 'OVE E 8101:2025-10-01':
        out.append(finding(rcd['id'],'type_ac','Typ AC bei Neuanlage/Änderung/Erweiterung','FEHLER',
            reference='OVE E 8101:2025-10-01; OVE Änderungsübersicht'))
    supported = {'AC':{'AC'}, 'A':{'AC','A'}, 'B':{'AC','A','B/DC'}, 'B+':{'AC','A','B/DC'}}
    required = supported.get(rcd['type'])
    actual = {t['waveform'] for t in rcd['tests']}
    if not rcd['tests'] or required is None or not required <= actual:
        out.append(finding(rcd['id'],'coverage','RCD-Prüfplan / Stromformen unvollständig'))
    for test in rcd['tests']:
        ready = approved(test) and approved(rcd) and approved(rules) and positive(rcd['idn_ma']) and positive(test['factor'])
        if required and test['waveform'] not in required:
            ready = False
        status = 'OFFEN'
        if ready and isinstance(test['tripped'], bool):
            if test['expected'] == 'Keine Auslösung':
                status = 'FEHLER' if test['tripped'] else 'OK'
            elif test['expected'] == 'Auslösung':
                if test['tripped'] is False:
                    status = 'FEHLER'
                elif test['mode'] == 'Rampenprüfung':
                    lo, hi, value = test['min_current_ma'],test['max_current_ma'],test['current_ma']
                    if positive(lo) and positive(hi) and lo <= hi and nonnegative(value):
                        status = 'OK' if lo <= value <= hi else 'FEHLER'
                    if test['max_time_ms'] is not None:
                        time_status = compare(test['time_ms'],test['max_time_ms'],True,rules['strict_limits'])
                        if status != 'FEHLER':
                            status = time_status if time_status != 'OK' else status
                elif test['time_ms'] is not None and not positive(test['time_ms']):
                    status = 'FEHLER'
                elif positive(test['max_time_ms']) and positive(test['time_ms']):
                    status = compare(test['time_ms'], test['max_time_ms'], True, rules['strict_limits'])
                    if test['min_current_ma'] is not None or test['max_current_ma'] is not None:
                        lo, hi, value = test['min_current_ma'],test['max_current_ma'],test['current_ma']
                        if not (positive(lo) and positive(hi) and lo <= hi and nonnegative(value)):
                            status = 'OFFEN'
                        elif not lo <= value <= hi:
                            status = 'FEHLER'
        out.append(finding(rcd['id'],'rcd_'+test['id'],'RCD '+test['waveform']+' '+str(test['factor'])+'×IΔN',
                           status,test['severity'], test=test.copy(), reference=test['reference']))
    return out


def evaluate(project):
    out = []
    rules = project['rules']
    for section, keys in [('plant',['company','site','name','asset_id']),
                          ('inspection',['inspector','date','kind','device','calibration','scope','next_due','interval_basis'])]:
        for key in keys:
            if not str(project[section].get(key,'')).strip():
                out.append(finding(project['id'],section+'_'+key,'Pflichtangabe fehlt: '+key))
    if not approved(rules) or not rules['approved_at'] or not rules['scope_note'].strip() or not rules['legal_basis'].strip():
        out.append(finding(project['id'],'rules','Normgrundlage / fachliche Regelfreigabe fehlt'))
    if not positive(rules.get('u0_v')) or not nonnegative(rules.get('plausibility_tolerance')):
        out.append(finding(project['id'],'rule_values','Ungültige Rechenparameter'))
    try:
        date = __import__('datetime').date.fromisoformat(project['inspection']['date'])
        due = __import__('datetime').date.fromisoformat(project['inspection']['next_due'])
        if due <= date:
            out.append(finding(project['id'],'due','Nächster Prüftermin muss nach dem Prüfdatum liegen'))
    except (ValueError, TypeError):
        out.append(finding(project['id'],'dates','Prüfdatum / nächster Termin fehlt oder ungültig'))
    try:
        __import__('datetime').date.fromisoformat(rules['approved_at'])
    except (ValueError,TypeError):
        out.append(finding(project['id'],'rule_date','Gültiges Freigabedatum fehlt'))
    for defect in project['defects']:
        if defect['state']=='Offen':
            try:
                __import__('datetime').date.fromisoformat(defect['due'])
            except (ValueError,TypeError):
                out.append(finding(defect['id'],'defect_due','Behebungsfrist fehlt / ungültig'))
    if not project['boards'] or not project['points']:
        out.append(finding(project['id'],'structure','Verteiler / Messpunkte fehlen'))
    circuits = {c['id']:c for c in project['circuits']}
    for target, checks in [(project['id'],project['checks'])] + [(b['id'],b['checks']) for b in project['boards']] + [(r['id'],r['checks']) for r in project['rcds']]:
        if not checks:
            out.append(finding(target,'checks','Prüfkatalog fehlt'))
        for check in checks:
            status = {'OK':'OK','Mangel':'FEHLER','N/A':'N/A'}.get(check['status'],'OFFEN')
            if status == 'N/A' and not check['reason'].strip():
                status = 'OFFEN'
            out.append(finding(target,'check_'+check['id'],check['criterion'],status,check['severity'],reason=check['reason']))
    for circuit in project['circuits']:
        if not any(p['circuit_id'] == circuit['id'] for p in project['points']):
            out.append(finding(circuit['id'],'coverage','Stromkreis ohne Messpunkt'))
    identities = set()
    for point in project['points']:
        identity = (point['board_id'],point['room'].strip().casefold(),point['name'].strip().casefold(),point['phase'])
        if identity in identities:
            out.append(finding(point['id'],'duplicate','Doppelter Messpunkt','WARNUNG'))
        identities.add(identity)
        out.extend(evaluate_point(point,circuits.get(point['circuit_id']),rules,project['plant']['network']))
    for rcd in project['rcds']:
        out.extend(evaluate_rcd(rcd,rules,project['plant']))
    # A project with all tests excluded cannot receive a positive completion.
    if not any(f['status'] == 'OK' and f['rule'] in ['zs_ohm','zi_ohm','ik_zs_a','ik_zi_a','riso_mohm','rpe_ohm'] and f['target_id'] in {p['id'] for p in project['points']} for f in out):
        out.append(finding(project['id'],'evidence','Keine positiv bewertete Messung vorhanden'))
    return out


def sync_defects(project, findings):
    """Stable target+rule identity; preserve manual entries and status history."""
    from domain import manual_defect
    existing = {(d['target_id'],d['rule']):d for d in project['defects'] if d['automatic']}
    active = set()
    for f in findings:
        if f['status'] not in ['FEHLER','WARNUNG']:
            continue
        key = (f['target_id'],f['rule'])
        active.add(key)
        d = existing.get(key)
        if d is None:
            d = manual_defect(f['target_id'],f['title'],f['severity'])
            d.update(automatic=True,rule=f['rule'])
            project['defects'].append(d)
            existing[key] = d
        if d['state'] != 'Offen':
            d['state'] = 'Offen'
            d['history'].append(dict(at=now(),state='Offen'))
        d.update(title=f['title'],severity=f['severity'],details=str(f['evidence']))
    for key, d in existing.items():
        # Unknown / removed evidence does not prove remediation.
        current = next((f for f in findings if (f['target_id'],f['rule']) == key), None)
        if key not in active and current and current['status'] == 'OK' and d['state'] != 'Behoben':
            d['state'] = 'Behoben'
            d['history'].append(dict(at=now(),state='Behoben'))


def summary(project, findings):
    defects = [d for d in project['defects'] if d['state'] == 'Offen']
    complete = not any(f['status'] == 'OFFEN' for f in findings)
    failures = [f for f in findings if f['status'] in ['FEHLER','WARNUNG']]
    severities = [d['severity'] for d in defects] + [f['severity'] for f in failures]
    if 'S3' in severities or 'S2' in severities:
        traffic = 'ROT'
    elif severities:
        traffic = 'GELB'
    elif complete:
        traffic = 'GRÜN'
    else:
        traffic = 'GRAU'
    return dict(traffic=traffic, complete=complete, positive=complete and not defects and not failures,
                open_checks=sum(f['status']=='OFFEN' for f in findings), open_defects=len(defects))
