"""Local SQLite revisions. Each save is an immutable, transactionally committed snapshot."""
import hashlib
from contextlib import closing
import copy
import json
import os
from pathlib import Path
import sqlite3
from domain import validate, now
from exports import load_json


def connect(path=None):
    path = Path(path or os.environ.get('INSPECTION_DB','data/inspections.sqlite3'))
    path.parent.mkdir(parents=True,exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS revisions (revision INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, created_at TEXT NOT NULL, actor TEXT NOT NULL, content TEXT NOT NULL, digest TEXT NOT NULL)')
    return db


def change_log(before, after, path=''):
    changes = []
    if isinstance(before,dict) and isinstance(after,dict):
        for key in sorted(set(before) | set(after)):
            if key != 'audit':
                changes.extend(change_log(before.get(key),after.get(key),path+'/'+key))
    elif isinstance(before,list) and isinstance(after,list):
        if all(isinstance(r,dict) and 'id' in r for r in before+after):
            changes.extend(change_log({r['id']:r for r in before},{r['id']:r for r in after},path))
        elif before != after:
            changes.append(dict(field=path,before=before,after=after))
    elif before != after:
        def short(value):
            if len(str(value))>256:
                return {'sha256':hashlib.sha256(str(value).encode()).hexdigest(),'note':'Vollwert in Revision'}
            return value
        changes.append(dict(field=path,before=short(before),after=short(after)))
    return changes


def save(project, actor, path=None):
    validate(project)
    with closing(connect(path)) as db, db:
        previous = db.execute('SELECT content FROM revisions WHERE project_id=? ORDER BY revision DESC LIMIT 1',(project['id'],)).fetchone()
        before = json.loads(previous[0]) if previous else {}
        changes = change_log(before,project)
        saved = copy.deepcopy(project)
        if changes:
            saved['audit'].append(dict(at=now(),action='Revision gespeichert',actor=actor,changes=changes))
        content = json.dumps(saved,ensure_ascii=False,sort_keys=True,allow_nan=False)
        digest = hashlib.sha256(content.encode()).hexdigest()
        cursor = db.execute('INSERT INTO revisions(project_id,created_at,actor,content,digest) VALUES(?,?,?,?,?)',
                            (project['id'],now(),actor,content,digest))
        revision = cursor.lastrowid
    project['audit'] = saved['audit']
    return revision


def revisions(path=None):
    with closing(connect(path)) as db, db:
        return db.execute('SELECT revision,project_id,created_at,actor FROM revisions ORDER BY revision DESC').fetchall()


def load(revision,path=None):
    with closing(connect(path)) as db, db:
        row = db.execute('SELECT content,digest FROM revisions WHERE revision=?',(revision,)).fetchone()
    if row is None:
        raise ValueError('Revision nicht gefunden.')
    if hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
        raise ValueError('Prüfsumme stimmt nicht überein.')
    return load_json(row[0])
