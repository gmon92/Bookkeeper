"""Suggestions explain review groups without deciding bookkeeping treatment."""
import csv
import io
import unittest
from pathlib import Path

import review_batches
import server
import test_credits


class SuggestedBatchTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, server, 'PROFILE_PATH', server.PROFILE_PATH)
        self.fixture = test_credits.CreditReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.handler = self.fixture.handler

    def import_rows(self, rows, account='card'):
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['Date', 'Description', 'Debit', 'Credit'])
        writer.writerows(rows)
        self.fixture.import_csv(account, output.getvalue().encode())

    def overview(self):
        with server.connect() as db:
            return review_batches.overview(db)

    def row(self, description, direction='debit'):
        with server.connect() as db:
            return dict(db.execute('SELECT * FROM transactions WHERE description=? AND direction=?',
                                   (description, direction)).fetchone())

    def snapshot(self):
        with server.connect() as db:
            return {table: [tuple(row) for row in db.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                    for table in ('transactions', 'categories', 'merchant_rules', 'credit_rules', 'review_actions',
                                  'review_action_items', 'transaction_history', 'original_transactions')}

    def test_service_aliases_group_by_purpose_without_merging_different_google_products(self):
        self.import_rows([
            ('11/01/2026', 'AplPay DO NOT PAY LAPALO ALTO CA', '36.00', ''),
            ('12/01/2026', 'AplPay DONOTPAY PALO ALTO CA', '36.00', ''),
            ('11/02/2026', 'GOODRXGOLD GOODRX SANTA MONICA CA', '19.00', ''),
            ('12/02/2026', 'GOODRX GOLD SANTA MONICA CA', '9.99', ''),
            ('11/03/2026', 'PAYPAL GOOGLE YOUTU8558363987 CA', '7.99', ''),
            ('12/03/2026', 'PAYPAL GOOGLE YOUTU8558363987 CA', '7.99', ''),
            ('11/04/2026', 'PAYPAL GOOGLE GOOGL8558363987 CA', '9.99', ''),
            ('12/04/2026', 'PAYPAL GOOGLE GOOGL8558363987 CA', '9.99', ''),
            ('11/05/2026', 'AMAZON ONEMED 2062661000 WA', '9.00', ''),
            ('12/05/2026', 'AMAZON ONEMED 2062661000 WA', '9.00', ''),
        ])
        groups = self.overview()['groups']
        donotpay = next(group for group in groups if group['title'] == 'DoNotPay')
        self.assertEqual((len(donotpay['ids']), donotpay['category']), (2, 'Subscriptions'))
        health = next(group for group in groups if group['title'] == 'GoodRx')
        self.assertEqual((len(health['ids']), health['category']), (2, ''))
        medical = next(group for group in groups if group['title'] == 'One Medical')
        self.assertEqual((len(medical['ids']), medical['category']), (2, ''))
        youtube = next(group for group in groups if group['title'] == 'YouTube')
        youtube_ids = {self.row('PAYPAL GOOGLE YOUTU8558363987 CA')['id']}
        self.assertTrue(youtube_ids <= set(youtube['ids']))
        self.assertEqual(len(youtube['ids']), 2)
        self.assertNotIn(self.row('PAYPAL GOOGLE GOOGL8558363987 CA')['id'], youtube['ids'])

    def test_cleaning_and_general_retail_groups_ask_different_questions(self):
        self.import_rows([
            ('11/01/2026', 'GREEN CLEAN 513 GREECHARLOTTESVIL VA', '29.00', ''),
            ('12/01/2026', 'ALL AMERICAN CAR WASCHARLOTTESVIL VA', '8.00', ''),
            ('11/02/2026', 'AMAZON COM AMZN COM BILL WA', '82.00', ''),
            ('12/02/2026', 'PAYPAL IKEANORTHAM PA', '145.00', ''),
        ])
        groups = self.overview()['groups']
        cleaning = next(group for group in groups if group['title'] == 'Vehicle cleaning')
        retail = next(group for group in groups if group['title'] == 'Purchases needing receipts')
        self.assertEqual((len(cleaning['ids']), cleaning['category']), (2, 'Cleaning / detailing'))
        self.assertEqual((len(retail['ids']), retail['category']), (2, ''))
        self.assertIn('equipment', retail['question'])

    def test_groups_keep_accounts_and_existing_business_assignments_separate(self):
        rows = [('11/01/2026', 'AUDIBLE BUSINESS READING', '15.00', ''),
                ('12/01/2026', 'AUDIBLE BUSINESS READING', '15.00', '')]
        self.import_rows(rows, 'card')
        self.import_rows([(day, description + ' BANK', debit, credit) for day, description, debit, credit in rows], 'bank')
        groups = [group for group in self.overview()['groups'] if group['title'] == 'Audible']
        self.assertEqual({group['accountId'] for group in groups}, {'card', 'bank'})
        self.assertTrue(all(len(group['ids']) == 2 for group in groups))
        bank = groups[0] if groups[0]['accountId'] == 'bank' else groups[1]
        with server.connect() as db:
            db.execute("UPDATE transactions SET classification='business',business_id=? WHERE id=?",
                       (self.fixture.business, bank['ids'][0]))
        self.assertFalse(any(group['accountId'] == 'bank' and group['title'] == 'Audible'
                             for group in self.overview()['groups']))

    def test_exact_merchant_refund_pair_reserves_the_purchase_from_category_batches(self):
        self.import_rows([
            ('11/01/2026', 'AplPay ADVANCE AUTO CHARLOTTESVILLE VA', '73.69', ''),
            ('11/02/2026', 'ADVANCE AUTO PARTS CHARLOTTESVILLE VA', '', '73.69'),
            ('11/01/2026', 'UNRELATED SHOP', '73.69', ''),
            ('11/03/2026', 'AplPay AUTOZONE CHARLOTTESVILLE VA', '12.00', ''),
        ])
        result = self.overview()
        purchase = self.row('AplPay ADVANCE AUTO CHARLOTTESVILLE VA')
        credit = self.row('ADVANCE AUTO PARTS CHARLOTTESVILLE VA', 'credit')
        pair = next(pair for pair in result['pairs'] if pair['creditId'] == credit['id'])
        self.assertEqual((pair['kind'], pair['candidateIds']), ('refund', [purchase['id']]))
        self.assertFalse(any(purchase['id'] in group['ids'] for group in result['groups']))
        self.assertIsNone(self.row('ADVANCE AUTO PARTS CHARLOTTESVILLE VA', 'credit')['related_transaction_id'])

    def test_matching_amount_alone_or_another_account_never_establishes_a_pair(self):
        self.import_rows([('11/01/2026', 'OTHER MERCHANT', '28.38', ''),
                          ('11/02/2026', 'AMAZON MARKETPLACE', '', '28.38')])
        self.import_rows([('11/01/2026', 'AMAZON MARKETPLACE', '28.38', '')], 'bank')
        self.assertFalse(self.overview()['pairs'])

    def test_partial_refund_keeps_multiple_candidates_and_excludes_future_purchases(self):
        self.import_rows([
            ('10/12/2026', 'ADOBE SAN JOSE CA', '19.99', ''),
            ('11/12/2026', 'ADOBE SAN JOSE CA', '19.99', ''),
            ('11/29/2026', 'ADOBE SAN JOSE CA', '', '9.91'),
            ('12/12/2026', 'ADOBE SAN JOSE CA', '19.99', ''),
        ])
        pair = self.overview()['pairs'][0]
        self.assertEqual((pair['kind'], pair['candidateCount'], len(pair['candidateIds'])), ('refund', 2, 2))
        self.assertIn('partial refund', pair['reason'])
        with server.connect() as db:
            dates = [db.execute('SELECT date FROM transactions WHERE id=?', (tx_id,)).fetchone()[0] for tx_id in pair['candidateIds']]
        self.assertEqual(dates, ['2026-11-12', '2026-10-12'])

    def test_rewards_and_clear_are_offsets_with_an_open_treatment_question(self):
        self.import_rows([
            ('11/01/2026', 'PwP AMEXTRAVEL CO SEATTLE WA', '214.75', ''),
            ('11/01/2026', 'POINTS FOR AMEX TRVL', '', '214.75'),
            ('11/02/2026', 'CLEAR CLEARME COM NEW YORK NY', '189.00', ''),
            ('11/03/2026', 'CLEAR NEW YORK', '', '189.00'),
        ])
        pairs = self.overview()['pairs']
        self.assertEqual(len(pairs), 2)
        self.assertTrue(all(pair['kind'] == 'offset' and 'card benefit' in pair['question'] for pair in pairs))

    def test_payments_and_benefits_are_reviewed_separately_from_refund_candidates(self):
        self.import_rows([
            ('11/01/2026', 'ONLINE PAYMENT THANK YOU', '', '100.00'),
            ('11/02/2026', 'PLATINUM DIGITAL ENTERTAINMENT CREDIT', '', '19.99'),
            ('12/02/2026', 'PLATINUM DIGITAL ENTERTAINMENT CREDIT', '', '19.99'),
        ])
        result = self.overview()
        credits_groups = [group for group in result['groups'] if group['kind'] == 'credits']
        payment = next(group for group in credits_groups if group['treatment'] == 'payment')
        benefits = next(group for group in credits_groups if group['treatment'] == 'statement_credit')
        self.assertIn(self.row('ONLINE PAYMENT THANK YOU', 'credit')['id'], payment['ids'])
        with server.connect() as db:
            new_benefits = {row['id'] for row in db.execute("SELECT id FROM transactions WHERE description='PLATINUM DIGITAL ENTERTAINMENT CREDIT'")}
        self.assertEqual(len(new_benefits), 2)
        self.assertTrue(new_benefits <= set(benefits['ids']))
        ids = [tx_id for group in credits_groups for tx_id in group['ids']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_reviewed_excluded_and_possible_duplicate_charges_do_not_enter_batches(self):
        self.import_rows([
            ('11/01/2026', 'AUDIBLE DUPLICATE', '15.00', ''),
            ('11/01/2026', 'AUDIBLE DUPLICATE', '15.00', ''),
            ('11/02/2026', 'AUDIBLE EXCLUDED', '15.00', ''),
            ('12/01/2026', 'AUDIBLE REVIEWED', '15.00', ''),
        ])
        with server.connect() as db:
            db.execute("UPDATE transactions SET excluded=1 WHERE description='AUDIBLE EXCLUDED'")
            db.execute("UPDATE transactions SET classification='personal',status='approved' WHERE description='AUDIBLE REVIEWED'")
        self.assertFalse(any(group['title'] == 'Audible' for group in self.overview()['groups']))

    def test_personal_consistency_conflicts_are_left_to_explicit_correction(self):
        self.import_rows([('11/01/2026', 'AUDIBLE PERSONAL CONFLICT', '15.00', ''),
                          ('12/01/2026', 'AUDIBLE PERSONAL CONFLICT', '15.00', '')])
        with server.connect() as db:
            db.execute("UPDATE transactions SET classification='business',business_id=?,category_name='Personal / non-business' WHERE description='AUDIBLE PERSONAL CONFLICT'", (self.fixture.business,))
        self.assertFalse(any(group['title'] == 'Audible' for group in self.overview()['groups']))

    def test_api_read_is_repeatable_and_never_saves_decisions_rules_or_history(self):
        self.import_rows([('11/01/2026', 'SCRIBD READING', '11.99', ''),
                          ('12/01/2026', 'SCRIBD READING', '11.99', '')])
        before = self.snapshot()
        self.handler.local_request = lambda: True
        self.handler.path = '/api/review/batches'
        status, response = self.handler.get_request()
        self.assertEqual(status, 200)
        self.assertEqual(response, self.overview())
        self.assertEqual(self.snapshot(), before)

    def test_docker_context_includes_all_copied_runtime_sources(self):
        root = Path(server.__file__).parent
        allowed = {line[1:] for line in (root / '.dockerignore').read_text().splitlines() if line.startswith('!')}
        dockerfile = (root / 'Dockerfile').read_text().replace('\\\n', ' ')
        for line in dockerfile.splitlines():
            if line.startswith('COPY '):
                for name in line.split()[1:-1]:
                    self.assertIn(name, allowed)
                    self.assertTrue((root / name).is_file())


if __name__ == '__main__':
    unittest.main()
