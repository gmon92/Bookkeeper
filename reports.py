"""Deterministic USD reports from reviewed SQLite transactions."""
import io
import json
from collections import defaultdict
from decimal import Decimal
from credits import LABELS as CREDIT_LABELS


def safe_text(value):
    text = str(value or '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t','\r','\n')) else text


def included(row):
    return bool(row['include_in_totals'] and not row['excluded'] and row['status'] == 'approved' and row['classification'] == 'business' and not row['duplicate_of'] and ((row['direction'] == 'debit' and row['transaction_kind'] in {'expense','fee'}) or (row['direction'] == 'credit' and row['transaction_kind'] == 'refund')))


def expense_cents(row):
    return -row['amount_cents'] if row['direction'] == 'credit' else row['amount_cents']


def excel_report(rows, business_label, year):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    workbook = Workbook()
    workbook.remove(workbook.active)
    headers = ['Date','Description','Business','Source account','Category','Expense USD','Amount USD','Direction','Kind','Classification','Review status','Included in totals','Source document','Source sheet','Source row','Transaction ID','Duplicate of','Notes','Credit decision','Related transaction ID']
    def ledger_row(row):
        raw = json.loads(row['source_raw_json'])
        return [row['date'],safe_text(row['description']),safe_text(row['business_name']),safe_text(row['nickname'] + (' ···· '+row['last_four'] if row['last_four'] else '')),safe_text(row['category_name']),Decimal(expense_cents(row))/100 if included(row) else None,Decimal(row['amount_cents'])/100,row['direction'],row['transaction_kind'],row['classification'],row['status'],bool(included(row)),safe_text(row['filename']),safe_text(raw.get('sheet')),row['source_row'],row['id'],row['duplicate_of'],safe_text(row['notes']),CREDIT_LABELS.get(row['credit_treatment'],'') if row['direction']=='credit' or row['credit_treatment'] else '',row['related_transaction_id']]
    def sheet(name, titles, records, money_columns=()):
        tab = workbook.create_sheet(name)
        tab.append([safe_text(business_label) + ' · ' + str(year or 'All years')])
        tab.append(['Bookkeeping and tax preparation assistance; review tax treatment with your preparer.'])
        tab.append(titles)
        for record in records: tab.append(record)
        tab.freeze_panes = 'A4'
        tab.auto_filter.ref = f'A3:{get_column_letter(len(titles))}{max(3,tab.max_row)}'
        for cell in tab[3]:
            cell.font = Font(bold=True, color='FFFFFF'); cell.fill = PatternFill('solid', fgColor='384D38')
        for column in range(1,len(titles)+1):
            tab.column_dimensions[get_column_letter(column)].width = min(52,max(16,len(titles[column-1])+3))
        for number in money_columns:
            for cells in tab.iter_rows(min_row=4,min_col=number,max_col=number): cells[0].number_format = '#,##0.00;[Red](#,##0.00)'
    ledger = [r for r in rows if included(r)]
    sheet('Expense Ledger',headers,[ledger_row(r) for r in ledger],(6,7))
    monthly, categories = defaultdict(int), defaultdict(int)
    for row in ledger:
        monthly[row['date'][:7]] += expense_cents(row)
        categories[row['category_name']] += expense_cents(row)
    sheet('Monthly Summary',['Month','Expense USD'],[[k,Decimal(v)/100] for k,v in sorted(monthly.items())],(2,))
    sheet('Category Summary',['Category','Expense USD'],[[safe_text(k),Decimal(v)/100] for k,v in sorted(categories.items())],(2,))
    sheet('Tax Preparation Summary',['Category','Reviewed expense USD','Review guidance'],[[safe_text(k),Decimal(v)/100,'Confirm business purpose and tax treatment. Vehicle, meals, loan and owner activity need separate review.'] for k,v in sorted(categories.items())],(2,))
    sheet('Review Queue',headers,[ledger_row(r) for r in rows if r['status'] in {'needs_review','suggested'}],(6,7))
    sheet('Excluded Transactions',headers,[ledger_row(r) for r in rows if not included(r)],(6,7))
    sheet('Duplicate-Transfer Transactions',headers,[ledger_row(r) for r in rows if r['duplicate_of'] or r['transaction_kind']=='transfer' or r['classification']=='transfer'],(6,7))
    output = io.BytesIO(); workbook.save(output)
    return output.getvalue()
