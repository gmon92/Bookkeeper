"""Local, read-only review groups and evidence-backed credit comparisons."""
from collections import defaultdict
from datetime import date
import hashlib
import re

import automation
import consistency
import credits
from categorization import merchant_text


MAX_BATCH_ROWS = 5000
MAX_PAIR_CANDIDATES = 3
SERVICES = (
    (r'\b(?:green clean|tiger wash|car lovers|all american car was\w*)\b', 'cleaning', 'Vehicle cleaning',
     'Cleaning / detailing', 'Were these washes for a vehicle used by the business? Leave out any personal vehicle washes.'),
    (r'\b(?:donotpay|do not pay)\b', 'donotpay', 'DoNotPay', 'Subscriptions',
     'Was this service used for the business or personally?'),
    (r'\b(?:goodrx|goodrxgold)\b', 'goodrx', 'GoodRx', '',
     'Were these personal health costs, or is there a documented business purpose?'),
    (r'\bamazon onemed\b', 'onemed', 'One Medical', '',
     'Was this a personal health membership, or is there a documented business purpose? Check the invoice before choosing a category.'),
    (r'\b(?:youtube|youtu\d*)\b', 'youtube', 'YouTube', 'Subscriptions',
     'Which YouTube product was purchased, and was it used for business?'),
    (r'\baudible\b', 'audible', 'Audible', 'Subscriptions',
     'Were these books or listening services used for business learning or personally?'),
    (r'\bscribd\b', 'scribd', 'Scribd', 'Subscriptions',
     'Was this subscription used for business research or personal reading?'),
    (r'\badobe\b', 'adobe', 'Adobe', 'Subscriptions',
     'Was this subscription used for the business? Check any refunds separately.'),
)
VEHICLE = re.compile(r'\b(?:mavis\d*|settle tire|advance auto|autozone|rockautollc|rockauto|harry a wrights)\b')
RETAIL = re.compile(r'\b(?:amazon|ikeanortham|ikea|big lots|lowes|lowe s|home depot|ebay|woot|b h photo|walmart|tiktok|wolverine|ctshirts)\b')


def pending(row):
    return (row['status'] in ('needs_review', 'suggested') and not row['excluded']
            and not row['duplicate_of'] and not row['related_transaction_id']
            and not consistency.transaction_issue(row))


def merchant_family(row):
    text = merchant_text(row['merchant'] or row['description'])
    for pattern, family in ((r'\bamazon\b', 'amazon'), (r'\bmavis\d*\b', 'mavis'),
                            (r'\badvance auto\b', 'advance-auto'), (r'\badobe\b', 'adobe'),
                            (r'\bclear\b', 'clear')):
        if re.search(pattern, text):
            # One Medical is a different service from Amazon retail orders.
            return 'one-medical' if family == 'amazon' and 'onemed' in text else family
    text = re.sub(r'^(?:aplpay|paypal|pwp)\s+', '', text)
    return re.sub(r'\b\d{4,}\b', '', text).strip()


def identity(*parts):
    return hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:20]


