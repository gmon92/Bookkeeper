"""Synthetic Chase PDFs exercise extraction, reconciliation and retained evidence."""
import hashlib
import base64
import io
import json
import time
import unittest

from reportlab.pdfgen import canvas
from reportlab.lib.pdfencrypt import StandardEncryption

import server
import source_archive
import test_credits


def statement_pdf(*, amount='200.00', deposit_total='300.00', second_page=True, continuation=False,
        bad_date=False, broken_row=False, other_account=False, encrypted=False, scanned=False):
    output=io.BytesIO()
    pdf=canvas.Canvas(output,pagesize=(612,792),encrypt=StandardEncryption('test-only-password') if encrypted else None)
    def header(account='000000001234'):
        pdf.setFont('Helvetica',10)
        pdf.drawString(35,756,'JPMorgan Chase Bank, N.A.')
        pdf.drawString(35,740,'December 24, 2024 through January 24, 2025')
        pdf.drawString(340,720,'Account Number:')
        pdf.drawString(440,720,account)
    def line(y,day,description,amount,balance):
        pdf.drawString(35,y,day);pdf.drawString(80,y,description)
        pdf.drawRightString(463,y,amount);pdf.drawRightString(540,y,balance)
    def table(y):
        pdf.drawString(35,y,'TRANSACTION DETAIL')
        pdf.drawString(35,y-20,'DATE');pdf.drawString(80,y-20,'DESCRIPTION')
        pdf.drawRightString(463,y-20,'AMOUNT');pdf.drawRightString(540,y-20,'BALANCE')
    if not scanned:
        header()
        pdf.drawString(35,680,'CHECKING SUMMARY')
        for y,label,value in [(660,'Beginning Balance','1,000.00'),(645,'Deposits and Additions',deposit_total),
                (630,'Electronic Withdrawals','-150.00'),(615,'Ending Balance','1,150.00')]:
            pdf.drawString(35,y,label);pdf.drawRightString(450,y,value)
        table(570)
        pdf.drawString(80,535,'Beginning Balance');pdf.drawRightString(540,535,'1,000.00')
        line(520,'02/24' if bad_date else '12/24','DEPOSIT ONE',amount,'1,200.00')
        if continuation:pdf.drawString(80,513,'ADDITIONAL MERCHANT DETAILS')
        line(505,'12/30','Payment To Chase Card Ending IN 4321','unreadable' if broken_row else '-100.00','1,100.00')
        pdf.setFont('Helvetica',1);pdf.drawString(35,506,'*end*transaction detail');pdf.setFont('Helvetica',10)
        if second_page:
            pdf.showPage();header('000000005678' if other_account else '000000001234');table(675)
            line(630,'01/02','DEPOSIT TWO','100.00','1,200.00')
            line(615,'01/03','UTILITY BILL','-50.00','1,150.00')
            pdf.drawString(80,595,'Ending Balance');pdf.drawRightString(540,595,'1,150.00')
            pdf.drawString(35,560,'Your other electronic deposits this period were $9,999.99. This is not a transaction.')
            pdf.drawString(35,540,'01/20 A dated disclosure outside the table 800.00 8,000.00')
    pdf.save()
    return output.getvalue()


class PdfParsingTests(unittest.TestCase):
    def parse(self,**options):return server.parse_statement(statement_pdf(**options),'synthetic.pdf',server.parse_csv)

    def test_year_rollover_amount_signs_continued_pages_and_payment_kind(self):
        parsed=self.parse()
        self.assertEqual((parsed['format'],parsed['provider']),('pdf','Chase checking'))
        rows=parsed['rows'];self.assertEqual(len(rows),4)
        self.assertEqual([r['date'] for r in rows],['2024-12-24','2024-12-30','2025-01-02','2025-01-03'])
        self.assertEqual([r['direction'] for r in rows],['credit','debit','credit','debit'])
        self.assertEqual(rows[1]['transaction_kind'],'transfer')
        self.assertEqual(rows[0]['transaction_kind'],'unknown')
        self.assertEqual(rows[1]['source_amount_cents'],-10000)
        self.assertEqual(rows[1]['amount_cents'],10000)
        self.assertEqual(rows[2]['source_page'],2)
        self.assertEqual(rows[2]['raw']['sheet'],'Page 2')
        self.assertIn('PDF page 2',rows[2]['raw']['evidence']['location'])
        self.assertIn('bank deposit',rows[0]['raw']['evidence']['directionReason'])
        self.assertEqual(parsed['extraction']['accountLastFour'],'1234')
        self.assertEqual(parsed['extraction']['format'],'pdf')
        self.assertEqual(parsed['reconciliation']['actualCents'],{'deposits':30000,'withdrawals':15000,'endingBalance':115000})
        self.assertEqual(parsed['warnings']['total'],0)

    def test_bad_balances_totals_dates_missing_pages_and_unreadable_rows_stop_import(self):
        for options,message in [({'amount':'201.00'},'running balance'),({'deposit_total':'301.00'},'reconcile'),
                ({'second_page':False},'reconcile'),({'bad_date':True},'outside the statement period'),
                ({'broken_row':True},'dated PDF row'),({'other_account':True},'single account')]:
            with self.subTest(options=options),self.assertRaisesRegex(ValueError,message):self.parse(**options)

    def test_scanned_locked_malformed_and_unsupported_pdfs_are_readable_errors(self):
        for options in ({'scanned':True},{'encrypted':True}):
            with self.subTest(options=options),self.assertRaises(ValueError):self.parse(**options)
        with self.assertRaisesRegex(ValueError,'readable PDF'):server.parse_statement(b'not a PDF','bad.pdf',server.parse_csv)
        data=io.BytesIO();pdf=canvas.Canvas(data);pdf.drawString(50,700,'Another bank statement');pdf.save()
        with self.assertRaisesRegex(ValueError,'not supported'):server.parse_statement(data.getvalue(),'other.pdf',server.parse_csv)

    def test_wrapped_description_is_retained_without_creating_an_extra_row(self):
        parsed=self.parse(continuation=True)
        self.assertEqual(len(parsed['rows']),4)
        self.assertEqual(parsed['rows'][0]['description'],'DEPOSIT ONE ADDITIONAL MERCHANT DETAILS')


class PdfCommitTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr,server,'PROFILE_PATH',server.PROFILE_PATH)
        self.fixture=test_credits.CreditReviewTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.content=statement_pdf();self.parsed=server.parse_statement(self.content,'synthetic.pdf',server.parse_csv)
        with server.connect() as db:
            db.execute("INSERT INTO accounts(id,nickname,last_four,account_type) VALUES('checking','Test checking','1234','checking')")
            db.execute("INSERT INTO accounts(id,nickname,last_four) VALUES('wrong','Other account','9999')")
            db.execute("INSERT INTO accounts(id,nickname,last_four,account_type) VALUES('credit','Credit card','1234','credit')")
            db.execute('INSERT INTO staged_imports VALUES(?,?,?,?,?)',('pdf-token',self.content,json.dumps(self.parsed),hashlib.sha256(self.content).hexdigest(),time.time()))

    def commit(self,**changes):
        body={'token':'pdf-token','accountId':'checking','confirmExtraction':True,'confirmMapping':True}|changes
        self.fixture.handler.read_json=lambda:body
        return self.fixture.handler.commit_import()

    def test_commit_keeps_pdf_and_page_line_evidence_with_no_implicit_approval(self):
        status,result=self.commit();self.assertEqual(status,201)
        with server.connect() as db:
            rows=db.execute('SELECT * FROM transactions WHERE document_id=? ORDER BY date',(result['documentId'],)).fetchall()
            self.assertEqual(len(rows),4)
            self.assertTrue(all(r['status']=='needs_review' and not r['include_in_totals'] and r['business_id'] is None for r in rows))
            self.assertEqual([r['source_page'] for r in rows],[1,1,2,2])
            original=source_archive.original(db,rows[-1]['id'])
            self.assertEqual(original['raw']['balanceCents'],115000)
            self.assertEqual(original['raw']['pdfPage'],2)
            self.assertEqual(original['raw']['values'][2],'-50.00')
            archive=source_archive.document_rows(db,result['documentId'],'Page 2',0)
            self.assertEqual(archive['sheets'][0]['kind'],'pdf_text')
            self.assertTrue(any('UTILITY BILL' in r['cells'][0]['value'] for r in archive['rows']))
            path=self.fixture.root/db.execute('SELECT stored_path FROM documents WHERE id=?',(result['documentId'],)).fetchone()[0]
            self.assertEqual(path.read_bytes(),self.content)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())

    def test_preview_shows_reconciled_totals_and_page_references_without_importing(self):
        handler=self.fixture.handler
        handler.local_request=lambda:True
        handler.headers={'X-Bookkeeper-Workspace':server.WORKSPACE_ID}
        handler.path='/api/imports/preview'
        handler.read_json=lambda:{'filename':'synthetic.pdf','contentBase64':base64.b64encode(self.content).decode()}
        status,result=handler.post_request()
        self.assertEqual(status,200)
        self.assertEqual((result['rowCount'],result['creditCents'],result['debitCents']),(4,30000,15000))
        self.assertTrue(result['requiresMappingConfirmation'])
        self.assertTrue(result['reconciliation']['matched'])
        self.assertEqual([r['sourcePage'] for r in result['rows']],[1,1,2,2])
        with server.connect() as db:
            self.assertFalse(db.execute("SELECT 1 FROM documents WHERE filename='synthetic.pdf'").fetchone())

    def test_wrong_account_and_missing_confirmations_save_nothing(self):
        for changes in ({'accountId':'wrong'},{'accountId':'credit'},{'confirmMapping':False},{'confirmExtraction':False}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.commit(**changes)
            with server.connect() as db:
                self.assertFalse(db.execute("SELECT 1 FROM documents WHERE filename='synthetic.pdf'").fetchone())
                self.assertIsNotNone(db.execute("SELECT 1 FROM staged_imports WHERE token='pdf-token'").fetchone())


if __name__=='__main__':unittest.main()
