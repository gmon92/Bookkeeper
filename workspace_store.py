"""Per-user location preferences and validation for independent books folders."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

APP_ID = 0x4C424B50
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


def save_preferences(directory):
    CONFIG_PATH.parent.mkdir(parents=True,exist_ok=True)
    filename = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=CONFIG_PATH.parent,prefix='.settings-',suffix='.json',delete=False) as stream:
            filename = Path(stream.name)
            json.dump({'version':1,'directory':str(directory)},stream,indent=2)
            stream.flush(); os.fsync(stream.fileno())
        filename.replace(CONFIG_PATH)
    finally:
        if filename: filename.unlink(missing_ok=True)


def directory_path(value):
    if not isinstance(value,str) or not value.strip(): raise ValueError('Choose a books folder.')
    path = Path(os.path.expandvars(value.strip())).expanduser()
    if not path.is_absolute(): raise ValueError('Enter an absolute folder path or use Browse.')
    path = path.resolve()
    if path.is_file(): raise ValueError('Choose the folder containing the database, rather than a file.')
    return path


def validate_existing(directory):
    database = directory/'bookkeeper.sqlite3'
    if not database.is_file(): raise ValueError('No bookkeeper.sqlite3 database was found in that folder.')
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
    documents = Path.home()/'Documents'
    return (documents if documents.is_dir() else Path.home())/'Local Bookkeeper Books'


def choose_directory(initial=''):
    # A separate main-thread GUI process keeps the local HTTP server responsive.
    try:
        result = subprocess.run([sys.executable,str(Path(__file__).resolve()),'browse',initial],
            capture_output=True,encoding='utf-8',env=dict(os.environ,PYTHONIOENCODING='utf-8'),timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ValueError('The folder picker could not open. Enter the folder path instead.') from exc
    if result.returncode:
        raise ValueError('The folder picker is unavailable. Enter or paste the folder path instead.')
    return result.stdout.strip()


if __name__ == '__main__' and len(sys.argv)>1 and sys.argv[1]=='browse':
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk(); root.withdraw(); root.attributes('-topmost',True)
    options = {'parent':root,'title':'Choose a Local Bookkeeper books folder','mustexist':False}
    if len(sys.argv)>2 and Path(sys.argv[2]).is_dir(): options['initialdir'] = sys.argv[2]
    selected = filedialog.askdirectory(**options)
    root.destroy()
    print(selected)
