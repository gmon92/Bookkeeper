"""Original category rules match new merchants, scopes and money directions."""
import unittest

import automation
import categorization
import server
import test_credits
import workspace_store


class StatementCategoryRuleTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr,server,'PROFILE_PATH',server.PROFILE_PATH)
        self.fixture=test_credits.CreditReviewTests()
        self.fixture.setUp(); self.addCleanup(self.fixture.tearDown)

    def save(self, **options):
        body={'type':'expense','patterns':[],'sourceCategories':['Benefits','Supplies'],
            'accountId':'card','businessId':self.fixture.business,'category':'Meals',
            'mode':'review','includeInTotals':True}|options
        with server.connect() as db:
            result=automation.save(db,body,server.utc_now())
            return body|{'id':result['id']}

    def import_row(self, description, category, account='card', direction='debit'):
        debit,credit=('23.45','') if direction=='debit' else ('','23.45')
        self.fixture.import_csv(account,('Date,Description,Debit,Credit,Category\n11/15/2026,'+description+','+debit+','+credit+','+category+'\n').encode())
        with server.connect() as db:
            return dict(db.execute('SELECT * FROM transactions WHERE description=? AND date=?',(description,'2026-11-15')).fetchone())

    def test_category_rule_matches_different_new_merchants_and_multiple_labels(self):
        before=self.fixture.row('PLUS MEMBERSHIP')
        self.save()
        for merchant,label in [('UNSEEN CAFE','Benefits'),('NEW GAS STATION','Supplies')]:
            row=self.import_row(merchant,label)
            self.assertEqual((row['category_name'],row['status'],row['include_in_totals']),('Meals','approved',1))
        self.assertEqual(self.import_row('DIFFERENT LABEL','Travel')['status'],'needs_review')
        self.assertEqual(self.fixture.row('PLUS MEMBERSHIP'),before)

    def test_account_and_direction_are_kept_separate(self):
        self.save()
        self.assertEqual(self.import_row('ANOTHER ACCOUNT','Benefits',account='bank')['status'],'needs_review')
        credit=self.import_row('MONEY IN','Benefits',direction='credit')
        self.assertEqual((credit['status'],credit['credit_treatment'],credit['include_in_totals']),('needs_review','',0))

    def test_category_credit_rule_reuses_decision_across_accounts(self):
        original=self.fixture.row('PLUS MEMBERSHIP')
        self.save(type='credit',sourceCategories=['Benefits'],accountId=None,businessId=None,category='',treatment='statement_credit',includeInTotals=False)
        for account,merchant in [('card','CARD BENEFIT'),('bank','BANK BENEFIT')]:
            row=self.import_row(merchant,'Benefits',account=account,direction='credit')
            self.assertEqual((row['credit_treatment'],row['excluded'],row['include_in_totals']),('statement_credit',1,0))
        self.assertEqual(self.fixture.row('PLUS MEMBERSHIP'),original)

    def test_legacy_single_category_and_normalized_labels_still_work(self):
        self.save(sourceCategories=['Food / Meals'])
        self.assertEqual(self.import_row('UNKNOWN RESTAURANT','food - MEALS')['category_name'],'Meals')
        body=self.save(sourceCategories=['Benefits'],sourceCategory='Benefits')
        with server.connect() as db:
            legacy=body.copy(); legacy.pop('sourceCategories')
            automation.save(db,legacy,server.utc_now())
            saved=next(r for r in automation.all_rules(db) if r['id']==body['id'])
            self.assertEqual(automation.conditions(saved)['sourceCategory'],'Benefits')
            self.assertEqual(automation.source_categories(saved),['Benefits'])
            self.assertIn('original statement category equals',automation.reason(saved))

    def test_single_category_exception_and_merchant_exception_override_broad_rule(self):
        self.save(accountId=None)
        self.save(sourceCategories=['Benefits'],accountId=None,category='Office supplies')
        self.save(sourceCategories=[],patterns=['SPECIAL MERCHANT'],accountId=None,category='Fuel')
        self.assertEqual(self.import_row('SOME MERCHANT','Benefits')['category_name'],'Office supplies')
        self.assertEqual(self.import_row('SPECIAL MERCHANT','Benefits')['category_name'],'Fuel')

    def test_save_decision_uses_original_categories_without_locking_to_merchants(self):
        body={'ids':[self.fixture.ids['PLUS MEMBERSHIP'],self.fixture.ids['SUPPLIER PURCHASE']],
            'businessId':self.fixture.business,'category':'Meals','markReviewed':True,'includeInTotals':True,
            'rememberRule':True,'ruleMatch':'sourceCategory','ruleSourceCategories':['Benefits','Supplies'],
            'ruleAccountId':'card','ruleMode':'review'}
        with server.connect() as db:
            preview=categorization.plan(db,body,self.fixture.handler.validate_transaction)[0]
            saved=categorization.commit(db,body|{'revision':preview['revision']},self.fixture.handler,server.utc_now())
            rule=next(r for r in automation.all_rules(db) if r['id']==saved['ruleId'])
            self.assertEqual(automation.conditions(rule)['patterns'],[])
        row=self.import_row('A COMPLETELY NEW MERCHANT','Supplies')
        self.assertEqual(row['category_name'],'Meals')

    def test_add_source_groups_to_existing_rule_retains_its_categories(self):
        body=self.save(sourceCategories=['Benefits'])
        expanded=body|{'sourceCategories':['Benefits','Supplies'],'selectedIds':[self.fixture.ids['SUPPLIER PURCHASE']]}
        with server.connect() as db:
            self.assertEqual(automation.rule_preview(db,expanded)['matched'],2)
            automation.save(db,expanded,server.utc_now())
            self.assertEqual(db.execute('SELECT count(*) FROM merchant_rules').fetchone()[0],1)
        self.assertEqual(self.import_row('EXPANDED LABEL','Supplies')['category_name'],'Meals')

    def test_blank_category_cannot_create_a_rule_that_matches_everything(self):
        for categories in ([],[''],['  '],['Benefits','']):
            with self.subTest(categories=categories),self.assertRaises(ValueError):self.save(sourceCategories=categories)

    def test_group_layout_preference_persists_and_rejects_invalid_views(self):
        with server.connect() as db:
            workspace_store.save_profile_settings(db,{'groupLayout':'details'})
        with server.connect() as db:
            self.assertEqual(workspace_store.profile_settings(db)['groupLayout'],'details')
            with self.assertRaises(ValueError):workspace_store.save_profile_settings(db,{'groupLayout':'anything'})
            workspace_store.save_profile_settings(db,{'groupLayout':'cards'})
            self.assertEqual(workspace_store.profile_settings(db)['groupLayout'],'cards')


if __name__=='__main__':unittest.main()
