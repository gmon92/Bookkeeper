"""Batch imports retain per-file decisions, originals, and safe retry behavior."""
import base64
import json
import unittest

import automation
import server
import test_credits


class MultiStatementImportTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr,server,'PROFILE_PATH',server.PROFILE_PATH)
        self.fixture=test_credits.CreditReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.handler=self.fixture.handler
        self.handler.local_request=lambda:True
        self.handler.headers={'X-Bookkeeper-Workspace':server.WORKSPACE_ID}

    def request(self,path,body):
        self.handler.path=path;self.handler.read_json=lambda:body
        return self.handler.post_request()

    def stage(self,name='monthly.csv',content=None):
        content=content or b'Date,Description,Debit,Credit\n10/21/2026,BATCH MERCHANT,15.25,\n'
        status,preview=self.request('/api/imports/preview',{'filename':name,'contentBase64':base64.b64encode(content).decode()})
        self.assertEqual(status,200,preview)
        return preview

    def body(self,preview,**changes):
        return {'token':preview['token'],'accountId':'card','confirmExtraction':True,
            'confirmMapping':True,'allowDuplicate':False,'rememberLayout':False}|changes

    def test_batch_uses_one_account_and_keeps_originals_separate(self):
        with server.connect() as db:
            automation.save(db,{'type':'expense','patterns':['BATCH MERCHANT'],'accountId':'card',
                'businessId':self.fixture.business,'category':'Meals','mode':'categorize'},server.utc_now())
        first=self.stage('card.csv')
        second=self.stage('bank.csv',b'Date,Description,Debit,Credit\n10/22/2026,BATCH MERCHANT,18.25,\n')
        status,result=self.request('/api/imports/commit-batch',{'items':[self.body(first),self.body(second)]})
        self.assertEqual(status,201,result)
        self.assertEqual(len(result['imported']),2)
        self.assertIsNone(result['failedIndex'])
        with server.connect() as db:
            rows=db.execute("SELECT t.*,d.filename,d.stored_path FROM transactions t JOIN documents d ON t.document_id=d.id WHERE description='BATCH MERCHANT' ORDER BY date").fetchall()
            self.assertEqual([(r['account_id'],r['category_name'],r['status']) for r in rows],
                [('card','Meals','suggested'),('card','Meals','suggested')])
            self.assertEqual([r['filename'] for r in rows],['card.csv','bank.csv'])
            self.assertTrue(all((server.DATA_DIR/r['stored_path']).is_file() for r in rows))
            self.assertTrue(all(db.execute('SELECT 1 FROM original_transactions WHERE transaction_id=?',(r['id'],)).fetchone() for r in rows))

    def test_lost_response_retry_does_not_duplicate_saved_statements(self):
        previews=[self.stage('first.csv'),self.stage('second.csv',b'Date,Description,Debit,Credit\n10/22/2026,OTHER MERCHANT,18.25,\n')]
        body={'items':[self.body(p) for p in previews]}
        status,first=self.request('/api/imports/commit-batch',body)
        self.assertEqual(status,201)
        with server.connect() as db:before=db.execute('SELECT count(*) FROM transactions').fetchone()[0]
        status,retry=self.request('/api/imports/commit-batch',body)
        self.assertEqual(status,201)
        self.assertEqual(retry,first)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM transactions').fetchone()[0],before)
        status,changed=self.request('/api/imports/commit-batch',{'items':[body['items'][0]|{'accountId':'bank'}]})
        self.assertEqual(status,200)
        self.assertIn('different settings',changed['error'])
        self.assertEqual(changed['imported'],[])

    def test_failure_retains_completed_files_and_retry_imports_only_remaining(self):
        first=self.stage('first.csv');second=self.stage('same-copy.csv')
        body={'items':[self.body(first),self.body(second)]}
        status,partial=self.request('/api/imports/commit-batch',body)
        self.assertEqual((status,len(partial['imported']),partial['failedIndex']),(200,1,1))
        self.assertIn('already imported',partial['error'])
        with server.connect() as db:
            before=db.execute('SELECT count(*) FROM documents').fetchone()[0]
            self.assertIsNotNone(db.execute('SELECT 1 FROM staged_imports WHERE token=?',(second['token'],)).fetchone())
        status,retry=self.request('/api/imports/commit-batch',{'items':[body['items'][1]|{'allowDuplicate':True}]})
        self.assertEqual(status,201,retry)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM documents').fetchone()[0],before+1)
            self.assertIsNotNone(db.execute('SELECT 1 FROM documents WHERE id=?',(partial['imported'][0]['documentId'],)).fetchone())

    def test_mixed_accounts_or_settings_cannot_save_any_statement(self):
        first=self.stage('first.csv');second=self.stage('second.csv')
        for changes in ({'accountId':'bank'},{'rememberLayout':True},{'allowDuplicate':True},
                {'confirmMapping':False},{'confirmExtraction':False}):
            with self.subTest(changes=changes):
                status,result=self.request('/api/imports/commit-batch',{'items':[self.body(first),self.body(second,**changes)]})
                self.assertEqual(status,400)
                self.assertIn('same source account and import settings',result['error'])
        with server.connect() as db:self.assertFalse(db.execute("SELECT 1 FROM documents WHERE filename='first.csv'").fetchone())

    def test_later_pdf_account_mismatch_stops_batch_before_first_file_saves(self):
        first=self.stage('first.csv');second=self.stage('second.csv')
        with server.connect() as db:
            db.execute("UPDATE accounts SET last_four='4115',account_type='checking' WHERE id='card'")
            parsed=json.loads(db.execute('SELECT parsed_json FROM staged_imports WHERE token=?',(second['token'],)).fetchone()[0])
            parsed['format']='pdf';parsed['extraction']['accountLastFour']='9999'
            db.execute('UPDATE staged_imports SET parsed_json=? WHERE token=?',(json.dumps(parsed),second['token']))
        status,result=self.request('/api/imports/commit-batch',{'items':[self.body(first),self.body(second)]})
        self.assertEqual(status,400)
        self.assertIn('9999',result['error'])
        with server.connect() as db:self.assertFalse(db.execute("SELECT 1 FROM documents WHERE filename='first.csv'").fetchone())

    def test_different_pdf_accounts_cannot_share_an_account_without_last_four(self):
        previews=[self.stage('first.csv'),self.stage('second.csv')]
        with server.connect() as db:
            for preview,last_four in zip(previews,('4115','9999')):
                parsed=json.loads(db.execute('SELECT parsed_json FROM staged_imports WHERE token=?',(preview['token'],)).fetchone()[0])
                parsed['format']='pdf';parsed['extraction']['accountLastFour']=last_four
                db.execute('UPDATE staged_imports SET parsed_json=? WHERE token=?',(json.dumps(parsed),preview['token']))
        status,result=self.request('/api/imports/commit-batch',{'items':[self.body(preview) for preview in previews]})
        self.assertEqual(status,400)
        self.assertIn('different source accounts',result['error'])
        with server.connect() as db:self.assertFalse(db.execute("SELECT 1 FROM documents WHERE filename='first.csv'").fetchone())

    def test_missing_confirmation_and_expired_preview_cannot_save_that_file(self):
        preview=self.stage()
        status,result=self.request('/api/imports/commit-batch',{'items':[self.body(preview,confirmExtraction=False)]})
        self.assertEqual((status,result['imported']),(200,[]))
        self.assertIn('Confirm',result['error'])
        with server.connect() as db:db.execute('UPDATE staged_imports SET created_at=0 WHERE token=?',(preview['token'],))
        status,result=self.request('/api/imports/commit-batch',{'items':[self.body(preview)]})
        self.assertEqual(result['imported'],[])
        self.assertIn('expired',result['error'])
        with server.connect() as db:self.assertFalse(db.execute("SELECT 1 FROM documents WHERE filename='monthly.csv'").fetchone())

    def test_discard_removes_only_selected_previews_and_never_originals(self):
        first=self.stage('first.csv');second=self.stage('second.csv')
        with server.connect() as db:before=db.execute('SELECT count(*) FROM documents').fetchone()[0]
        status,_=self.request('/api/imports/discard',{'tokens':[first['token']]})
        self.assertEqual(status,200)
        with server.connect() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM staged_imports WHERE token=?',(first['token'],)).fetchone())
            self.assertIsNotNone(db.execute('SELECT 1 FROM staged_imports WHERE token=?',(second['token'],)).fetchone())
            self.assertEqual(db.execute('SELECT count(*) FROM documents').fetchone()[0],before)

    def test_batch_size_and_repeated_tokens_are_rejected_before_saving(self):
        preview=self.stage();item=self.body(preview)
        for items in ([],[item]*26,[item,item],['invalid']):
            with self.subTest(items=len(items)):
                status,_=self.request('/api/imports/commit-batch',{'items':items})
                self.assertEqual(status,400)
        with server.connect() as db:self.assertFalse(db.execute("SELECT 1 FROM documents WHERE filename='monthly.csv'").fetchone())

