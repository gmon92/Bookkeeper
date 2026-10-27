"""Editable JSON rules round-trip safely and automate future imports."""
import copy
import base64
import io
import json
import unittest

import automation
import categorization
import server
import test_credits


class RuleFileTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr,server,'PROFILE_PATH',server.PROFILE_PATH)
        self.fixture=test_credits.CreditReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.handler=self.fixture.handler
        self.handler.local_request=lambda:True
        self.handler.headers={'X-Bookkeeper-Workspace':server.WORKSPACE_ID}
        self.handler.path='/api/automation/rules-json'

    def expense(self, **changes):
        return {'type':'expense','patterns':['NEW SUPPLIER'],'businessId':self.fixture.business,
            'accountId':'card','category':'Meals','mode':'categorize'}|changes

    def payload(self, *rules):
        return {'format':'local-bookkeeper-rules','version':1,'rules':list(rules)}

    def import_file(self, payload):
        self.handler.read_json=lambda:payload
        return self.handler.post_request()

    def saved(self):
        with server.connect() as db:return automation.all_rules(db)

    def export_file(self):
        status,payload=self.handler.get_request()
        self.assertEqual(status,200)
        return json.loads(json.dumps(payload))

    def test_edit_export_and_add_rule_without_reimport_duplicates(self):
        self.assertEqual(self.import_file(self.payload(self.expense()))[0],200)
        exported=self.export_file()
        self.assertEqual(exported['reference']['businesses'][0]['id'],self.fixture.business)
        self.assertIn('Example card',[r['name'] for r in exported['reference']['accounts']])
        rule_id=exported['rules'][0]['id']
        exported['rules'][0].update(category='Fuel',mode='review',includeInTotals=True)
        exported['rules'].append({'type':'credit','patterns':['NEW BENEFIT'],
            'accountId':None,'treatment':'statement_credit','mode':'review'})
        with server.connect() as db:
            before=[tuple(r) for r in db.execute('SELECT * FROM transactions ORDER BY id')]
        status,result=self.import_file(exported)
        self.assertEqual((status,result['imported'],result['updated']),(200,1,1))
        self.assertIn(rule_id,[r['id'] for r in self.saved()])
        self.assertEqual(len(self.saved()),2)
        self.assertEqual(self.import_file(exported)[1],{'ok':True,'imported':0,'updated':0,'skipped':2})
        with server.connect() as db:
            self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM transactions ORDER BY id')])
        self.fixture.import_csv('card',b'Date,Description,Debit,Credit\n11/01/2026,NEW SUPPLIER,20.00,\n11/02/2026,NEW BENEFIT,,12.00\n')
        with server.connect() as db:
            charge=db.execute("SELECT * FROM transactions WHERE description='NEW SUPPLIER'").fetchone()
            credit=db.execute("SELECT * FROM transactions WHERE description='NEW BENEFIT'").fetchone()
            self.assertEqual((charge['category_name'],charge['status'],charge['include_in_totals']),('Fuel','approved',1))
            self.assertEqual((credit['credit_treatment'],credit['excluded'],credit['include_in_totals']),('statement_credit',1,0))

    def test_exports_include_valid_json_guide_for_every_rule_field(self):
        self.import_file(self.payload(self.expense()))
        exported=self.export_file()
        self.assertEqual(next(iter(exported)),'_comments')
        guide=exported['_comments']
        self.assertTrue(set(exported['rules'][0])<=set(guide['fields']))
        self.assertEqual(set(guide['fields']['mode']),{'suggest','categorize','review'})
        self.assertIn('refunds subtract',guide['fields']['includeInTotals']['true'])
        self.assertIn('mode: "review"',guide['fields']['includeInTotals']['true'])
        self.assertIn('patterns',guide['examples']['merchant_expense'])
        self.assertEqual(json.loads(json.dumps(exported)),exported)

    def test_personal_rules_exclude_imports_and_preserve_reviewed_rows(self):
        for mode in ('review','categorize'):
            with self.subTest(mode=mode):
                merchant='PERSONAL '+mode.upper()
                self.assertEqual(self.import_file(self.payload(self.expense(
                    patterns=[merchant],category='Personal / non-business',mode=mode)))[0],200)
                self.fixture.import_csv('card',('Date,Description,Debit,Credit\n11/03/2026,'+merchant+',45.00,\n').encode())
                with server.connect() as db:
                    row=db.execute('SELECT * FROM transactions WHERE description=?',(merchant,)).fetchone()
                    self.assertEqual((row['classification'],row['business_id'],row['category_id'],row['excluded'],row['include_in_totals']),
                        ('personal',None,None,1,0))
                    self.assertEqual(row['status'],'approved' if mode=='review' else 'suggested')
        before=self.fixture.row('PLUS MEMBERSHIP')
        self.import_file(self.payload(self.expense(patterns=['PLUS MEMBERSHIP'],category='Personal / non-business',mode='review')))
        with server.connect() as db:
            automation.apply(db,self.handler,server.utc_now())
        self.assertEqual(self.fixture.row('PLUS MEMBERSHIP'),before)

    def test_personal_rules_cannot_include_business_expense_totals(self):
        status,result=self.import_file(self.payload(self.expense(
            category='Personal / non-business',mode='review',includeInTotals=True)))
        self.assertEqual(status,400)
        self.assertIn('Personal expense rules must stay excluded',result['error'])
        self.assertEqual(self.saved(),[])

    def test_applying_a_personal_rule_suggestion_uses_personal_classification(self):
        self.import_file(self.payload(self.expense(patterns=['PERSONAL SUPPLIER'],
            category='Personal / non-business',mode='suggest')))
        self.fixture.import_csv('card',b'Date,Description,Debit,Credit\n11/04/2026,PERSONAL SUPPLIER,45.00,\n')
        with server.connect() as db:
            row=db.execute("SELECT * FROM transactions WHERE description='PERSONAL SUPPLIER'").fetchone()
            self.assertEqual(row['status'],'needs_review')
            public,changes,_=categorization.plan(db,{'ids':[row['id']],'mode':'suggestions'},self.handler.validate_transaction)
            self.assertEqual(public['exceptionCount'],0)
            self.assertEqual((changes[0]['new']['classification'],changes[0]['new']['business_id'],
                changes[0]['new']['excluded'],changes[0]['new']['include_in_totals']),('personal',None,1,0))

    def test_comments_and_examples_are_ignored_when_importing_rules(self):
        self.import_file(self.payload(self.expense()))
        before=self.saved()
        exported=self.export_file()
        exported['_comments']={'rules':[self.expense(patterns=['DO NOT IMPORT'])],
            'examples':{'brokenExample':{'businessId':'not-a-business','category':'not-a-category'}}}
        status,result=self.import_file(exported)
        self.assertEqual((status,result['imported'],result['updated'],result['skipped']),(200,0,0,1))
        self.assertEqual(self.saved(),before)
        del exported['_comments']
        self.assertEqual(self.import_file(exported)[0],200)

    def test_unedited_legacy_export_receives_default_comments(self):
        from pathlib import Path
        self.import_file(self.payload(self.expense()))
        legacy=self.export_file(); legacy.pop('_comments')
        path=Path(server.active_profile()['rulesFile'])
        path.write_text(json.dumps(legacy,indent=2),encoding='utf-8')
        self.handler.path='/api/automation/rules-json/file'; self.handler.read_json=lambda:{}
        status,result=self.handler.post_request()
        self.assertEqual(status,200)
        self.assertTrue(result['exported'])
        self.assertFalse(result['externalEdits'])
        upgraded=json.loads(path.read_text(encoding='utf-8'))
        self.assertIn('_comments',upgraded)
        self.assertEqual(upgraded['rules'],legacy['rules'])

    def test_legacy_exports_with_pending_rule_edits_are_preserved(self):
        from pathlib import Path
        self.import_file(self.payload(self.expense()))
        legacy=self.export_file(); legacy.pop('_comments')
        legacy['rules'][0]['patterns'].append('UNIMPORTED PHRASE')
        path=Path(server.active_profile()['rulesFile'])
        content=json.dumps(legacy,indent=2)
        path.write_text(content,encoding='utf-8')
        self.handler.path='/api/automation/rules-json/file'; self.handler.read_json=lambda:{}
        status,result=self.handler.post_request()
        self.assertEqual(status,200)
        self.assertTrue(result['externalEdits'])
        self.assertEqual(path.read_text(encoding='utf-8'),content)

    def test_external_notes_in_comment_section_are_preserved(self):
        from pathlib import Path
        self.import_file(self.payload(self.expense()))
        self.handler.path='/api/automation/rules-json/file'; self.handler.read_json=lambda:{}
        _,result=self.handler.post_request()
        path=Path(result['path'])
        edited=json.loads(path.read_text(encoding='utf-8'))
        edited['_comments']['my_notes']='I am still editing these rules.'
        path.write_text(json.dumps(edited),encoding='utf-8')
        status,result=self.handler.post_request()
        self.assertEqual(status,200)
        self.assertTrue(result['externalEdits'])
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')),edited)

    def test_round_trip_preserves_conditions_scopes_paused_and_credit_rules(self):
        rules=[self.expense(patterns=[],sourceCategories=['Travel','Transport'],minAmount='10.01',maxAmount='30.11',active=False),
            {'type':'credit','patterns':['NEW REFUND'],'accountId':None,'treatment':'refund',
                'businessId':self.fixture.business,'category':'Meals','mode':'review','includeInTotals':True},
            {'type':'credit','sourceCategories':['Benefits'],'treatment':'excluded_credit','mode':'suggest'}]
        status,result=self.import_file(self.payload(*rules))
        self.assertEqual((status,result['imported']),(200,3))
        exported=self.export_file()
        with server.connect() as db:
            db.execute('DELETE FROM merchant_rules'); db.execute('DELETE FROM credit_rules')
        for rule in exported['rules']:rule.pop('id')
        self.assertEqual(self.import_file(exported)[1]['imported'],3)
        actual=self.export_file()
        for rule in actual['rules']:rule.pop('id')
        self.assertEqual(sorted(actual['rules'],key=lambda r:r['category']+r['type']+r['treatment']),
            sorted(exported['rules'],key=lambda r:r['category']+r['type']+r['treatment']))

    def test_later_invalid_rule_leaves_all_existing_rules_unchanged(self):
        self.import_file(self.payload(self.expense()))
        before=self.saved()
        exported=self.export_file()
        exported['rules'][0]['category']='Fuel'
        exported['rules'].append(self.expense(category='No such category'))
        status,result=self.import_file(exported)
        self.assertEqual(status,400)
        self.assertIn('Rule 2:',result['error'])
        self.assertEqual(self.saved(),before)

    def test_bad_types_unknown_ids_and_duplicate_ids_are_readable_errors(self):
        self.import_file(self.payload(self.expense()))
        saved=self.export_file()['rules'][0]
        invalid=[self.payload(self.expense(category=[])),self.payload(self.expense(accountId={})),
            self.payload(self.expense(active='true')),self.payload(self.expense(patterns='SUPPLIER')),
            self.payload(self.expense(id='not-in-this-profile')),self.payload(self.expense(categroy='Meals')),
            self.payload(saved,copy.deepcopy(saved)),self.payload(self.expense())|{'version':True}]
        before=self.saved()
        for payload in invalid:
            with self.subTest(payload=payload):
                status,result=self.import_file(payload)
                self.assertEqual(status,400)
                self.assertTrue(result['error'])
                self.assertEqual(self.saved(),before)

    def test_legacy_rules_export_and_deduplicate_by_meaning(self):
        with server.connect() as db:
            db.execute('INSERT INTO merchant_rules(id,pattern,account_id,business_id,category_name,created_at) VALUES(?,?,?,?,?,?)',
                ('legacy','NEW SUPPLIER','card',self.fixture.business,'Meals',server.utc_now()))
        exported=self.export_file()
        self.assertEqual(exported['rules'][0]['patterns'],['NEW SUPPLIER'])
        exported['rules'][0].pop('id')
        exported['rules'][0]['patterns']=['new-supplier']
        self.assertEqual(self.import_file(exported)[1]['skipped'],1)
        self.assertEqual(len(self.saved()),1)

    def test_statement_imports_apply_saved_rules_without_changing_definitions(self):
        from openpyxl import Workbook
        self.import_file(self.payload(self.expense()))
        before=self.saved()
        workbook=Workbook()
        sheet=workbook.active
        sheet.append(['Date','Description','Debit','Credit','RulePattern','RuleCategory'])
        sheet.append(['11/10/2026','NEW SUPPLIER',25,None,'OVERWRITE ME','Fuel'])
        rules=workbook.create_sheet('Rules')
        rules.append(['pattern','category','mode']); rules.append(['ANYTHING','Fuel','review'])
        output=io.BytesIO(); workbook.save(output); workbook.close()
        csv=b'Date,Description,Debit,Credit,RulePattern,RuleCategory\n11/11/2026,NEW SUPPLIER,26,,OVERWRITE ME,Fuel\n'
        for filename,content in [('statement.xlsx',output.getvalue()),('statement.csv',csv)]:
            with self.subTest(filename=filename):
                self.handler.path='/api/imports/preview'
                self.handler.read_json=lambda:{'filename':filename,'contentBase64':base64.b64encode(content).decode()}
                status,preview=self.handler.post_request()
                self.assertEqual(status,200)
                self.handler.path='/api/imports/commit'
                self.handler.read_json=lambda:{'token':preview['token'],'accountId':'card','confirmExtraction':True,'confirmMapping':True}
                status,_=self.handler.post_request()
                self.assertEqual(status,201)
                self.assertEqual(self.saved(),before)
        with server.connect() as db:
            rows=db.execute("SELECT category_name,status FROM transactions WHERE description='NEW SUPPLIER'").fetchall()
            self.assertEqual([tuple(r) for r in rows],[('Meals','suggested'),('Meals','suggested')])

    def test_report_rules_file_preserves_external_edits_until_explicit_import(self):
        from pathlib import Path
        self.import_file(self.payload(self.expense()))
        profile=server.active_profile()
        self.assertFalse(profile['rulesFileExists'])
        self.handler.path='/api/automation/rules-json/file'
        status,result=self.handler.post_request()
        self.assertEqual((status,result['created']),(200,True))
        path=Path(result['path'])
        self.assertEqual(path,self.fixture.root/'bookkeeper.rules.json')
        exported=json.loads(path.read_text(encoding='utf-8'))
        exported['rules'].append(self.expense(patterns=['ANOTHER SUPPLIER'],category='Fuel'))
        changed=json.dumps(exported,indent=2)+'\n'
        path.write_text(changed,encoding='utf-8')
        self.assertTrue(server.active_profile()['rulesFileExists'])
        status,result=self.handler.post_request()
        self.assertEqual(status,200)
        self.assertEqual(result['path'],str(path))
        self.assertFalse(result['created'])
        self.assertTrue(result['externalEdits'])
        self.assertEqual(path.read_text(encoding='utf-8'),changed)
        self.assertEqual(len(self.saved()),1)
        self.handler.path='/api/automation/rules-json'
        self.assertEqual(self.import_file(exported)[1]['imported'],1)
        self.assertEqual(len(self.saved()),2)
        self.handler.path='/api/automation/rules-json/file'
        self.handler.read_json=lambda:{}
        status,result=self.handler.post_request()
        self.assertEqual((status,result['ruleCount']),(200,2))
        self.assertFalse(result['externalEdits'])
        self.assertTrue(all(r.get('id') for r in json.loads(path.read_text(encoding='utf-8'))['rules']))

    def test_report_rules_file_refreshes_unedited_export_after_rules_change(self):
        from pathlib import Path
        self.import_file(self.payload(self.expense()))
        self.handler.path='/api/automation/rules-json/file'
        self.handler.read_json=lambda:{}
        status,result=self.handler.post_request()
        self.assertEqual((status,result['ruleCount']),(200,1))
        path=Path(result['path'])
        status,unchanged=self.handler.post_request()
        self.assertEqual(status,200)
        self.assertFalse(unchanged['exported'])
        self.assertFalse(unchanged['externalEdits'])
        with server.connect() as db:
            automation.save(db,{'type':'credit','patterns':['ANOTHER BENEFIT'],
                'treatment':'statement_credit','mode':'suggest'},server.utc_now())
        status,result=self.handler.post_request()
        self.assertEqual((status,result['ruleCount']),(200,2))
        self.assertTrue(result['exported'])
        self.assertFalse(result['externalEdits'])
        self.assertIsNone(result['backup'])
        exported=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual({r['type'] for r in exported['rules']},{'expense','credit'})
        self.assertEqual(len(exported['rules']),len(self.saved()))

    def test_explicit_rules_refresh_backs_up_external_edits(self):
        from pathlib import Path
        self.import_file(self.payload(self.expense()))
        self.handler.path='/api/automation/rules-json/file'
        self.handler.read_json=lambda:{}
        _,result=self.handler.post_request()
        path=Path(result['path'])
        external='{"unimportedEdits":true}'
        path.write_text(external,encoding='utf-8')
        self.handler.read_json=lambda:{'refresh':True}
        status,result=self.handler.post_request()
        self.assertEqual(status,200)
        self.assertEqual(Path(result['backup']).read_text(encoding='utf-8'),external)
        self.assertEqual(len(json.loads(path.read_text(encoding='utf-8'))['rules']),1)
        self.assertFalse(result['externalEdits'])

    def test_open_rules_in_container_returns_saved_json_view(self):
        from unittest.mock import patch
        self.import_file(self.payload(self.expense()))
        self.handler.path='/api/automation/rules-json/file'
        self.handler.read_json=lambda:{'open':True}
        with patch.dict(server.os.environ,{'LOCAL_BOOKKEEPER_STORAGE_ROOT':str(self.fixture.root)}):
            status,result=self.handler.post_request()
        self.assertEqual(status,200)
        self.assertFalse(result['opened'])
        self.assertEqual(result['url'],'/api/automation/rules-json/file')
        status,document=self.handler.get_request()
        self.assertEqual(status,200)
        self.assertEqual(len(document['rules']),1)

    @unittest.skipUnless(hasattr(server.os,'startfile'),'Windows desktop opener')
    def test_open_rules_uses_default_desktop_editor(self):
        from unittest.mock import patch
        self.handler.path='/api/automation/rules-json/file'
        self.handler.read_json=lambda:{'open':True}
        with patch.dict(server.os.environ,{'LOCAL_BOOKKEEPER_STORAGE_ROOT':''}), patch.object(server.os,'startfile') as opener:
            status,result=self.handler.post_request()
        self.assertEqual(status,200)
        self.assertTrue(result['opened'])
        opener.assert_called_once_with(result['path'])

    def test_report_rules_location_follows_active_profile(self):
        from pathlib import Path
        first=server.active_profile()['rulesFile']
        server.activate_workspace(self.fixture.root/'other-profile','Another business')
        profile=server.active_profile()
        self.assertNotEqual(profile['rulesFile'],first)
        self.assertFalse(profile['rulesFileExists'])
        self.handler.headers={'X-Bookkeeper-Workspace':server.WORKSPACE_ID}
        self.handler.path='/api/automation/rules-json/file'
        status,result=self.handler.post_request()
        self.assertEqual(status,200)
        self.assertEqual(Path(result['path']).parent,self.fixture.root/'other-profile')
        self.assertTrue(server.active_profile()['rulesFileExists'])


if __name__=='__main__':unittest.main()
