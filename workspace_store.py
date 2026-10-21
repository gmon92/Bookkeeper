"""Per-user location preferences and validation for independent books folders."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from contextlib import closing
from pathlib import Path

APP_ID = 0x4C424B50
PROFILE_FORMAT = 'local-bookkeeper-profile'
DEFAULT_SETTINGS = {'workspace':'all','year':'all','groupImportsBySourceCategory':False,'sort':'date-desc'}
CONFIG_PATH = Path(os.environ.get('LOCAL_BOOKKEEPER_CONFIG',
    str(Path(os.environ.get('LOCALAPPDATA', Path.home()/'.config'))/'LocalBookkeeper'/'settings.json'))).expanduser().resolve()


def load_preferences():
    if not CONFIG_PATH.is_file(): return {}, ''
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        if not isinstance(value,dict) or not isinstance(value.get('directory'),str): raise ValueError()
        return value, ''
    except (OSError,ValueError):
        return {}, 'The saved books location could not be read. Choose your existing books folder again.'


def atomic_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    filename = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.settings-',suffix='.json',delete=False) as stream:
            filename = Path(stream.name)
            json.dump(value,stream,indent=2)
            stream.flush(); os.fsync(stream.fileno())
        filename.replace(path)
    finally:
        if filename: filename.unlink(missing_ok=True)


def save_preferences(directory, database=None, profile=None, name=None):
    previous,_=load_preferences()
    database=Path(database or directory/'bookkeeper.sqlite3')
    location=str(profile or database)
    recent=[{'path':location,'name':name or directory.name}]
    for item in previous.get('recentProfiles',[]):
        if isinstance(item,dict) and isinstance(item.get('path'),str) and item['path']!=location:
            recent.append({'path':item['path'],'name':str(item.get('name') or Path(item['path']).stem)})
    atomic_json(CONFIG_PATH,{'version':2,'directory':str(directory),'database':str(database),
        'profile':str(profile) if profile else None,'recentProfiles':recent[:12]})


def absolute_path(value):
    if not isinstance(value,str) or not value.strip(): raise ValueError('Choose a profile, database file or books folder.')
    path=Path(os.path.expandvars(value.strip().strip('"'))).expanduser()
    if not path.is_absolute(): raise ValueError('Enter an absolute path or use Browse.')
    return path.resolve()


def locate_books(value):
    path=absolute_path(value)
    if not path.exists(): raise ValueError('That location was not found. Choose the existing profile, SQLite database or books folder.')
    profile=None
    if path.is_dir():
        if (path/'bookkeeper.profile.json').is_file(): path=path/'bookkeeper.profile.json'
        elif (path/'bookkeeper.sqlite3').is_file():path=path/'bookkeeper.sqlite3'
        else:
            profiles=list(path.glob('*.profile.json'))
            if len(profiles)!=1:raise ValueError('Choose the profile or SQLite file directly; this folder does not identify a single books database.')
            path=profiles[0]
    if path.suffix.lower()=='.json':
        if path.stat().st_size>65536: raise ValueError('This profile file is too large.')
        try: value=json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError,ValueError) as exc: raise ValueError('The profile file could not be read.') from exc
        if not isinstance(value,dict) or value.get('format')!=PROFILE_FORMAT or value.get('version')!=1 or not isinstance(value.get('database'),str) or not value['database'].strip():
            raise ValueError('Choose a Local Bookkeeper .profile.json file or a SQLite database.')
        profile=path
        reference=Path(value['database'])
        path=(reference if reference.is_absolute() else profile.parent/reference).resolve()
    if not path.is_file(): raise ValueError('The profile database was not found. Keep the profile and its database together, or choose the SQLite file directly.')
    with path.open('rb') as stream: signature=stream.read(16)
    if signature!=b'SQLite format 3\x00':
        if path.suffix.lower()=='.zip': raise ValueError('This is a backup ZIP. Choose Restore backup and a new destination folder.')
        raise ValueError('This is not a SQLite database. SQL text exports and statements cannot be opened as books. Choose the SQLite file, a .profile.json file, or restore a backup ZIP.')
    return {'directory':path.parent,'database':path,'profile':profile}


def profile_document(db, database_name):
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_metadata'").fetchone()
    row=db.execute("SELECT value FROM app_metadata WHERE key='profile_name'").fetchone() if exists else None
    return {'format':PROFILE_FORMAT,'version':1,'name':row[0] if row else 'My books','database':database_name}


def profile_settings(db):
    row=db.execute("SELECT value FROM app_metadata WHERE key='profile_settings'").fetchone()
    try: saved=json.loads(row[0]) if row else {}
    except ValueError: saved={}
    return DEFAULT_SETTINGS|saved if isinstance(saved,dict) else dict(DEFAULT_SETTINGS)


def save_profile_settings(db, updates):
    if not isinstance(updates,dict) or not set(updates)<=set(DEFAULT_SETTINGS): raise ValueError('Choose supported profile settings.')
    if 'groupImportsBySourceCategory' in updates and type(updates['groupImportsBySourceCategory']) is not bool: raise ValueError('The import grouping setting must be true or false.')
    if 'workspace' in updates:
        value=updates['workspace']
        if not isinstance(value,str) or (value not in ('all','personal') and not db.execute('SELECT id FROM businesses WHERE id=? AND active=1',(value,)).fetchone()): raise ValueError('Choose a business in this profile.')
    if 'year' in updates and (not isinstance(updates['year'],str) or (updates['year']!='all' and (len(updates['year'])!=4 or not updates['year'].isdigit()))): raise ValueError('Choose a reporting year or all years.')
    if 'sort' in updates and updates['sort'] not in ('date-desc','date-asc','amount-desc','amount-asc','merchant'):raise ValueError('Choose a valid transaction sort order.')
    settings=profile_settings(db)|updates
    db.execute("INSERT INTO app_metadata(key,value) VALUES('profile_settings',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(settings),))
    return settings


def save_profile(db, database, name=None, path=None):
    if name is not None and (not isinstance(name,str) or not name.strip() or len(name.strip())>100): raise ValueError('Enter a profile name between 1 and 100 characters.')
    db.execute("INSERT OR IGNORE INTO app_metadata VALUES('profile_name',?)",(database.parent.name,))
    if name is not None: db.execute("UPDATE app_metadata SET value=? WHERE key='profile_name'",(name.strip(),))
    save_profile_settings(db,{})
    explicit=path is not None
    path=path or database.with_suffix('.profile.json')
    if path.exists():
        try:existing=locate_books(str(path))
        except (ValueError,OSError):
            if explicit:raise
            existing=None
        if not existing or existing['database']!=database:
            if explicit:raise ValueError('That profile file points to different books. Choose the existing profile directly.')
            path=database.with_name(database.stem+'-'+uuid.uuid4().hex[:8]+'.profile.json')
    try: reference=os.path.relpath(database,path.parent)
    except ValueError: reference=str(database)
    atomic_json(path,profile_document(db,reference))
    return path


def directory_path(value):
    if not isinstance(value,str) or not value.strip(): raise ValueError('Choose a books folder.')
    path = Path(os.path.expandvars(value.strip())).expanduser()
    if not path.is_absolute(): raise ValueError('Enter an absolute folder path or use Browse.')
    path = path.resolve()
    if path.is_file(): raise ValueError('Choose the folder containing the database, rather than a file.')
    return path


def validate_existing(directory):
    database = locate_books(str(directory))['database']
    try:
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
            application_id = db.execute('PRAGMA application_id').fetchone()[0]
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {'businesses','accounts','categories','documents','transactions','transaction_history','review_actions','review_action_items'}
            if application_id not in (0,APP_ID) or not required <= tables:
                raise ValueError('This is not a Local Bookkeeper database. No changes were made.')
            if db.execute('PRAGMA user_version').fetchone()[0] > 8:
                raise ValueError('These books need a newer version of the app.')
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('The database needs recovery before it can be opened.')
    except sqlite3.Error as exc:
        raise ValueError('This database could not be read. Check the folder and file permissions.') from exc
    return database


def default_directory():
    if os.environ.get('LOCAL_BOOKKEEPER_BOOKS_DIR'):
        return absolute_path(os.environ['LOCAL_BOOKKEEPER_BOOKS_DIR'])
    documents = Path.home()/'Documents'
    return (documents if documents.is_dir() else Path.home())/'Local Bookkeeper Books'


def choose_directory(initial='', kind='directory'):
    if os.environ.get('LOCAL_BOOKKEEPER_STORAGE_ROOT'):
        raise ValueError('Enter a container path inside '+os.environ['LOCAL_BOOKKEEPER_STORAGE_ROOT']+'. Native file pickers are unavailable in Docker.')
    # A separate main-thread GUI process keeps the local HTTP server responsive.
    try:
        result = subprocess.run([sys.executable,str(Path(__file__).resolve()),'browse',initial,kind],
            capture_output=True,encoding='utf-8',env=dict(os.environ,PYTHONIOENCODING='utf-8'),timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ValueError('The location picker could not open. Enter the file or folder path instead.') from exc
    if result.returncode:
        raise ValueError('The location picker is unavailable. Enter or paste the file or folder path instead.')
    return result.stdout.strip()


if __name__ == '__main__' and len(sys.argv)>1 and sys.argv[1]=='browse':
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk(); root.withdraw(); root.attributes('-topmost',True)
    initial=Path(sys.argv[2]) if len(sys.argv)>2 and sys.argv[2] else Path.home()
    kind=sys.argv[3] if len(sys.argv)>3 else 'directory'
    options = {'parent':root,'title':'Choose your Local Bookkeeper profile','initialdir':str(initial if initial.is_dir() else initial.parent)}
    if kind=='directory': selected=filedialog.askdirectory(**options,mustexist=False)
    else:
        filters=[('Profile or SQLite database','*.profile.json *.sqlite3 *.sqlite *.db'),('All files','*.*')]
        if kind=='backup': filters=[('Profile export or backup','*.zip *.xlsx *.sqlite3 *.sqlite *.db'),('All files','*.*')]
        selected=filedialog.askopenfilename(**options,filetypes=filters)
    root.destroy()
    print(selected)
