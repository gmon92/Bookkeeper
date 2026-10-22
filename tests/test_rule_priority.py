"""Merchant exceptions precede category fallbacks in every rule workflow."""
import unittest

import automation
import credits
import server
import test_credits


class RulePriorityTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, server, 'PROFILE_PATH', server.PROFILE_PATH)
        self.fixture = test_credits.CreditReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.handler = self.fixture.handler
        self.business = self.fixture.business
        self.tx_id = self.fixture.ids['PLUS MEMBERSHIP']

    def category_rule(self, db, **overrides):
        return automation.save(db, {'type': 'expense', 'patterns': [], 'sourceCategory': 'Benefits',
            'accountId': 'card', 'minAmount': '1.00', 'maxAmount': '100.00',
            'businessId': self.business, 'category': 'Office supplies', 'mode': 'review',
            'includeInTotals': True} | overrides, server.utc_now())['id']

    def merchant_rule(self, db, **overrides):
        return automation.save(db, {'type': 'expense', 'patterns': ['PLUS MEMBERSHIP'],
            'accountId': None, 'businessId': self.business, 'category': 'Meals', 'mode': 'suggest'} | overrides,
            server.utc_now())['id']

    def unreview_member(self, db):
        db.execute("""UPDATE transactions SET status='needs_review',include_in_totals=0,
            classification='unknown',business_id=NULL,category_id=NULL,
            category_name='Uncategorized / review' WHERE id=?""", (self.tx_id,))

    def test_global_merchant_overrides_scoped_category_even_with_less_automatic_mode(self):
        for mode in automation.MODES:
            with self.subTest(mode=mode), server.connect() as db:
                db.execute('UPDATE merchant_rules SET active=0')
                self.unreview_member(db)
                category_id = self.category_rule(db)
                merchant_id = self.merchant_rule(db, mode=mode, includeInTotals=mode == 'review')
                row = next(row for row in automation.rows(db) if row['id'] == self.tx_id)
                match = automation.choose(row, automation.all_rules(db))
                self.assertEqual(match['rule']['id'], merchant_id)
                self.assertEqual(match['overriddenRuleIds'], [category_id])
                self.assertIn('Merchant description rules take priority', match['reason'])
                preview = automation.plan(db, self.handler)[0]
                if mode == 'suggest':
                    self.assertIn(self.tx_id, preview['groups']['suggested'])
                    self.assertEqual(preview['rows'], [])
                else:
                    change = next(row for row in preview['rows'] if row['id'] == self.tx_id)
                    self.assertEqual(change['new']['category_name'], 'Meals')
                    self.assertEqual(change['new']['status'], 'approved' if mode == 'review' else 'suggested')
                    self.assertEqual(change['new']['include_in_totals'], int(mode == 'review'))
                    automation.apply(db, self.handler, server.utc_now(), revision=preview['revision'])
                    self.assertEqual(db.execute('SELECT category_name FROM transactions WHERE id=?', (self.tx_id,)).fetchone()[0], 'Meals')

    def test_credit_merchant_rule_overrides_a_category_credit_rule(self):
        with server.connect() as db:
            category_id = self.category_rule(db, type='credit', treatment='statement_credit',
                businessId=None, category='', includeInTotals=False)
            merchant_id = self.merchant_rule(db, type='credit', patterns=['PLATINUM WALMART CREDIT'],
                treatment='excluded_credit', businessId=None, category='', mode='review')
            row = next(row for row in automation.rows(db) if row['id'] == self.fixture.ids['Platinum Walmart+ Credit'])
            match = automation.choose(row, automation.all_rules(db))
            self.assertEqual((match['rule']['id'], match['overriddenRuleIds']), (merchant_id, [category_id]))
            suggestion = credits.suggestion(row, credits.rules(db))
            self.assertEqual(suggestion['treatment'], 'excluded_credit')
            preview = automation.plan(db, self.handler)[0]
            change = next(change for change in preview['rows'] if change['id'] == row['id'])
            self.assertEqual(change['new']['credit_treatment'], 'excluded_credit')

    def test_category_is_used_when_the_merchant_rule_does_not_match_or_is_paused(self):
        with server.connect() as db:
            category_id = self.category_rule(db)
            merchant_id = self.merchant_rule(db, minAmount='20.00')
            row = next(row for row in automation.rows(db) if row['id'] == self.tx_id)
            self.assertEqual(automation.choose(row, automation.all_rules(db))['rule']['id'], category_id)
            automation.save(db, {'id': merchant_id, 'type': 'expense', 'active': False}, server.utc_now())
            self.assertEqual(automation.choose(row, automation.all_rules(db))['rule']['id'], category_id)

    def add_reviewed_example(self):
        self.fixture.import_csv('card', b'Date,Description,Debit,Credit,Category\n10/21/2026,PLUS MEMBERSHIP,16.25,,Benefits\n')

    def merchant_ideas(self, db):
        return [idea for idea in automation.overview(db)['proposals'] if idea['patterns'] == ['PLUS MEMBERSHIP']]

    def test_category_rules_do_not_hide_merchant_ideas_but_complete_merchant_coverage_does(self):
        with server.connect() as db:
            self.category_rule(db)
        self.add_reviewed_example()
        with server.connect() as db:
            self.assertEqual(self.merchant_ideas(db)[0]['count'], 2)
            merchant_id = self.merchant_rule(db, category='Office supplies')
            self.assertEqual(self.merchant_ideas(db), [])
            automation.save(db, {'id': merchant_id, 'type': 'expense', 'active': False}, server.utc_now())
            self.assertEqual(self.merchant_ideas(db)[0]['count'], 2)

    def test_partial_merchant_coverage_does_not_hide_uncovered_rule_ideas(self):
        with server.connect() as db:
            self.category_rule(db)
        self.add_reviewed_example()
        with server.connect() as db:
            self.merchant_rule(db, category='Office supplies', minAmount='15.00')
            self.assertEqual(self.merchant_ideas(db)[0]['count'], 2)

    def test_existing_pass_preserves_reviewed_decisions_even_when_merchant_would_win(self):
        before = self.fixture.row('PLUS MEMBERSHIP')
        with server.connect() as db:
            self.category_rule(db)
            self.merchant_rule(db, mode='review', includeInTotals=True)
            preview = automation.plan(db, self.handler)[0]
            self.assertNotIn(self.tx_id, [row['id'] for row in preview['rows']])
            result = automation.apply(db, self.handler, server.utc_now(), revision=preview['revision'])
            self.assertIsNone(result['actionId'])
        self.assertEqual(self.fixture.row('PLUS MEMBERSHIP'), before)


if __name__ == '__main__':
    unittest.main()
