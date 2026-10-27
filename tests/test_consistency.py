"""Legacy conflicts stay visible; new writes cannot repeat them."""
import json
import unittest

import automation
import categorization
import consistency
import credits
import server
import test_credits


class PersonalConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, server, 'PROFILE_PATH', server.PROFILE_PATH)
        self.fixture = test_credits.CreditReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.handler = self.fixture.handler
        self.handler.local_request = lambda: True
        self.handler.headers = {'X-Bookkeeper-Workspace': server.WORKSPACE_ID}
        self.tx_id = self.fixture.ids['PLUS MEMBERSHIP']

    def request(self, path, body):
        self.handler.path = path
        self.handler.read_json = lambda: body
        return self.handler.post_request()

    def legacy_transaction(self):
        with server.connect() as db:
            category = db.execute("SELECT id FROM categories WHERE name='Personal / non-business'").fetchone()[0]
            db.execute("UPDATE transactions SET category_id=?,category_name='Personal / non-business' WHERE id=?", (category, self.tx_id))

    def legacy_rule(self, kind='expense'):
        table = 'merchant_rules' if kind == 'expense' else 'credit_rules'
        fields = ['id', 'pattern', 'account_id', 'business_id', 'category_name', 'active', 'created_at',
                  'conditions_json', 'automation_mode', 'include_expenses']
        values = ['legacy-' + kind, 'PLUS MEMBERSHIP', 'card', self.fixture.business,
                  'Personal / non-business', 1, server.utc_now(),
                  json.dumps({'patterns': ['PLUS MEMBERSHIP'], 'direction': 'debit' if kind == 'expense' else 'credit'}), 'review', 1]
        if kind == 'credit':
            fields.append('treatment')
            values.append('refund')
        with server.connect() as db:
            db.execute('INSERT INTO ' + table + '(' + ','.join(fields) + ') VALUES(' + ','.join('?' for _ in fields) + ')', values)
        return 'legacy-' + kind

    def snapshot(self):
        with server.connect() as db:
            return {table: [tuple(row) for row in db.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                    for table in ('transactions', 'categories', 'merchant_rules', 'credit_rules', 'review_actions',
                                  'review_action_items', 'transaction_history', 'original_transactions')}

    def test_reading_legacy_conflicts_flags_reviewed_rows_and_rules_without_changing_books(self):
        self.legacy_transaction()
        rule_id = self.legacy_rule()
        before = self.snapshot()
        total = self.fixture.expense_total()
        self.handler.path = '/api/transactions'
        status, transactions = self.handler.get_request()
        self.assertEqual(status, 200)
        flagged = [row for row in transactions if row['consistencyIssue']]
        self.assertEqual([row['id'] for row in flagged], [self.tx_id])
        self.assertEqual((flagged[0]['status'], flagged[0]['includeInTotals']), ('approved', True))
        with server.connect() as db:
            rules = automation.overview(db)['rules']
        self.assertTrue(next(rule for rule in rules if rule['id'] == rule_id)['consistencyIssue'])
        self.assertEqual(self.fixture.expense_total(), total)
        self.assertEqual(self.snapshot(), before)

    def test_editor_rejects_personal_category_in_business_books_and_rolls_back_history(self):
        before = self.snapshot()
        for included in (False, True):
            with self.subTest(included=included):
                status, body = self.request('/api/transactions/' + self.tx_id,
                                            {'category': 'Personal / non-business', 'includeInTotals': included})
                self.assertEqual(status, 400)
                self.assertIn('Mark the transaction Personal', body['error'])
                self.assertEqual(self.snapshot(), before)

    def test_unreviewed_and_reviewed_categorization_cannot_create_a_conflict(self):
        before = self.snapshot()
        for reviewed in (False, True):
            with self.subTest(reviewed=reviewed), server.connect() as db:
                body = {'ids': [self.tx_id], 'businessId': self.fixture.business,
                        'category': 'Personal / non-business', 'markReviewed': reviewed, 'includeInTotals': reviewed}
                preview = categorization.plan(db, body, self.handler.validate_transaction)[0]
                self.assertEqual((preview['applicableCount'], preview['exceptionCount']), (0, 1))
                self.assertIn('Mark the transaction Personal', preview['exceptions'][0]['reason'])
                with self.assertRaisesRegex(ValueError, 'attention'):
                    categorization.commit(db, body | {'revision': preview['revision']}, self.handler, server.utc_now())
        self.assertEqual(self.snapshot(), before)

    def test_batch_approve_and_include_reject_existing_personal_conflicts_atomically(self):
        self.legacy_transaction()
        before = self.snapshot()
        for action in ('approve', 'include'):
            with self.subTest(action=action):
                status, body = self.request('/api/review/batch', {'ids': [self.fixture.ids['SUPPLIER PURCHASE'], self.tx_id], 'action': action})
                self.assertEqual(status, 400)
                self.assertIn('Personal / non-business', body['error'])
                self.assertEqual(self.snapshot(), before)

    def test_business_refund_cannot_use_a_personal_category(self):
        before = self.snapshot()
        with server.connect() as db, self.assertRaisesRegex(ValueError, 'Personal / non-business'):
            credits.plan(db, {'ids': [self.fixture.ids['SUPPLIER REFUND']], 'treatment': 'refund',
                             'refundUsage': 'business', 'businessId': self.fixture.business,
                             'category': 'Personal / non-business'}, self.handler.validate_transaction)
        self.assertEqual(self.snapshot(), before)

    def test_rule_apis_reject_personal_business_refunds_and_included_personal_expenses(self):
        before = self.snapshot()
        for mode in automation.MODES:
            for kind in ('expense', 'credit'):
                with self.subTest(mode=mode, kind=kind):
                    status, body = self.request('/api/automation/rules', {'type': kind, 'patterns': ['PLUS MEMBERSHIP'],
                        'accountId':None,'businessId': self.fixture.business, 'category': 'Personal / non-business',
                        'mode': mode, 'treatment': 'refund','includeInTotals':kind=='expense'})
                    self.assertEqual(status, 400)
                    self.assertIn('personal', body['error'].lower())
        status, _ = self.request('/api/rules', {'pattern': 'PLUS MEMBERSHIP', 'accountId':None,'businessId': self.fixture.business,
                                              'category': 'Personal / non-business'})
        self.assertEqual(status, 400)
        self.assertEqual(self.snapshot(), before)

    def test_legacy_personal_rule_can_be_paused_but_not_reenabled_through_any_api(self):
        for kind, legacy_path in [('expense', '/api/rules'), ('credit', '/api/credits/rules')]:
            rule_id = self.legacy_rule(kind)
            for path in ('/api/automation/rules', legacy_path):
                with self.subTest(kind=kind, path=path):
                    identity = {'id': rule_id, **({'type': kind} if path == '/api/automation/rules' else {})}
                    status, _ = self.request(path, identity | {'active': False})
                    self.assertEqual(status, 200)
                    status, body = self.request(path, identity | {'active': True})
                    self.assertEqual(status, 400)
                    self.assertIn('Pause', body['error'])

    def test_legacy_personal_rule_never_runs_on_a_future_import(self):
        self.legacy_rule()
        self.fixture.import_csv('card', b'Date,Description,Debit,Credit\n11/01/2026,PLUS MEMBERSHIP,18.25,\n')
        with server.connect() as db:
            row = db.execute("SELECT * FROM transactions WHERE date='2026-11-01'").fetchone()
            self.assertEqual((row['classification'], row['status'], row['include_in_totals']), ('unknown', 'needs_review', 0))
            self.assertTrue(categorization.suggestions(db)[row['id']]['conflict'])
            preview = automation.plan(db, self.handler)[0]
            self.assertIn(row['id'], preview['groups']['conflicts'])
            self.assertEqual(preview['rows'], [])

    def test_personal_correction_has_history_and_undo_cannot_restore_the_conflict(self):
        self.legacy_transaction()
        status, result = self.request('/api/review/batch', {'ids': [self.tx_id], 'action': 'personal'})
        self.assertEqual(status, 200)
        corrected = self.fixture.row('PLUS MEMBERSHIP')
        self.assertEqual((corrected['classification'], corrected['business_id'], corrected['include_in_totals']), ('personal', None, 0))
        self.assertIsNone(consistency.transaction_issue(corrected))
        self.assertEqual(self.fixture.expense_total(), 6000)
        with server.connect() as db:
            self.assertGreater(db.execute('SELECT count(*) FROM transaction_history WHERE action_id=?', (result['actionId'],)).fetchone()[0], 0)
        status, undone = self.request('/api/review/undo', {'actionId': result['actionId']})
        self.assertEqual(status, 200)
        self.assertEqual((undone['restored'], undone['conflicts']), ([], [self.tx_id]))
        self.assertEqual(self.fixture.row('PLUS MEMBERSHIP'), corrected)

    def test_editor_can_correct_the_classification_or_choose_a_business_category(self):
        self.legacy_transaction()
        status, _ = self.request('/api/transactions/' + self.tx_id, {'classification': 'personal', 'includeInTotals': False})
        self.assertEqual(status, 200)
        self.assertIsNone(consistency.transaction_issue(self.fixture.row('PLUS MEMBERSHIP')))
        status, _ = self.request('/api/transactions/' + self.tx_id, {'classification': 'business',
            'businessId': self.fixture.business, 'category': 'Office supplies', 'includeInTotals': True})
        self.assertEqual(status, 200)
        self.assertEqual(self.fixture.expense_total(), 7295)

    def test_category_matching_handles_formatting_without_flagging_business_equipment(self):
        self.assertTrue(consistency.is_personal_category('  PERSONAL ／ NON-BUSINESS  '))
        self.assertFalse(consistency.is_personal_category('Personal protective equipment'))
        row = self.fixture.row('PLUS MEMBERSHIP')
        self.assertIsNone(consistency.transaction_issue(row))
        self.assertIsNone(consistency.transaction_issue(row | {'classification': 'personal', 'include_in_totals': 0,
                                                              'category_name': 'Personal / non-business'}))


if __name__ == '__main__':
    unittest.main()
