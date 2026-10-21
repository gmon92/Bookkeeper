"""Deterministic USD reports from reviewed SQLite transactions."""
import io
import json
import base64
import hashlib
import binascii
from collections import defaultdict
from decimal import Decimal
from credits import LABELS as CREDIT_LABELS

PROFILE_SHEET = '_Bookkeeper_Profile'
PROFILE_FORMAT = 'local-bookkeeper-workbook-profile'
MAX_PROFILE_BYTES = 64 * 1024 * 1024
PROFILE_CHUNK_SIZE = 30000


def add_profile(workbook, database, profile):
    if len(database)>MAX_PROFILE_BYTES:
        raise ValueError('This profile is too large for an embedded Excel copy. Export SQLite instead, or uncheck Include reusable profile to export the ledger alone.')
    encoded = base64.b64encode(database).decode('ascii')
    chunks = [encoded[i:i+PROFILE_CHUNK_SIZE] for i in range(0,len(encoded),PROFILE_CHUNK_SIZE)]
    manifest = {'format':PROFILE_FORMAT,'version':1,'bytes':len(database),'sha256':hashlib.sha256(database).hexdigest(),'chunks':len(chunks)}
    payload = workbook.create_sheet(PROFILE_SHEET)
    payload.append([PROFILE_FORMAT]); payload.append([json.dumps(manifest,sort_keys=True)])
    for index,chunk in enumerate(chunks):
        payload.append([index,chunk]); payload.cell(payload.max_row,2).data_type='s'
    payload.sheet_state='veryHidden'
    info = workbook.create_sheet('Profile Restore')
    for row in [
        ['Reusable Local Bookkeeper profile'],
        ['Scope','Full active profile, including ALL businesses and years; independent of the report filters.'],
        ['Profile name',safe_text(profile.get('name','My books'))],
        ['Transactions',profile.get('transactionCount',0)],['Saved rules',profile.get('ruleCount',0)],
        ['What is retained','Transactions, categorizations, credit decisions, account scopes, rules, categories, businesses, import layouts, preferences and original row archives.'],
        ['Resume','In Local Bookkeeper, open the profile chooser, choose Restore export / backup, select this Excel file, then choose a new empty destination.'],
        ['Original statement files','Use Download profile backup to also transfer the original statement files. Original rows remain inside this profile.'],
        ['Report edits','Editing report cells does not change the embedded profile snapshot. Export a fresh copy after making decisions in the app.'],
        ['Integrity','Restore validates the embedded database checksum and SQLite integrity before opening.'],
        ['Plain ledger','A report exported without reusable profile data cannot restore saved rules.'],
    ]: info.append(row)
    info.column_dimensions['A'].width=26; info.column_dimensions['B'].width=110
    from openpyxl.styles import Alignment, Font
    for row in info:
        for cell in row: cell.alignment=Alignment(wrap_text=True,vertical='top')
        info.row_dimensions[row[0].row].height=42
    info['A1'].font=Font(bold=True,size=15)


def read_profile(workbook):
    if PROFILE_SHEET not in workbook.sheetnames:
        raise ValueError('This Excel file does not contain a reusable profile. Export a new ledger with Include reusable profile checked, or open an exported SQLite database.')
    data = workbook[PROFILE_SHEET].iter_rows(values_only=True)
    if next(data,())[0:1] != (PROFILE_FORMAT,): raise ValueError('The workbook profile format is invalid.')
    try:
        manifest = json.loads(next(data)[0])
        if not isinstance(manifest,dict) or manifest.get('format')!=PROFILE_FORMAT or manifest.get('version')!=1: raise ValueError()
        size,count=manifest['bytes'],manifest['chunks']
        if type(size) is not int or not 0<size<=MAX_PROFILE_BYTES or type(count) is not int or not 0<count<=((MAX_PROFILE_BYTES*4//3+4)//PROFILE_CHUNK_SIZE+1): raise ValueError()
        parts=[]
        for index in range(count):
            row=next(data)
            if len(row)<2 or row[0]!=index or not isinstance(row[1],str) or len(row[1])>PROFILE_CHUNK_SIZE: raise ValueError()
            parts.append(row[1])
        if next(data,None) is not None: raise ValueError()
        content=base64.b64decode(''.join(parts),validate=True)
        if len(content)!=size or hashlib.sha256(content).hexdigest()!=manifest['sha256'] or not content.startswith(b'SQLite format 3\x00'): raise ValueError()
        return content
    except (ValueError,KeyError,TypeError,StopIteration,binascii.Error) as exc:
        raise ValueError('The reusable profile data is incomplete or its checksum does not match. Export another copy or use the SQLite database.') from exc


def safe_text(value):
    text = str(value or '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t','\r','\n')) else text


def included(row):
    return bool(row['include_in_totals'] and not row['excluded'] and row['status'] == 'approved' and row['classification'] == 'business' and not row['duplicate_of'] and ((row['direction'] == 'debit' and row['transaction_kind'] in {'expense','fee'}) or (row['direction'] == 'credit' and row['transaction_kind'] == 'refund')))


def expense_cents(row):
    return -row['amount_cents'] if row['direction'] == 'credit' else row['amount_cents']


def excel_report(rows, business_label, year, database=None, profile=None):
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
    if database is not None: add_profile(workbook,database,profile or {})
    output = io.BytesIO(); workbook.save(output)
    return output.getvalue()
