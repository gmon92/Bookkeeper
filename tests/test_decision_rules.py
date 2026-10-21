"""Decisions persist as scoped rules and apply to genuinely new imports."""
import sqlite3
import unittest
from contextlib import closing

import automation
import categorization
import credits
import server
import test_credits


class DecisionRuleTests(unittest.TestCase):
    def setUp(self):
        self.previous_profile = server.PROFILE_PATH
        self.addCleanup(setattr,server,'PROFILE_PATH',self.previous_profile)
        self.fixture = test_credits.CreditReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.handler = self.fixture.handler
        self.business = self.fixture.business

    def categorize(self, **options):
        body = {'ids':[self.fixture.ids['PLUS MEMBERSHIP']], 'businessId':self.business,
            'category':'Meals', 'markReviewed':True, 'includeInTotals':True, 'rememberRule':True,
            'rulePattern':'PLUS MEMBERSHIP', 'ruleAccountId':'card', 'ruleMode':'review'} | options
        with server.connect() as db:
            preview = categorization.plan(db,body,self.handler.validate_transaction)[0]
            result = categorization.commit(db,body|{'revision':preview['revision']},self.handler,server.utc_now())
        return result

    def import_row(self, account, description, direction='debit', amount='15.25'):
        debit,credit = (amount,'') if direction=='debit' else ('',amount)
        self.fixture.import_csv(account,('Date,Description,Debit,Credit\n10/21/2026,'+description+','+debit+','+credit+'\n').encode())
        with server.connect() as db:
            return dict(db.execute('SELECT * FROM transactions WHERE account_id=? AND date=? AND description=? AND direction=?',
                (account,'2026-10-21',description,direction)).fetchone())

    def test_account_scoped_expense_rule_does_not_reach_another_account(self):
        self.categorize()
        own = self.import_row('card','PLUS MEMBERSHIP')
        other = self.import_row('bank','PLUS MEMBERSHIP',amount='16.25')
        unrelated = self.import_row('card','ANOTHER MERCHANT',amount='18.15')
        self.assertEqual((own['category_name'],own['status'],own['include_in_totals']),('Meals','approved',1))
        self.assertEqual(other['status'],'needs_review')
        self.assertEqual(unrelated['status'],'needs_review')

    def test_global_rule_covers_future_accounts_and_retains_unreviewed_choice(self):
        self.categorize(ruleAccountId=None,ruleAllAccounts=True,ruleMode='categorize',markReviewed=False,includeInTotals=False)
        with server.connect() as db:
            db.execute("INSERT INTO accounts(id,nickname) VALUES('new-card','A later account')")
        row = self.import_row('new-card','PLUS MEMBERSHIP')
        self.assertEqual((row['category_name'],row['status'],row['include_in_totals']),('Meals','suggested',0))

    def test_suggestion_choice_keeps_future_matches_undecided(self):
        self.categorize(ruleMode='suggest')
        row = self.import_row('card','PLUS MEMBERSHIP')
        self.assertEqual((row['status'],row['include_in_totals']),('needs_review',0))
        with server.connect() as db:
            self.assertEqual(categorization.suggestions(db)[row['id']]['category'],'Meals')

    def test_multiple_merchant_groups_save_as_one_rule_and_match_independently(self):
        result = self.categorize(ids=[self.fixture.ids['PLUS MEMBERSHIP'],self.fixture.ids['SUPPLIER PURCHASE']],
            rulePatterns=['PLUS MEMBERSHIP','SUPPLIER PURCHASE'])
        with server.connect() as db:
            saved = next(r for r in automation.all_rules(db) if r['id']==result['ruleId'])
            self.assertEqual(automation.conditions(saved)['patterns'],['PLUS MEMBERSHIP','SUPPLIER PURCHASE'])
            self.assertEqual(db.execute('SELECT count(*) FROM merchant_rules WHERE active=1').fetchone()[0],1)
        for description in ('PLUS MEMBERSHIP','SUPPLIER PURCHASE'):
            row = self.import_row('card',description)
            self.assertEqual((row['category_name'],row['status']),('Meals','approved'))
        other = self.import_row('card','ANOTHER MERCHANT',amount='19.50')
        self.assertEqual(other['status'],'needs_review')

    def test_multiple_credit_groups_can_share_one_global_decision_rule(self):
        self.fixture.apply({'ids':[self.fixture.ids['Platinum Walmart+ Credit'],self.fixture.ids['SUPPLIER REFUND']],
            'treatment':'excluded_credit','rememberRule':True,'rulePatterns':['Walmart','SUPPLIER REFUND'],
            'ruleAllAccounts':True,'ruleMode':'review'})
        for account,description in (('card','Platinum Walmart+ Credit'),('bank','SUPPLIER REFUND')):
            row = self.import_row(account,description,'credit')
            self.assertEqual((row['credit_treatment'],row['excluded'],row['include_in_totals']),('excluded_credit',1,0))
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM credit_rules WHERE active=1').fetchone()[0],1)

    def test_add_selected_groups_to_an_existing_rule_preserves_old_phrases(self):
        with server.connect() as db:
            original = {'type':'expense','patterns':['PLUS MEMBERSHIP'],'accountId':'card',
                'businessId':self.business,'category':'Meals','mode':'categorize'}
            saved = automation.save(db,original,server.utc_now())
            combined = original|{'id':saved['id'],'patterns':['PLUS MEMBERSHIP','SUPPLIER PURCHASE'],
                'selectedIds':[self.fixture.ids['SUPPLIER PURCHASE']]}
            preview = automation.rule_preview(db,combined)
            self.assertEqual(preview['matched'],2)
            automation.save(db,combined,server.utc_now())
            self.assertEqual(db.execute('SELECT count(*) FROM merchant_rules').fetchone()[0],1)
        for description in ('PLUS MEMBERSHIP','SUPPLIER PURCHASE'):
            self.assertEqual(self.import_row('card',description)['category_name'],'Meals')

    def test_existing_rule_scope_cannot_silently_leave_out_selected_groups(self):
        with server.connect() as db:
            body = {'type':'expense','patterns':['PLUS MEMBERSHIP'],'accountId':'card',
                'businessId':self.business,'category':'Meals','mode':'categorize'}
            saved = automation.save(db,body,server.utc_now())
            invalid = body|{'id':saved['id'],'patterns':['PLUS MEMBERSHIP','CARD WITHDRAWAL'],
                'selectedIds':[self.fixture.ids['CARD WITHDRAWAL']]}
            with self.assertRaisesRegex(ValueError,'selected groups'):
                automation.rule_preview(db,invalid)
            with self.assertRaisesRegex(ValueError,'selected groups'):
                automation.save(db,invalid,server.utc_now())
            current = db.execute('SELECT pattern FROM merchant_rules WHERE id=?',(saved['id'],)).fetchone()[0]
            self.assertEqual(current,'PLUS MEMBERSHIP')
            # Explicitly broadening scope includes the chosen second account.
            automation.rule_preview(db,invalid|{'accountId':None})

    def test_new_category_rule_preview_and_commit_are_consistent(self):
        self.categorize(category='Membership costs',createCategory=True)
        row = self.import_row('card','PLUS MEMBERSHIP')
        self.assertEqual((row['category_name'],row['status']),('Membership costs','approved'))

    def test_repeated_decision_replaces_same_scope_without_conflict(self):
        first = self.categorize()
        second = self.categorize(category='Office supplies',includeInTotals=False)
        self.assertNotEqual(first['ruleId'],second['ruleId'])
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT active FROM merchant_rules WHERE id=?',(first['ruleId'],)).fetchone()[0],0)
        row = self.import_row('card','PLUS MEMBERSHIP')
        self.assertEqual((row['category_name'],row['status'],row['include_in_totals']),('Office supplies','approved',0))

    def test_credit_rule_scope_precedence_and_original_charge_are_preserved(self):
        charge = self.fixture.row('PLUS MEMBERSHIP')
        body = {'ids':[self.fixture.ids['Platinum Walmart+ Credit']], 'treatment':'statement_credit',
            'rememberRule':True,'rulePattern':'Walmart','ruleAllAccounts':True,'ruleMode':'review'}
        self.fixture.apply(body)
        self.fixture.apply(body|{'treatment':'excluded_credit','ruleAccountId':'card','ruleAllAccounts':False})
        own = self.import_row('card','Platinum Walmart+ Credit','credit')
        other = self.import_row('bank','Platinum Walmart+ Credit','credit',amount='16.25')
        debit = self.import_row('bank','Platinum Walmart+ Credit','debit',amount='32.50')
        self.assertEqual((own['credit_treatment'],own['status'],own['include_in_totals']),('excluded_credit','approved',0))
        self.assertEqual((other['credit_treatment'],other['excluded']),('statement_credit',1))
        self.assertEqual(debit['status'],'needs_review')
        self.assertEqual(self.fixture.row('PLUS MEMBERSHIP'),charge)

    def test_automatic_card_payment_does_not_reuse_a_transaction_link(self):
        with server.connect() as db:
            payment = db.execute("SELECT id FROM transactions WHERE account_id='card' AND amount_cents=10000 AND direction='credit'").fetchone()[0]
        self.fixture.apply({'ids':[payment],'treatment':'payment','relatedId':self.fixture.ids['CARD WITHDRAWAL'],
            'rememberRule':True,'rulePattern':'MOBILE PAYMENT','ruleAccountId':'card','ruleMode':'review'})
        row = self.import_row('card','MOBILE PAYMENT - THANK YOU','credit',amount='225.50')
        self.assertEqual((row['credit_treatment'],row['status'],row['include_in_totals']),('payment','approved',0))
        self.assertIsNone(row['related_transaction_id'])

    def test_business_refund_rule_reuses_explicit_totals_choice(self):
        self.fixture.apply({'ids':[self.fixture.ids['SUPPLIER REFUND']],'treatment':'refund',
            'refundUsage':'business','businessId':self.business,'category':'Office supplies','includeInTotals':True,
            'rememberRule':True,'rulePattern':'SUPPLIER REFUND','ruleAccountId':'card','ruleMode':'review'})
        row = self.import_row('card','SUPPLIER REFUND','credit')
        self.assertEqual((row['credit_treatment'],row['classification'],row['include_in_totals']),('refund','business',1))
        self.assertIsNone(row['related_transaction_id'])

    def test_invalid_rule_in_single_editor_rolls_back_the_edit(self):
        before = self.fixture.row('PLUS MEMBERSHIP')
        self.handler.read_json = lambda:{'category':'Meals','rememberRule':True,'rulePattern':'PLUS MEMBERSHIP',
            'ruleAccountId':'bank','ruleMode':'review'}
        with self.assertRaisesRegex(ValueError,'must match'):
            self.handler.update_transaction(before['id'])
        self.assertEqual(self.fixture.row('PLUS MEMBERSHIP'),before)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM review_actions').fetchone()[0],0)

    def test_single_editor_saves_rule_and_explicit_account_scope(self):
        self.handler.read_json = lambda:{'category':'Meals','rememberRule':True,'rulePattern':'PLUS MEMBERSHIP',
            'ruleAccountId':None,'ruleAllAccounts':True,'ruleMode':'review'}
        status,result = self.handler.update_transaction(self.fixture.ids['PLUS MEMBERSHIP'])
        self.assertEqual(status,200)
        self.assertTrue(result['ruleId'])
        row = self.import_row('bank','PLUS MEMBERSHIP')
        self.assertEqual((row['category_name'],row['include_in_totals']),('Meals',1))

    def test_changed_rule_after_preview_requires_a_new_preview(self):
        self.categorize()
        body = {'ids':[self.fixture.ids['PLUS MEMBERSHIP']],'businessId':self.business,'category':'Meals',
            'rememberRule':True,'rulePattern':'PLUS MEMBERSHIP','ruleAccountId':'card','ruleMode':'categorize'}
        with server.connect() as db:
            preview = categorization.plan(db,body,self.handler.validate_transaction)[0]
            automation.save(db,{'type':'expense','patterns':['PLUS MEMBERSHIP'],'accountId':'card',
                'businessId':self.business,'category':'Office supplies','mode':'suggest'},server.utc_now())
            with self.assertRaisesRegex(ValueError,'changed'):
                categorization.commit(db,body|{'revision':preview['revision']},self.handler,server.utc_now())

    def test_reports_download_is_standalone_consistent_and_keeps_rules(self):
        self.categorize()
        self.handler.local_request = lambda:True
        self.handler.path = '/api/export.sqlite3?businessId=ignored&year=1900'
        self.handler.download = lambda data,name,content_type:(data,name,content_type)
        # Keep committed data in an open WAL connection while downloading.
        with server.connect() as live:
            live.execute('PRAGMA wal_autocheckpoint=0')
            live.execute("INSERT INTO app_metadata(key,value) VALUES('export-check','saved in WAL')")
            live.execute("INSERT INTO staged_imports VALUES('private-staging',x'00','{}','hash',0)")
            live.commit()
            content,name,content_type = self.handler.get_request()
        self.assertTrue(content.startswith(b'SQLite format 3\x00'))
        self.assertTrue(name.endswith('.sqlite3'))
        self.assertEqual(content_type,'application/vnd.sqlite3')
        target = self.fixture.root/'exported.sqlite3'
        target.write_bytes(content)
        with closing(sqlite3.connect(target)) as exported:
            self.assertEqual(exported.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(exported.execute("SELECT value FROM app_metadata WHERE key='export-check'").fetchone()[0],'saved in WAL')
            self.assertEqual(exported.execute('SELECT count(*) FROM staged_imports').fetchone()[0],0)
            self.assertEqual(exported.execute('SELECT count(*) FROM merchant_rules WHERE active=1').fetchone()[0],1)
            self.assertEqual(exported.execute('SELECT count(*) FROM transactions').fetchone()[0],7)
            self.assertEqual(exported.execute('SELECT count(*) FROM original_transactions').fetchone()[0],7)
        with server.connect() as live:
            self.assertEqual(live.execute('SELECT count(*) FROM staged_imports').fetchone()[0],1)


if __name__=='__main__': unittest.main()
