"""Consistent local backup and offline restore into a new directory.

Restore: python backup.py restore PATH_TO_ZIP NEW_DATA_DIRECTORY
The server must be stopped before switching to the restored directory.
"""
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import workspace_store


def database_snapshot(database_path, destination_path):
    with closing(sqlite3.connect(database_path)) as source, closing(sqlite3.connect(destination_path)) as destination:
        source.backup(destination)
        if destination.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='staged_imports'").fetchone():
            destination.execute('DELETE FROM staged_imports')
        destination.commit()


def export_database(database_path):
    """Return a consistent standalone SQLite file, including committed WAL data."""
    with tempfile.TemporaryDirectory() as directory:
        copy = Path(directory)/'bookkeeper.sqlite3'
        database_snapshot(database_path,copy)
        return copy.read_bytes()


def create_backup(database_path, data_directory):
    result = io.BytesIO()
    with tempfile.TemporaryDirectory() as directory:
        copy = Path(directory) / 'bookkeeper.sqlite3'
        database_snapshot(database_path,copy)
        with closing(sqlite3.connect(copy)) as destination:
            paths = [r[0] for r in destination.execute('SELECT stored_path FROM documents')]
            profile=workspace_store.profile_document(destination,'bookkeeper.sqlite3')
        manifest = {'version':1,'files':{},'missingSources':[]}
        with ZipFile(result,'w',ZIP_DEFLATED) as archive:
            content = copy.read_bytes()
            archive.writestr('bookkeeper.sqlite3',content)
            manifest['files']['bookkeeper.sqlite3'] = hashlib.sha256(content).hexdigest()
            profile_bytes=json.dumps(profile,indent=2).encode('utf-8')
            archive.writestr('bookkeeper.profile.json',profile_bytes)
            manifest['files']['bookkeeper.profile.json']=hashlib.sha256(profile_bytes).hexdigest()
            for relative in sorted(set(paths)):
                path = (Path(data_directory)/relative).resolve()
                if not path.is_relative_to(Path(data_directory).resolve() / 'documents'):
                    raise ValueError('Managed document path is outside the documents directory.')
                if not path.is_file():
                    manifest['missingSources'].append(relative); continue
                content = path.read_bytes()
                archive.writestr(relative,content)
                manifest['files'][relative] = hashlib.sha256(content).hexdigest()
            archive.writestr('manifest.json',json.dumps(manifest,indent=2))
    return result.getvalue()


def restore_database(content, target_directory, allow_empty=False):
    target = Path(target_directory).resolve()
    if target.exists() and (not allow_empty or not target.is_dir() or any(target.iterdir())):
        raise ValueError('Restore requires a new directory. Existing books are never overwritten.')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        staging=Path(temporary)/'restored'; staging.mkdir()
        database=staging/'bookkeeper.sqlite3'; database.write_bytes(content)
        workspace_store.validate_existing(str(database))
        with closing(sqlite3.connect(database)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('The exported database failed its integrity check.')
            profile=workspace_store.profile_document(db,'bookkeeper.sqlite3')
            missing=[r[0] for r in db.execute('SELECT stored_path FROM documents')]
        (staging/'bookkeeper.profile.json').write_text(json.dumps(profile,indent=2),encoding='utf-8')
        if target.exists(): target.rmdir()
        staging.rename(target)
    return {'version':1,'missingSources':missing,'databaseOnly':True}


def restore_backup(archive_path, target_directory, allow_empty=False):
    target = Path(target_directory).resolve()
    if target.exists() and (not allow_empty or not target.is_dir() or any(target.iterdir())):
        raise ValueError('Restore requires a new directory. Existing books are never overwritten.')
    if hasattr(archive_path,'read'):
        archive_path.seek(0); signature=archive_path.read(16); archive_path.seek(0)
    else:
        with Path(archive_path).open('rb') as stream: signature=stream.read(16)
    if signature==b'SQLite format 3\x00':
        content=archive_path.read() if hasattr(archive_path,'read') else Path(archive_path).read_bytes()
        return restore_database(content,target,allow_empty)
    if not signature.startswith(b'PK'):
        raise ValueError('Choose a SQLite export, reusable Excel ledger or profile backup ZIP.')
    with ZipFile(archive_path) as archive:
        if sum(i.file_size for i in archive.infolist()) > 2 * 1024**3:
            raise ValueError('Backup exceeds the 2 GB expanded restore limit.')
        if 'manifest.json' not in archive.namelist() and 'xl/workbook.xml' in archive.namelist():
            if sum(i.file_size for i in archive.infolist())>128*1024**2:
                raise ValueError('The expanded workbook is too large to restore. Use the SQLite export instead.')
            from openpyxl import load_workbook
            from reports import read_profile
            if hasattr(archive_path,'seek'): archive_path.seek(0)
            workbook=load_workbook(archive_path,read_only=True,data_only=False)
            try: content=read_profile(workbook)
            finally: workbook.close()
            return restore_database(content,target,allow_empty)
        if 'manifest.json' not in archive.namelist():
            raise ValueError('This ZIP does not contain a Local Bookkeeper profile backup.')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('version') != 1 or 'bookkeeper.sqlite3' not in manifest.get('files',{}):
            raise ValueError('Unsupported backup manifest.')
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(manifest['files']) | {'manifest.json'}:
            raise ValueError('Backup contains unexpected or duplicate files.')
        # Validate the entire archive before writing anything to the destination.
        for name,digest in manifest['files'].items():
            path = (target/name).resolve()
            if not path.is_relative_to(target) or (name not in {'bookkeeper.sqlite3','bookkeeper.profile.json'} and not path.is_relative_to(target/'documents')):
                raise ValueError('Unsafe path in backup.')
            if name=='bookkeeper.profile.json':
                profile=json.loads(archive.read(name))
                if not isinstance(profile,dict) or profile.get('format')!=workspace_store.PROFILE_FORMAT or profile.get('version')!=1 or profile.get('database')!='bookkeeper.sqlite3':raise ValueError('The backup profile must reference its included SQLite database.')
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError('Backup checksum mismatch.')
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
            staging = Path(temporary)/'restored'; staging.mkdir()
            for name in manifest['files']:
                path = staging/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(archive.read(name))
            with closing(sqlite3.connect(staging/'bookkeeper.sqlite3')) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
                    raise ValueError('Restored database integrity check failed.')
            if target.exists(): target.rmdir()  # Only an empty, explicitly chosen destination can reach this point.
            staging.rename(target)
    return manifest


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] != 'restore':
        raise SystemExit('Usage: python backup.py restore BACKUP.zip NEW_DATA_DIRECTORY')
    try:
        manifest = restore_backup(sys.argv[2],sys.argv[3])
        print('Restored to',Path(sys.argv[3]).resolve())
        if manifest['missingSources']: print('Missing originals:',len(manifest['missingSources']))
    except (ValueError,OSError) as error:
        raise SystemExit(str(error))