def overview(db):
    rows = [dict(row) for row in automation.rows(db)]
    by_fingerprint = defaultdict(list)
    for row in rows:
        by_fingerprint[(row['account_id'], row['source_fingerprint'])].append(row['id'])
    distinct = {frozenset((row['first_id'], row['second_id'])) for row in
                db.execute("SELECT first_id,second_id FROM duplicate_decisions WHERE decision='distinct'")}

    def duplicate_candidate(row):
        return any(other != row['id'] and frozenset((row['id'], other)) not in distinct
            for other in by_fingerprint[(row['account_id'], row['source_fingerprint'])])

    def eligible(row):
        return pending(row) and not duplicate_candidate(row)

    debits = defaultdict(list)
    for row in rows:
        if (row['direction'] == 'debit' and not row['duplicate_of'] and not row['excluded']
                and row['transaction_kind'] in ('expense', 'fee', 'unknown')
                and not row['related_transaction_id'] and not row['credit_treatment'] and not duplicate_candidate(row)):
            debits[row['account_id']].append(row)

    pairs, reserved, credit_groups = [], set(), defaultdict(list)
    saved_credit_rules = credits.rules(db)
    for credit in rows:
        if credit['direction'] != 'credit' or not eligible(credit):
            continue
        suggestion = credits.suggestion(credit, saved_credit_rules)
        treatment = suggestion.get('treatment') if suggestion and not suggestion.get('conflict') else None
        if treatment in ('payment', 'statement_credit', 'excluded_credit'):
            credit_groups[(credit['account_id'], credit['business_id'], treatment)].append(credit)
            continue
        text = merchant_text(credit['merchant'] or credit['description'])
        points = bool(re.search(r'\bpoints for amex trvl\b', text))
        family = merchant_family(credit)
        candidates = []
        for purchase in debits[credit['account_id']]:
            try:
                days = (date.fromisoformat(credit['date']) - date.fromisoformat(purchase['date'])).days
            except ValueError:
                continue
            if not 0 <= days <= (3 if points else 365) or purchase['amount_cents'] < credit['amount_cents']:
                continue
            if credit['business_id'] and purchase['business_id'] and credit['business_id'] != purchase['business_id']:
                continue
            if points:
                travel = merchant_text(purchase['merchant'] or purchase['description'])
                if purchase['amount_cents'] != credit['amount_cents'] or not travel.startswith('pwp '):
                    continue
            elif merchant_family(purchase) != family:
                continue
            exact = purchase['amount_cents'] == credit['amount_cents']
            candidates.append((not exact, days, purchase['id'], purchase))
        candidates.sort(key=lambda item: item[:3])
        if candidates and not candidates[0][0]:
            candidates = [item for item in candidates if not item[0]]
        if candidates:
            offset = points or family == 'clear'
            visible = candidates[:MAX_PAIR_CANDIDATES]
            pairs.append({'id': identity('pair', credit['id']), 'creditId': credit['id'],
                'candidateIds': [item[2] for item in visible], 'candidateCount': len(candidates),
                'kind': 'offset' if offset else 'refund',
                'question': 'Is this a rewards redemption, a card benefit, or a merchant refund?' if offset else
                            'Does this credit refund one of these purchases, and does it belong in business books?',
                'reason': ('Travel booked with points has an equal charge close to the credit date.' if points else
                           'The merchant and amount match an earlier charge.' if not candidates[0][0] else
                           'The merchant matches an earlier, larger charge; this could be a partial refund.')})
            reserved.update(item[2] for item in candidates)
        else:
            credit_groups[(credit['account_id'], credit['business_id'], 'unclear')].append(credit)

    grouped = defaultdict(list)
    specs = {}
    for row in rows:
        if (row['direction'] != 'debit' or not eligible(row) or row['id'] in reserved
                or row['classification'] in ('personal', 'transfer') or row['transaction_kind'] not in ('expense', 'fee')):
            continue
        text = merchant_text(row['merchant'] or row['description'])
        if re.search(r'\b(?:amex send|add money|autopay|payment)\b', text):
            continue
        spec = None
        for pattern, family, title, category, question in SERVICES:
            if re.search(pattern, text):
                spec = (family, title, category, question, 'Similar service descriptions; confirm their purpose together.', 0)
                break
        if spec is None and VEHICLE.search(text):
            spec = ('vehicle', 'Vehicle services and parts', '',
                    'Which vehicle and work do these receipts cover? Choose maintenance, tires, or personal use as appropriate.',
                    'Vehicle-service merchants; invoices determine the category and business use.', 1)
        if spec is None and RETAIL.search(text):
            spec = ('receipts', 'Purchases needing receipts', '',
                    'What was purchased, and which items are business supplies, equipment, or personal purchases?',
                    'General retailers do not identify the purchased items. Choose a subset after checking receipts.', 3)
        if spec is None:
            # Unknown merchants stay separate; equal repeat amounts are a clue, not a category decision.
            family = merchant_family(row)
            spec = ('repeat:' + family + ':' + str(row['amount_cents']), ' '.join((row['merchant'] or row['description']).split()), '',
                    'Were these repeated charges for the same purpose, and was that purpose business or personal?',
                    'The same merchant description and amount repeat on different dates.', 2)
        family, title, category, question, reason, priority = spec
        key = (family, row['account_id'], row['business_id'])
        grouped[key].append(row)
        specs[key] = (title, category, question, reason, priority)

    groups = []

    def add_group(key, members, title, category, question, reason, priority, kind='charges', treatment=None):
        members.sort(key=lambda row: (row['date'], row['id']))
        for offset in range(0, len(members), MAX_BATCH_ROWS):
            selected = members[offset:offset + MAX_BATCH_ROWS]
            groups.append({'id': identity('group', *key, offset), 'kind': kind, 'title': title,
                'ids': [row['id'] for row in selected], 'accountId': selected[0]['account_id'],
                'businessId': selected[0]['business_id'], 'category': category, 'question': question,
                'reason': reason, 'priority': priority, 'treatment': treatment,
                'part': offset // MAX_BATCH_ROWS + 1, 'parts': (len(members) + MAX_BATCH_ROWS - 1) // MAX_BATCH_ROWS})

    for key, members in grouped.items():
        title, category, question, reason, priority = specs[key]
        if len(members) < 2 or (key[0].startswith('repeat:') and len({row['date'] for row in members}) < 2):
            continue
        add_group(key, members, title, category, question, reason, priority)
    for key, members in credit_groups.items():
        treatment = key[2]
        title, question = {
            'payment': ('Possible card payments', 'Are these payments between your own accounts?'),
            'statement_credit': ('Possible statement benefits', 'Are these card benefits rather than purchase refunds?'),
            'excluded_credit': ('Credits outside business books', 'Should these credits remain outside business books?'),
            'unclear': ('Credits needing a decision', 'Are these refunds, account benefits, payments, or another kind of credit?'),
        }[treatment]
        add_group(key, members, title, '', question, 'Review money-in decisions separately from purchase categories.',
                  1, kind='credits', treatment=None if treatment == 'unclear' else treatment)
    groups.sort(key=lambda group: (group['priority'], -len(group['ids']), group['title'], group['id']))
    return {'groups': groups, 'pairs': pairs}
