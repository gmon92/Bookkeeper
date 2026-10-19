"""Human-readable import evidence, built from the actual parser decisions."""
import hashlib
import json
import datetime as dt


def finish(parsed):
    extraction = parsed['extraction']
    extraction['provider'] = parsed['provider']
    extraction['parserVersion'] = parsed['parser_version']
    extraction['rowCount'] = len(parsed['rows'])
    extraction['rowSelection'] = 'Read nonempty rows after the detected header. Blank rows are skipped. Invalid amounts or dates are retained for review, not silently discarded.'
    extraction['categoryPolicy'] = 'A statement category is source evidence. Imports do not assign an approved business category or include expenses in totals.'
    if parsed['provider']=='American Express':
        extraction['amountPolicy'] = 'American Express layout: positive Amount values are card charges (debit); negative values are payments or credits (credit). Payment wording suggests a transfer; other credits require review.'
    elif 'amount' not in extraction['columns'] and ('debit' in extraction['columns'] or 'credit' in extraction['columns']):
        extraction['amountPolicy'] = 'The populated Debit/Withdrawal or Credit/Deposit column determines money movement. Both columns populated is a conflict and remains unknown.'
    else:
        extraction['amountPolicy'] = 'Amount preserves its original sign. A recognized Type value determines debit or credit. A numeric sign alone does not establish direction; ambiguous rows stay unknown.'
    signature = {'format':parsed['format'],'provider':parsed['provider'],'parserVersion':parsed['parser_version'],
                 'columns':extraction['columns'],'headers':parsed['headers'],'sheet':extraction.get('sheet')}
    parsed['layout_key'] = hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    extraction['layoutKey'] = parsed['layout_key']
    extraction['datePolicy'] = 'ISO dates are accepted. Numeric month/day/year is attempted before day/month/year; confirm ambiguous dates in the preview.'
    for tx in parsed['rows']:
        raw = tx['raw']; values = raw['values']; columns = extraction['columns']
        def source(key):
            column = columns.get(key)
            return str(values[column['index']]) if column and column['index']<len(values) else ''
        if parsed['provider']=='American Express':
            movement = ('Negative' if tx['source_amount_cents']<0 else 'Nonnegative')+' Amount interpreted as '+tx['direction']+' under the confirmed American Express convention.'
        elif 'amount' not in columns:
            movement = 'Debit and Credit source columns were inspected; resulting direction is '+tx['direction']+'.'
        else:
            movement = ('Source Type “'+source('type')+'” maps to '+tx['direction']+'.') if tx['direction']!='unknown' else 'No trusted direction mapping was found. Review this row; the amount sign alone was not used.'
        location = (str(extraction.get('sheet'))+' · ' if extraction.get('sheet') else '')+'row '+str(tx['source_row'])
        try: dt.date.fromisoformat(tx['date']); valid_date = True
        except ValueError: valid_date = False
        raw['evidence'] = {
            'location':location,'dateSource':source('date'),'descriptionSource':source('description'),
            'amountSource':tx['raw_amount_text'],'sourceCents':tx['source_amount_cents'],'normalizedCents':tx['amount_cents'],
            'dateReason':'Read '+(columns.get('date',{}).get('header') or 'no recognized date column')+' → '+(tx['date'] or 'missing date')+('.' if valid_date else '; invalid or missing date requires review.'),
            'amountReason':'Read original amount “'+tx['raw_amount_text']+'”; retained source cents '+str(tx['source_amount_cents'])+' and a separate magnitude of '+str(tx['amount_cents'])+' USD cents. Zero or unreadable amounts require review.',
            'directionReason':movement,
            'kindReason':('Provider payment wording suggests a transfer.' if parsed['provider']=='American Express' and tx['transaction_kind']=='transfer' else
                'Parsed kind is '+tx['transaction_kind']+'. '+('A money-out row is a draft expense; confirm business purpose.' if tx['transaction_kind']=='expense' else 'This remains subject to review.')),
            'categoryReason':'No business category was assigned by import.'+(' Statement category “'+source('sourceCategory')+'” was retained as evidence.' if source('sourceCategory') else ''),
        }
    return parsed
