"""Text-based Chase checking statements with running-balance reconciliation."""
import csv
import datetime as dt
import hashlib
import io
import re
from decimal import Decimal, InvalidOperation

from import_evidence import finish

MAX_PAGES = 100
MAX_LINES = 100000
MONEY = r'(?:-?\$?[\d,]+\.\d{2}|\(\$?[\d,]+\.\d{2}\))'
TRANSACTION = re.compile(r'^(\d{2}/\d{2})\s+(.+?)\s+('+MONEY+r')\s+('+MONEY+r')$')
PERIOD = re.compile(r'([A-Za-z]+\s+\d{1,2},\s*\d{4})\s*through\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})',re.I)


def extract_pages(content):
    if not content.lstrip().startswith(b'%PDF-'):raise ValueError('This is not a readable PDF statement.')
    try:import pdfplumber
    except ImportError as exc:raise ValueError('PDF import needs pdfplumber. Run python -m pip install -r requirements.txt.') from exc
    result=[];line_count=text_bytes=0
    try:
        with pdfplumber.open(io.BytesIO(content)) as document:
            if not 0<len(document.pages)<=MAX_PAGES:raise ValueError('Choose a PDF statement with 1 to 100 pages.')
            for number,page in enumerate(document.pages,1):
                # Chase includes invisible one-point *start*/*end* routing text.
                # Its visible Type 3 glyphs can report size 0.24, so filtering
                # all small glyphs would discard the actual financial table.
                clean=page.filter(lambda obj:obj.get('object_type')!='char' or
                    (obj.get('upright',True) and abs(obj.get('size',0)-1)>0.05))
                words=sorted(clean.extract_words(x_tolerance=2,y_tolerance=2),key=lambda w:(w['top'],w['x0']))
                groups=[]
                for word in words:
                    if not groups or abs(word['top']-groups[-1][0]['top'])>2:groups.append([])
                    groups[-1].append(word)
                lines=[]
                for index,group in enumerate(groups,1):
                    group=sorted(group,key=lambda w:w['x0'])
                    text=' '.join(w['text'] for w in group)
                    lines.append({'number':index,'text':text,'top':min(w['top'] for w in group),
                        'x0':min(w['x0'] for w in group),'words':group})
                    text_bytes+=len(text.encode('utf-8'))
                line_count+=len(lines)
                if line_count>MAX_LINES or text_bytes>20*1024*1024:raise ValueError('Extracted PDF text exceeds the import limits. Split the statement.')
                result.append({'number':number,'width':page.width,'height':page.height,'lines':lines})
    except ValueError:raise
    except Exception as exc:raise ValueError('The PDF could not be read. Use an unlocked, text-based statement or export CSV/XLSX from the bank.') from exc
    if not any(page['lines'] for page in result):raise ValueError('This PDF has no readable text. Scanned/image-only PDFs need OCR; use a text-based PDF or CSV/XLSX export.')
    return result


def cents(value):
    value=value.strip().replace('$','').replace(',','')
    if value.startswith('(') and value.endswith(')'):value='-'+value[1:-1]
    try:
        amount=Decimal(value)
        if not amount.is_finite() or amount*100!=(amount*100).to_integral_value() or abs(amount)>Decimal('9999999999.99'):raise ValueError()
        return int(amount*100)
    except (ValueError,InvalidOperation) as exc:raise ValueError('Unreadable amount in PDF statement.') from exc


def statement_date(value,start,end):
    candidates=[]
    for year in range(start.year,end.year+1):
        try:day=dt.datetime.strptime(str(year)+'/'+value,'%Y/%m/%d').date()
        except ValueError:continue
        if start<=day<=end:candidates.append(day)
    if len(candidates)!=1:raise ValueError('A transaction date is outside the statement period or has an ambiguous year.')
    return candidates[0].isoformat()


