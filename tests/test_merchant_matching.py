"""Merchant spelling variations retain boundaries and all other rule limits."""
import json
import unittest

import automation
import server
import test_credits


class MerchantMatchingTests(unittest.TestCase):
    def matches(self,pattern,description,**conditions):
        rule={'pattern':pattern,'account_id':'card','active':1,
            'conditions_json':json.dumps({'patterns':[pattern],**conditions})}
        row={'merchant':'','description':description,'direction':'debit','account_id':'card',
            'amount_cents':2345,'original_source_category':'Transportation-Auto Services'}
        return automation.matches(row,rule)

    def test_names_allow_numeric_store_suffixes_and_optional_word_spaces(self):
        for pattern,description in [('MAVIS','AplPay MAVIS04531 CHARLOTTESVILLE'),('MAVIS','mavis 123'),
            ('ADVANCE AUTO','PAYPAL *ADVANCEAUTO 8772382623'),('DO NOT PAY','DONOTPAY'),
            ('APPLE.COM/BI','APPLE.COM/BI8001234567'),('LOWES','CARD PURCHASE LOWES567'),
            ('CAFÉ','ＣＡＦÉ123')]:
            with self.subTest(pattern=pattern,description=description):self.assertTrue(self.matches(pattern,description))

    def test_names_do_not_match_inside_other_words_or_expand_explicit_store_numbers(self):
        for pattern,description in [('MAVIS','SUPERMAVIS123'),('MAVIS','MAVISION'),('MAVIS','MAVIS123TIRE'),
            ('APPLE.COM','PINEAPPLE.COM'),('BP','SUBPAY'),('STORE 12','STORE 123'),
            ('MAVIS04531','MAVIS045312')]:
            with self.subTest(pattern=pattern,description=description):self.assertFalse(self.matches(pattern,description))

    def test_source_labels_and_amount_limits_do_not_gain_fuzzy_matching(self):
        self.assertTrue(self.matches('ADVANCE AUTO','ADVANCEAUTO',sourceCategories=['Transportation-Auto Services'],minCents=2000,maxCents=2400))
        self.assertFalse(self.matches('ADVANCE AUTO','ADVANCEAUTO',sourceCategories=['Auto Services']))
        self.assertFalse(self.matches('ADVANCE AUTO','ADVANCEAUTO',minCents=2400))
        self.assertFalse(self.matches('ADVANCE AUTO','ADVANCEAUTO',maxCents=2300))


class MerchantMatchingImportTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr,server,'PROFILE_PATH',server.PROFILE_PATH)
        self.fixture=test_credits.CreditReviewTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown)

    def test_future_imports_reuse_matching_for_expenses_and_refunds_with_account_scope(self):
        with server.connect() as db:
            for kind,pattern in [('expense','MAVIS'),('credit','NAPA STORE')]:
                automation.save(db,{'type':kind,'patterns':[pattern],'accountId':'card',
                    'businessId':self.fixture.business,'category':'Office supplies','treatment':'refund' if kind=='credit' else '',
                    'mode':'review','includeInTotals':True},server.utc_now())
        content=b'Date,Description,Debit,Credit\n11/20/2026,MAVIS04531,23.45,\n11/21/2026,NAPASTORE1256,,10.00\n'
        self.fixture.import_csv('card',content)
        self.fixture.import_csv('bank',content.replace(b'MAVIS04531',b'BANK MAVIS04531').replace(b'NAPASTORE1256',b'BANK NAPASTORE1256'))
        with server.connect() as db:
            rows=db.execute("SELECT * FROM transactions WHERE date>='2026-11-20' ORDER BY account_id,date").fetchall()
            self.assertEqual(len(rows),4)
            for row in rows:
                if row['account_id']=='card':
                    self.assertEqual((row['category_name'],row['status'],row['include_in_totals']),('Office supplies','approved',1))
                    if row['direction']=='credit':self.assertEqual(row['credit_treatment'],'refund')
                else:self.assertEqual((row['status'],row['include_in_totals']),('needs_review',0))

    def test_newly_overlapping_merchant_rules_still_require_conflict_review(self):
        with server.connect() as db:
            for pattern,category in [('MAVIS','Office supplies'),('MAVIS123','Meals')]:
                automation.save(db,{'type':'expense','patterns':[pattern],'accountId':'card',
                    'businessId':self.fixture.business,'category':category,'mode':'review','includeInTotals':True},server.utc_now())
        self.fixture.import_csv('card',b'Date,Description,Debit,Credit\n11/22/2026,MAVIS123,23.45,\n')
        with server.connect() as db:
            row=db.execute("SELECT * FROM transactions WHERE description='MAVIS123'").fetchone()
            self.assertEqual((row['status'],row['include_in_totals']),('needs_review',0))
            self.assertTrue(automation.choose(row,automation.all_rules(db))['conflict'])
