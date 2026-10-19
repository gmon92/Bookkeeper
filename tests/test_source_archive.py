"""Source retention is independent of edits, files, and category decisions."""
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
import zipfile
from contextlib import closing

import server
import source_archive


class SourceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='bookkeeper-source-tests-')
        self.root = Path(self.directory.name)
        self.previous = server.DATA_DIR, server.DOCS_DIR, server.DB_PATH, server.WORKSPACE_READY, server.WORKSPACE_ID
        server.activate_workspace(self.root, 'Example Business')
        self.handler = server.Handler.__new__(server.Handler)
        self.handler.send_json = lambda status, body: (status, body)
        with server.connect() as db:
            db.execute("INSERT INTO accounts(id,nickname) VALUES('account','Example card')")

    def tearDown(self):
        server.DATA_DIR, server.DOCS_DIR, server.DB_PATH, server.WORKSPACE_READY, server.WORKSPACE_ID = self.previous
        self.directory.cleanup()

    def import_statement(self, content=None, filename='example.csv'):
        content = content or b'Export for Example\nDate,Description,Debit,Credit,Category Description\n10/01/2026,CAFE A,12.00,,Dining\n10/02/2026,CAFE B,18.00,,Dining\n10/03/2026,OTHER SHOP,5.00,,\n'
        parsed = server.parse_statement(content, filename, server.parse_csv)
        with server.connect() as db:
            db.execute('INSERT INTO staged_imports VALUES(?,?,?,?,?)', ('token', content, json.dumps(parsed), hashlib.sha256(content).hexdigest(), time.time()))
        self.handler.read_json = lambda: {'token':'token','accountId':'account','confirmExtraction':True,'confirmMapping':True}
        status, result = self.handler.commit_import()
        self.assertEqual(status, 201)
        return result, parsed

    def test_originals_survive_edits_missing_file_and_database_backup(self):
        imported, parsed = self.import_statement()
        self.assertEqual(source_archive.category_groups(parsed), [
            {'category':'Dining','count':2,'amountCents':3000}, {'category':'','count':1,'amountCents':500}])
        tx_id = imported['inserted'][0]['id']
        with server.connect() as db:
            before = source_archive.original(db, tx_id)
            path = self.root / db.execute('SELECT stored_path FROM documents').fetchone()[0]
            db.execute("UPDATE transactions SET description='Corrected merchant',date='2026-10-05',amount_cents=999 WHERE id=?", (tx_id,))
        path.unlink()  # Disposable fixture: the database must be sufficient.
        with server.connect() as db:
            self.assertEqual(source_archive.original(db, tx_id), before)
            self.assertEqual(before['normalized']['description'], 'CAFE A')
            self.assertEqual(before['normalized']['amountCents'], 1200)
            archived = source_archive.document_rows(db, imported['documentId'], None, 0)
            self.assertEqual(archived['coverage'], 'all_cells')
            self.assertEqual(archived['rows'][0]['cells'][0]['value'], 'Export for Example')
            self.assertEqual(archived['rows'][2]['cells'][4]['value'], 'Dining')
        status, explanation = self.handler.explain_transaction(tx_id)
        self.assertEqual(status, 200)
        self.assertEqual(explanation['current']['amountCents'], 999)
        self.assertEqual(explanation['original']['normalized']['amountCents'], 1200)
        from backup import create_backup
        with zipfile.ZipFile(io.BytesIO(create_backup(server.DB_PATH, self.root))) as archive:
            db_name = next(n for n in archive.namelist() if n.endswith('.sqlite3'))
            restored = self.root / 'snapshot.sqlite3'
            restored.write_bytes(archive.read(db_name))
        with closing(sqlite3.connect(restored)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM source_rows').fetchone()[0], 5)
            self.assertEqual(db.execute('SELECT source_category FROM original_transactions WHERE transaction_id=?', (tx_id,)).fetchone()[0], 'Dining')

    def test_original_tables_reject_update_delete_and_replace(self):
        self.import_statement()
        for table in ('source_archives', 'source_rows', 'original_transactions'):
            for sql in (f'DELETE FROM {table}', f'INSERT OR REPLACE INTO {table} SELECT * FROM {table}'):
                with self.subTest(sql=sql), server.connect() as db:
                    with self.assertRaises(sqlite3.IntegrityError):
                        db.execute(sql)
        with server.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE original_transactions SET source_category='Altered'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE transactions SET source_raw_json='{}'")

    def test_xlsx_archives_other_sheets_typed_dates_and_formulas(self):
        from openpyxl import Workbook
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Transactions'
        sheet.append(['Date','Description','Debit','Credit','Merchant Category'])
        sheet.append([dt.datetime(2026,10,1),'EXAMPLE SHOP',12,None,'Supplies'])
        summary = workbook.create_sheet('Summary')
        summary.append(['Total','=12+0'])
        output = io.BytesIO()
        workbook.save(output)
        imported, parsed = self.import_statement(output.getvalue(), 'example.xlsx')
        self.assertEqual(source_archive.category_groups(parsed)[0]['category'], 'Supplies')
        with server.connect() as db:
            archive = source_archive.document_rows(db, imported['documentId'], 'Summary', 0)
            self.assertEqual(archive['rows'][0]['cells'][1], {'type':'f','value':'=12+0'})
            transaction_sheet = source_archive.document_rows(db, imported['documentId'], 'Transactions', 0)
            self.assertEqual(transaction_sheet['rows'][1]['cells'][0], {'type':'datetime','value':'2026-10-01T00:00:00'})

    def test_legacy_migration_uses_source_evidence_and_is_repeatable(self):
        imported, _ = self.import_statement()
        with server.connect() as db:
            db.execute("UPDATE transactions SET description='Edited after import',amount_cents=999")
            for table in ('original_transactions','source_rows','source_archives'):
                db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=5')
        server.initialize()
        server.initialize()
        with server.connect() as db:
            original = source_archive.original(db, imported['inserted'][0]['id'])
            self.assertIsNone(original['normalized'])
            self.assertEqual(original['raw']['values'][1], 'CAFE A')
            self.assertEqual(original['sourceCategory'], 'Dining')
            self.assertEqual(db.execute('SELECT count(*) FROM original_transactions').fetchone()[0], 3)
            self.assertEqual(source_archive.document_rows(db, imported['documentId'], None, 0)['coverage'], 'all_cells')

    def test_legacy_missing_file_keeps_retained_rows_with_explicit_coverage(self):
        imported, _ = self.import_statement()
        with server.connect() as db:
            (self.root / db.execute('SELECT stored_path FROM documents').fetchone()[0]).unlink()
            for table in ('original_transactions','source_rows','source_archives'):
                db.execute('DROP TABLE '+table)
        server.initialize()
        with server.connect() as db:
            archive = source_archive.document_rows(db, imported['documentId'], None, 0)
            self.assertEqual(archive['coverage'], 'imported_rows')
            self.assertEqual(archive['rows'][0]['number'], 3)
            self.assertEqual(archive['rows'][0]['cells'][1]['value'], 'CAFE A')


if __name__ == '__main__':
    unittest.main()
