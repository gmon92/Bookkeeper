"""Accountant exports reconcile without exposing transaction or profile data."""
import io
import unittest
from decimal import Decimal

from openpyxl import load_workbook
import reports
import server
import test_credits


class AccountantSummaryTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr,server,'PROFILE_PATH',server.PROFILE_PATH)
        self.fixture=test_credits.CreditReviewTests()
        self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.handler=self.fixture.handler
        self.handler.download=lambda data,name,kind:(data,name,kind)

    def export(self,query=''):
        self.handler.path='/api/export.xlsx'+query
        content,name,_=self.handler.export_excel()
        return load_workbook(io.BytesIO(content),data_only=True),name

    def test_default_export_is_a_summary_and_refunds_reconcile(self):
        self.fixture.apply({'ids':[self.fixture.ids['SUPPLIER REFUND']],'treatment':'refund','refundUsage':'business',
            'businessId':self.fixture.business,'category':'Office supplies','includeInTotals':True})
        workbook,name=self.export()
        self.addCleanup(workbook.close)
        self.assertEqual(name,'bookkeeper-accountant-summary.xlsx')
        self.assertEqual(workbook.sheetnames,['Accountant Summary','Monthly Summary'])
        summary=workbook['Accountant Summary'];monthly=workbook['Monthly Summary']
        self.assertEqual((summary['B6'].value,summary['B7'].value,summary['B8'].value),(72.95,20,52.95))
        self.assertEqual((summary['D14'].value,summary['E14'].value,summary['F14'].value,summary['G14'].value),(72.95,20,52.95,3))
        self.assertEqual((monthly['C6'].value,monthly['D6'].value,monthly['E6'].value),(72.95,20,52.95))
        all_values={str(cell.value) for tab in workbook for row in tab for cell in row}
        self.assertNotIn('SUPPLIER PURCHASE',all_values)
        self.assertTrue(all(tx not in all_values for tx in self.fixture.ids.values()))
        self.assertNotIn(reports.PROFILE_SHEET,workbook.sheetnames)
        self.assertTrue(all(tab.sheet_state=='visible' for tab in workbook))
        self.assertEqual(summary['B8'].data_type,'n')
        self.assertIn('A1:F1',{str(r) for r in monthly.merged_cells.ranges})
        self.assertIn('A2:F2',{str(r) for r in monthly.merged_cells.ranges})

    def test_business_and_year_filters_do_not_leak_other_business_on_same_account(self):
        with server.connect() as db:
            db.execute("INSERT INTO businesses(id,legal_name,display_name,created_at) VALUES('other','Other books','Other books',?)",(server.utc_now(),))
            db.execute("UPDATE transactions SET business_id='other' WHERE description='PLUS MEMBERSHIP'")
        self.fixture.import_csv('card',b'Date,Description,Debit,Credit\n10/01/2025,PREVIOUS YEAR PRIVATE,99.00,\n')
        workbook,_=self.export('?businessId='+self.fixture.business+'&year=2026')
        self.addCleanup(workbook.close)
        summary=workbook['Accountant Summary']
        self.assertEqual(summary['B8'].value,60)
        self.assertEqual(summary['B3'].value,'2026')
        self.assertNotIn('Other books',{cell.value for tab in workbook for row in tab for cell in row})

    def test_outside_groups_partition_all_rows_without_double_counting(self):
        with server.connect() as db:
            db.execute("UPDATE transactions SET classification='personal',business_id=NULL,excluded=1,include_in_totals=0 WHERE description='PLUS MEMBERSHIP'")
            rows=db.execute('SELECT t.*,b.display_name AS business_name FROM transactions t LEFT JOIN businesses b ON b.id=t.business_id').fetchall()
            result=reports.accountant_summary(rows,'All businesses','')
            self.assertEqual(result['includedCount'],1)
            self.assertEqual(result['netCents'],6000)
            self.assertEqual(result['includedCount']+sum(r[1] for r in result['outsideTotals']),len(rows))
            personal=next(r for r in result['outsideTotals'] if r[0]=='Personal activity')
            self.assertEqual(personal,['Personal activity',1,1295,0])
            self.assertEqual(sum(r[2] for r in result['outsideTotals'])+result['chargesCents'],sum(r['amount_cents'] for r in rows if r['direction']=='debit'))
            self.assertEqual(sum(r[3] for r in result['outsideTotals'])+result['refundsCents'],sum(r['amount_cents'] for r in rows if r['direction']=='credit'))

    def test_summary_rejects_embedded_profile_and_exports_empty_period(self):
        self.handler.path='/api/export.xlsx?portable=1'
        with self.assertRaisesRegex(ValueError,'never include a reusable profile'):self.handler.export_excel()
        workbook,_=self.export('?year=2020')
        self.addCleanup(workbook.close)
        self.assertEqual(workbook['Accountant Summary']['B8'].value,0)
        self.assertEqual(workbook['Monthly Summary']['A6'].value,'TOTAL')

    def test_older_personal_category_rows_never_inflate_expense_totals(self):
        with server.connect() as db:
            db.execute("UPDATE transactions SET category_name='Personal / non-business' WHERE description='PLUS MEMBERSHIP'")
            row=db.execute("SELECT * FROM transactions WHERE description='PLUS MEMBERSHIP'").fetchone()
            self.assertFalse(reports.included(row))
            self.assertEqual(row['include_in_totals'],1)  # Reporting does not rewrite saved decisions.
        workbook,_=self.export()
        self.addCleanup(workbook.close)
        self.assertEqual(workbook['Accountant Summary']['B8'].value,60)
