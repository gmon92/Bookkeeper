"""A blocked batch stays atomic; explicit subsets and repaired rows can proceed."""
import unittest

import categorization
import server
import test_credits


class CategorizationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_credits.CreditReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.handler=self.fixture.handler
        self.good=[self.fixture.ids['PLUS MEMBERSHIP'],self.fixture.ids['SUPPLIER PURCHASE']]
        self.bad=self.fixture.ids['CARD WITHDRAWAL']
        with server.connect() as db:
            db.execute("UPDATE transactions SET direction='unknown',transaction_kind='unknown' WHERE id=?",(self.bad,))
        self.body={'ids':self.good+[self.bad],'businessId':self.fixture.business,'category':'Meals','markReviewed':True,'includeInTotals':True}

    def test_blocked_preview_then_explicit_subset_changes_only_checked_rows(self):
        before=self.fixture.row('CARD WITHDRAWAL')
        with server.connect() as db:
            plan=categorization.plan(db,self.body,self.handler.validate_transaction)[0]
            self.assertEqual(plan['exceptionCount'],1)
            self.assertEqual(plan['exceptions'][0]['id'],self.bad)
            with self.assertRaisesRegex(ValueError,'attention'):
                categorization.commit(db,self.body|{'revision':plan['revision']},self.handler,server.utc_now())
            subset=self.body|{'ids':self.good}
            preview=categorization.plan(db,subset,self.handler.validate_transaction)[0]
            result=categorization.commit(db,subset|{'revision':preview['revision']},self.handler,server.utc_now())
            self.assertEqual(result['count'],2)
            self.assertEqual({r[0] for r in db.execute("SELECT id FROM transactions WHERE category_name='Meals'")},set(self.good))
        self.assertEqual(self.fixture.row('CARD WITHDRAWAL'),before)

    def test_reviewing_a_flagged_row_allows_the_original_batch_to_be_previewed_again(self):
        with server.connect() as db:
            initial=categorization.plan(db,self.body,self.handler.validate_transaction)[0]
            self.assertEqual(initial['exceptionCount'],1)
        self.handler.read_json=lambda:{'direction':'debit','kind':'expense'}
        status,_=self.handler.update_transaction(self.bad)
        self.assertEqual(status,200)
        with server.connect() as db:
            preview=categorization.plan(db,self.body,self.handler.validate_transaction)[0]
            self.assertEqual(preview['exceptionCount'],0)
            self.assertEqual(preview['applicableCount'],3)
            result=categorization.commit(db,self.body|{'revision':preview['revision']},self.handler,server.utc_now())
            self.assertEqual(result['count'],3)

    def test_attention_is_returned_even_when_every_row_fails_and_rule_is_requested(self):
        body=self.body|{'ids':[self.bad],'rememberRule':True,'rulePattern':'CARD WITHDRAWAL','ruleAccountId':'bank'}
        with server.connect() as db:
            plan=categorization.plan(db,body,self.handler.validate_transaction)[0]
            self.assertEqual(plan['exceptionCount'],1)
            self.assertEqual(plan['applicableCount'],0)
            with self.assertRaises(ValueError):categorization.commit(db,body|{'revision':plan['revision']},self.handler,server.utc_now())
            self.assertEqual(db.execute('SELECT count(*) FROM merchant_rules').fetchone()[0],0)

    def test_a_credit_can_be_left_out_without_changing_its_credit_decision(self):
        credit=self.fixture.ids['Platinum Walmart+ Credit']
        before=self.fixture.row('Platinum Walmart+ Credit')
        with server.connect() as db:
            plan=categorization.plan(db,self.body|{'ids':self.good+[credit]},self.handler.validate_transaction)[0]
            self.assertEqual(plan['exceptions'][0]['id'],credit)
            subset=self.body|{'ids':self.good}
            plan=categorization.plan(db,subset,self.handler.validate_transaction)[0]
            categorization.commit(db,subset|{'revision':plan['revision']},self.handler,server.utc_now())
        self.assertEqual(self.fixture.row('Platinum Walmart+ Credit'),before)


if __name__=='__main__':unittest.main()