def parse_pdf(content,filename,csv_parser):
    pages=extract_pages(content)
    text='\n'.join(line['text'] for page in pages for line in page['lines'])
    if 'JPMorgan Chase Bank' not in text or 'CHECKING SUMMARY' not in text:
        raise ValueError('This PDF layout is not supported yet. PDF import currently supports text-based Chase checking statements with DATE, DESCRIPTION, AMOUNT and BALANCE columns. Use CSV/XLSX for other banks or layouts.')
    periods={match.groups() for match in PERIOD.finditer(text)}
    if len(periods)!=1:raise ValueError('The PDF must contain one consistent statement period and one account.')
    first,last=next(iter(periods))
    try:start,end=[dt.datetime.strptime(re.sub(r'\s+',' ',v),'%B %d, %Y').date() for v in (first,last)]
    except ValueError as exc:raise ValueError('Could not read the PDF statement period.') from exc
    if not 0<=(end-start).days<=62:raise ValueError('Choose one monthly Chase checking statement, covering at most 62 days.')
    accounts={w['text'] for page in pages for line in page['lines'] if line['top']<page['height']*.18
        for w in line['words'] if w['x0']>page['width']*.55 and re.fullmatch(r'\d{9,20}',w['text'])}
    if len(accounts)!=1:raise ValueError('Could not identify a single account in the PDF header. Use one account statement.')
    last_four=next(iter(accounts))[-4:]
    summary={};in_summary=False
    for page in pages:
        for line in page['lines']:
            value=line['text']
            if value=='CHECKING SUMMARY':in_summary=True;continue
            if not in_summary:continue
            match=re.fullmatch(r'(.+?)\s+('+MONEY+r')',value)
            if not match:continue
            label=match[1].strip();amount=cents(match[2])
            if label in summary:raise ValueError('Multiple checking summaries were found; choose a single account statement.')
            summary[label]=amount
            if label=='Ending Balance':in_summary=False
    if 'Beginning Balance' not in summary or 'Ending Balance' not in summary:
        raise ValueError('The beginning and ending balances are required to validate this PDF.')
    credit_labels={'Deposits and Additions','Deposits and Other Additions','Deposits and Credits'}
    debit_labels={'Electronic Withdrawals','ATM & Debit Card Withdrawals','Fees','Checks Paid','Other Withdrawals'}
    if set(summary)-credit_labels-debit_labels-{'Beginning Balance','Ending Balance'}:
        raise ValueError('An unsupported checking-summary section was found. Use CSV/XLSX so no activity is skipped.')
    records=[];balance=summary['Beginning Balance'];ending_seen=False
    for page in pages:
        active=False;description_x=None
        for line in page['lines']:
            value=line['text']
            if re.fullmatch(r'DATE\s+DESCRIPTION\s+AMOUNT\s+BALANCE',value):
                active=True
                description_x=next(w['x0'] for w in line['words'] if w['text']=='DESCRIPTION')
                continue
            if not active or line['top']>page['height']-40:continue
            if value.startswith('Beginning Balance'):
                if records or cents(value.split('Balance',1)[1])!=balance:raise ValueError('The transaction opening balance does not match the summary.')
                continue
            if value.startswith('Ending Balance'):
                if cents(value.split('Balance',1)[1])!=balance:raise ValueError('The transaction closing balance does not reconcile.')
                active=False;ending_seen=True;continue
            if ending_seen:raise ValueError('Unexpected second transaction table after the closing balance.')
            match=TRANSACTION.fullmatch(value)
            if match:
                date_text,description,amount_text,balance_text=match.groups()
                amount,next_balance=cents(amount_text),cents(balance_text)
                if balance+amount!=next_balance:raise ValueError('PDF transaction running balance mismatch on page '+str(page['number'])+', line '+str(line['number'])+'. Import stopped; use CSV/XLSX if the layout differs.')
                day=statement_date(date_text,start,end)
                if records and day<records[-1]['date']:raise ValueError('PDF transaction dates are not in chronological order.')
                records.append({'date':day,'dateText':date_text,'description':description,'amountText':amount_text,
                    'amount':amount,'balanceText':balance_text,'balance':next_balance,'page':page['number'],'line':line['number'],'text':value})
                balance=next_balance
                if len(records)>50000:raise ValueError('PDF exceeds the 50,000 transaction limit.')
            elif re.match(r'^\d{1,2}/\d{1,2}\b',value):
                raise ValueError('A dated PDF row could not be read on page '+str(page['number'])+'. Import stopped instead of skipping it.')
            elif records and line['x0']>=description_x-3 and not re.search(MONEY,value):
                records[-1]['description']+=' '+value
            else:
                raise ValueError('Unexpected text inside the PDF transaction table on page '+str(page['number'])+'. Use CSV/XLSX for this layout.')
    expected_credit=sum(abs(summary.get(label,0)) for label in credit_labels)
    expected_debit=sum(abs(summary.get(label,0)) for label in debit_labels)
    actual_credit=sum(r['amount'] for r in records if r['amount']>0)
    actual_debit=-sum(r['amount'] for r in records if r['amount']<0)
    if not records or not ending_seen or balance!=summary['Ending Balance'] or actual_credit!=expected_credit or actual_debit!=expected_debit or summary['Beginning Balance']+actual_credit-actual_debit!=balance:
        raise ValueError('Extracted PDF activity does not reconcile to its statement totals and closing balance. Import stopped.')
    output=io.StringIO(newline='');writer=csv.writer(output)
    writer.writerow(['Date','Description','Amount','Balance'])
    for r in records:writer.writerow([r['date'],r['description'],r['amountText'],r['balanceText']])
    parsed=csv_parser(output.getvalue().encode('utf-8'),filename)
    parsed.update(format='pdf',provider='Chase checking',parser_version='chase-checking-pdf-v1',
        reconciliation={'matched':True,'expectedCents':{'deposits':expected_credit,'withdrawals':expected_debit,'endingBalance':balance},
            'actualCents':{'deposits':actual_credit,'withdrawals':actual_debit,'endingBalance':balance},'beginningBalanceCents':summary['Beginning Balance']})
    parsed['extraction'].update(sheet=None,pageCount=len(pages),accountLastFour=last_four,
        statementStart=start.isoformat(),statementEnd=end.isoformat(),
        rowSelection='Read only the Chase TRANSACTION DETAIL tables. Summary, beginning/ending balance rows, notices and footer text are not transactions. Every running balance and both gross totals reconcile.',
        pdfTextPolicy='Text-based extraction with page and line references (no OCR). Non-transaction routing markers and barcode text are ignored; the original PDF is retained.')
    for tx,r in zip(parsed['rows'],records):
        tx.update(source_page=r['page'],source_row=r['line'],direction='credit' if r['amount']>0 else 'debit' if r['amount']<0 else 'unknown')
        card_payment=bool(re.search(r'Payment To Chase Card|Chase Credit Crd Auto|American Express ACH Pmt|Capital One (?:Crcardpmt|Mobile Pmt)',r['description'],re.I))
        tx['transaction_kind']='transfer' if card_payment and tx['direction']=='debit' else 'expense' if tx['direction']=='debit' else 'unknown'
        tx['raw'].update(values=[r['dateText'],r['description'],r['amountText'],r['balanceText']],sheet='Page '+str(r['page']),
            pdfPage=r['page'],pdfLine=r['line'],pdfText=r['text'],balanceCents=r['balance'])
        key='|'.join((tx['date'],'',str(tx['amount_cents']),tx['direction'],''.join(c for c in tx['description'].lower() if c.isalnum())))
        tx['fingerprint']=hashlib.sha256(key.encode()).hexdigest()
    return finish(parsed)
