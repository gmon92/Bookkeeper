"""Deterministic import automation, explicit rule settings and reversible decisions."""
import hashlib
import json
import re
import uuid
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from functools import lru_cache

import source_archive
import consistency

MODES = ('suggest', 'categorize', 'review')
MAX_RULE_PHRASES = 200
MAX_SOURCE_CATEGORIES = 200


def initialize(db):
    for table in ('merchant_rules', 'credit_rules'):
        columns = {r['name'] for r in db.execute('PRAGMA table_info('+table+')')}
        for name, definition in (
            ('conditions_json', "TEXT NOT NULL DEFAULT '{}'"),
            ('automation_mode', "TEXT NOT NULL DEFAULT 'suggest'"),
            ('include_expenses', 'INTEGER NOT NULL DEFAULT 0 CHECK(include_expenses IN (0,1))'),
        ):
            if name not in columns: db.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+definition)


def text(value):
    from categorization import merchant_text
    return merchant_text(value)


def personal_category(name):
    return text(name) == text('Personal / non-business')


@lru_cache(maxsize=4096)
def merchant_expression(phrase):
    normalized=text(phrase)
    if not normalized:return None
    # Keep explicit store numbers exact; only a name may gain a numeric suffix.
    suffix=r'(?:\d+)?' if normalized[-1].isalpha() else ''
    return re.compile(r'(?<!\w)'+r'\s*'.join(re.escape(word) for word in normalized.split())+suffix+r'(?!\w)')


def conditions(rule):
    return json.loads(rule.get('conditions_json', '{}'))


def source_categories(rule):
    c = conditions(rule)
    return c.get('sourceCategories', [c['sourceCategory']] if c.get('sourceCategory') else [])


def source_category(row):
    if 'original_source_category' in row.keys(): return row['original_source_category'] or ''
    return source_archive.category(json.loads(row['source_raw_json']))


def matches(row, rule):
    c = conditions(rule)
    movement = c.get('direction', 'credit' if rule.get('treatment') else 'debit')
    phrases = [merchant_expression(p) for p in c.get('patterns', [rule['pattern']])]
    descriptions = [text(row['merchant'] or ''), text(row['description'] or '')]
    return (rule['active'] and row['direction'] == movement
        and (not rule['account_id'] or rule['account_id'] == row['account_id'])
        and (not phrases or any(phrase and any(phrase.search(description) for description in descriptions) for phrase in phrases))
        and (not source_categories(rule) or text(source_category(row)) in {text(value) for value in source_categories(rule)})
        and (c.get('minCents') is None or row['amount_cents'] >= c['minCents'])
        and (c.get('maxCents') is None or row['amount_cents'] <= c['maxCents']))


def rank(rule):
    """Description conditions win before account, category, or amount specificity."""
    c = conditions(rule)
    return (has_merchant_condition(rule), bool(rule['account_id']),
            bool(source_categories(rule)), int(c.get('minCents') is not None)+int(c.get('maxCents') is not None),
            -len(source_categories(rule)))


def has_merchant_condition(rule):
    return bool(conditions(rule).get('patterns', [rule['pattern']]))


def reason(rule):
    c = conditions(rule)
    phrases = c.get('patterns', [rule['pattern']])
    parts = [('Description contains '+ ' or '.join('“'+p+'”' for p in phrases))] if phrases else []
    if phrases:parts.append('merchant word spacing and trailing store numbers may vary')
    if source_categories(rule): parts.append('original statement category equals '+' or '.join('“'+value+'”' for value in source_categories(rule)))
    if rule['account_id']: parts.append('source account matches')
    if c.get('minCents') is not None: parts.append('amount ≥ '+format(c['minCents']/100, '.2f')+' USD')
    if c.get('maxCents') is not None: parts.append('amount ≤ '+format(c['maxCents']/100, '.2f')+' USD')
    parts.append('money in' if rule.get('treatment') else 'money out')
    return '; '.join(parts)+'. Rule '+rule['id']+'.'


def choose(row, rules):
    found = [r for r in rules if matches(row, r)]
    if not found: return None
    category_fallbacks = [r['id'] for r in found if not has_merchant_condition(r)]
    best = max(rank(r) for r in found)
    found = [r for r in found if rank(r) == best]
    if any(consistency.rule_issue(r) for r in found):
        return {'conflict': True, 'reason': consistency.RULE_MESSAGE, 'ruleIds': [r['id'] for r in found]}
    targets = {(r.get('treatment', ''), r['business_id'], r['category_name'], bool(r.get('include_expenses'))) for r in found}
    if len(targets) > 1:
        return {'conflict': True, 'reason': 'Equally specific rules disagree. Review the destination or pause a conflicting rule.', 'ruleIds': [r['id'] for r in found]}
    # Identical destinations use the least automatic setting when modes differ.
    rule = min(found, key=lambda r: MODES.index(r.get('automation_mode', 'suggest')))
    explanation = reason(rule)
    overridden = category_fallbacks if has_merchant_condition(rule) else []
    if overridden:
        explanation += ' Merchant description rules take priority over matching original-category rules.'
    return {'rule': rule, 'reason': explanation, 'ruleIds': [r['id'] for r in found],
            'overriddenRuleIds': sorted(overridden), 'conflict': False}


def all_rules(db):
    return [dict(r)|{'type': kind} for table, kind in (('merchant_rules', 'expense'), ('credit_rules', 'credit'))
            for r in db.execute('SELECT * FROM '+table+' ORDER BY created_at DESC,id')]


def editable_rules_comments():
    """Human-readable instructions stored as data, so the file stays valid JSON."""
    return {
        'about':'This section is a guide, not a rule. The importer ignores _comments and reference. Only entries inside rules are saved as rules. JSON does not support // or /* */ comments; keep explanations inside quoted strings like these.',
        'file_sections':{
            'format':'Keep "local-bookkeeper-rules" unchanged; it identifies this file as a rules export.',
            'version':'Keep 1 unchanged; it identifies the supported file format version.',
            'rules':'The actual list of rule objects to add or update. Supports up to 1,000 entries; browser uploads are limited to 5 MB.',
            '_comments':'Optional explanation at the top level. You can edit or remove this section; its examples and text never create rules.',
            'reference':'Lookup lists for existing businesses, accounts and categories. These lists do not change the profile.'
        },
        'how_to_use':[
            'Edit the rules array in a text editor. Save valid JSON with double quotes, true/false booleans and no trailing commas.',
            'To update a rule in this profile, keep its id. To add a rule, copy an entry and remove id, or write an entry without id.',
            'Use reference.businesses and reference.accounts to find IDs. Use reference.categories to choose an existing category for the business. A category with businessId null is shared.',
            'Import the file in Rules & automation > Import JSON and accept the safeguard prompt. File edits are never imported automatically.',
            'Import validates the entire file before saving. Unchanged entries and identical additions are skipped. Omitting an entry does not delete its saved rule; use active: false to pause it.',
            'Saved rules run on future confirmed statement imports. To change eligible existing rows, use Preview rules on existing rows and confirm the preview.',
            'At app startup, or when you copy/open its path, an unedited export refreshes after confirmation. External edits are preserved until you explicitly import them.'
        ],
        'matching_and_categorization':[
            'Expense rules match money out (debits); credit rules match money in (credits). The account is where the transaction came from; businessId selects the business destination or, for personal expense rules, the category lookup scope.',
            'An expense rule whose category is Personal / non-business classifies matches as personal, clears their business assignment, and excludes them from expense totals. Keep includeInTotals false. Its businessId identifies the existing category, not a business expense assignment.',
            'patterns matches merchant names or the full description, ignoring case and punctuation. Spaces between phrase words may be omitted, and a merchant name may have trailing store numbers: MAVIS matches MAVIS123, and ADVANCE AUTO matches ADVANCEAUTO. Word boundaries stay intact, so MAVIS does not match MAVISION. Explicit store numbers remain exact. Any one phrase can match.',
            'sourceCategories matches an original statement category label exactly after ignoring case and punctuation. Any one label in the list can match. These are bank labels, not your destination expense categories.',
            'If both patterns and sourceCategories contain entries, a transaction must match a phrase AND a source label. At least one of these lists must contain an entry.',
            'Account scope and amount limits must also match. minAmount/maxAmount use the nonnegative transaction amount in USD, for both debits and credits.',
            'Among matching rules, merchant phrases take priority, then a specific account, then source-category conditions, then amount limits, then fewer source labels.',
            'Equally specific rules that disagree leave the transaction for review. When equally specific rules agree on the destination and totals but differ in mode, the least automatic mode wins.',
            'Already reviewed rows, confirmed/possible duplicates, linked transactions and unclear movements can require separate attention. A matching rule does not bypass transaction validation.'
        ],
        'fields':{
            'id':'An existing rule ID from this profile. Keep it to update that rule. Remove it from a copied rule to create a new one. A rule ID from another profile cannot update this profile.',
            'type':{'expense':'Money-out rule: assigns eligible expenses or fees to businessId and category.','credit':'Money-in rule: uses treatment to handle payments, refunds or other credits.'},
            'patterns':'List of merchant/description phrases, for example ["SHELL OIL", "EXXON"]. Maximum 200 phrases, each 2-120 characters after normalization. Use [] for a source-category-only rule.',
            'sourceCategories':'List of original statement labels, for example ["Travel", "Transportation"]. Maximum 200 nonblank labels of up to 200 characters. Use [] for a merchant-only rule.',
            'sourceCategory':'Optional older spelling for a single source label. Prefer sourceCategories; the list takes precedence when supplied.',
            'accountId':'Required. A source account ID from reference.accounts limits this rule to that account. Explicit null means Universal: all current and future source accounts in this profile. Omitting the field or using an empty string is rejected.',
            'businessId':'A business ID from reference.businesses. Required for expense rules and business refunds. null puts a credit decision outside business books. Non-refund credit treatments ignore this field.',
            'category':'Destination expense category name, not a category ID or the original statement label. Choose an existing active category for businessId, or a shared category. Required for expenses/business refunds; use "" for other credits. Personal / non-business on an expense rule assigns personal classification and exclusion, with no business assignment. Uncategorized/review is not a valid rule destination.',
            'treatment':{
                'expense_rules':'Use "" or omit this field; it is ignored for expense rules.',
                'payment':'Card payment or account transfer. Kept outside business expense totals.',
                'refund':'Purchase refund. With a businessId and category, it can reduce that business expense category when reviewed and included. With businessId null, it stays outside business books.',
                'statement_credit':'Statement benefit, reward or account credit kept outside business expense totals. It does not automatically reduce the original purchase.',
                'excluded_credit':'Other money-in explicitly kept outside business expense totals.'
            },
            'minAmount':'Optional inclusive minimum transaction amount in USD. null means no minimum. A nonnegative number or decimal string such as "10.25" is accepted; use at most two decimal places.',
            'maxAmount':'Optional inclusive maximum in USD, with the same format as minAmount. null means no maximum. The maximum must not be less than the minimum.',
            'mode':{
                'suggest':'Suggests the decision. You still review and apply it. This is the default when mode is omitted.',
                'categorize':'Applies the category or credit decision automatically but leaves the transaction awaiting review, outside expense totals.',
                'review':'Trusted automation: applies the decision and marks eligible matches reviewed. includeInTotals separately controls business expense totals.'
            },
            'includeInTotals':{
                'true':'Counts eligible reviewed business expenses/fees in expense totals; business refunds subtract from those totals. Requires mode: "review" and either an expense rule or a refund assigned to a business and category.',
                'false':'Keeps matches outside reported business expense totals, even if categorized or reviewed. You can include them manually later. This is the default.',
                'limits':'Cannot be true for personal expenses, payments, statement credits, excluded credits, personal refunds, or suggest/categorize modes. Changing this field does not by itself change previously saved transactions.'
            },
            'active':'true enables this rule; false pauses it without deleting it or undoing previous decisions. New entries default to true.'
        },
        'reference':'Informational lists of active business/account IDs and category names. Editing reference does not create or rename businesses, accounts or categories; do that in the app first.',
        'examples_note':'These examples are ignored here. Copy one into rules, replace placeholder business/account IDs with values from reference, and choose an existing category. Leave id out to add a new rule.',
        'examples':{
            'merchant_expense':{'type':'expense','patterns':['OFFICE DEPOT','STAPLES'],'sourceCategories':[],
                'accountId':None,'businessId':'COPY-BUSINESS-ID-FROM-REFERENCE','category':'Office supplies',
                'mode':'categorize','includeInTotals':False,'active':True},
            'statement_category_expense':{'type':'expense','patterns':[],'sourceCategories':['Travel','Transportation'],
                'accountId':'COPY-ACCOUNT-ID-FROM-REFERENCE','businessId':'COPY-BUSINESS-ID-FROM-REFERENCE',
                'category':'Fuel','mode':'suggest','includeInTotals':False,'active':True},
            'reviewed_business_refund':{'type':'credit','patterns':['SUPPLIER REFUND'],'accountId':None,
                'businessId':'COPY-BUSINESS-ID-FROM-REFERENCE','category':'Office supplies','treatment':'refund',
                'mode':'review','includeInTotals':True,'active':True},
            'card_payment':{'type':'credit','patterns':['MOBILE PAYMENT'],'accountId':'COPY-ACCOUNT-ID-FROM-REFERENCE',
                'businessId':None,'category':'','treatment':'payment','mode':'suggest','includeInTotals':False,'active':True}
        }
    }


def editable_rules(db):
    """Rules file format intended for user editing outside the app."""
    result=[]
    for rule in all_rules(db):
        c=conditions(rule)
        patterns=c.get('patterns') or ([] if source_categories(rule) else [rule['pattern']])
        result.append({'id':rule['id'],'type':rule['type'],'patterns':patterns,
            'sourceCategories':source_categories(rule),'accountId':rule['account_id'],
            'businessId':rule['business_id'],'category':rule['category_name'],
            'treatment':rule.get('treatment',''),'minAmount':None if c.get('minCents') is None else c['minCents']/100,
            'maxAmount':None if c.get('maxCents') is None else c['maxCents']/100,
            'mode':rule['automation_mode'],'includeInTotals':bool(rule['include_expenses']),
            'active':bool(rule['active'])})
    return {'_comments':editable_rules_comments(),'format':'local-bookkeeper-rules','version':1,'rules':result,
        'reference':{
            'businesses':[{'id':r['id'],'name':r['legal_name']} for r in db.execute('SELECT id,legal_name FROM businesses WHERE active=1 ORDER BY legal_name')],
            'accounts':[{'id':r['id'],'name':r['nickname']} for r in db.execute('SELECT id,nickname FROM accounts WHERE active=1 ORDER BY nickname')],
            'categories':[{'name':r['name'],'businessId':r['business_id']} for r in db.execute('SELECT name,business_id FROM categories WHERE active=1 ORDER BY name')]}}


def editable_rule_signature(rule):
    c=conditions(rule)
    patterns=c.get('patterns') or ([] if source_categories(rule) else [rule['pattern']])
    return (rule['type'],tuple(sorted({text(p) for p in patterns})),
        tuple(sorted({text(s) for s in source_categories(rule)})),c.get('minCents'),c.get('maxCents'),
        rule['account_id'],rule['business_id'],rule['category_name'].casefold(),rule.get('treatment',''),
        rule['automation_mode'],bool(rule['include_expenses']),bool(rule['active']))


def import_editable_rules(db, payload, now):
    if not isinstance(payload,dict) or payload.get('format')!='local-bookkeeper-rules' or type(payload.get('version')) is not int or payload['version']!=1:
        raise ValueError('Choose a Local Bookkeeper rules JSON file (format local-bookkeeper-rules, version 1).')
    # _comments and reference are informational; only rules are imported.
    items=payload.get('rules')
    if not isinstance(items,list) or len(items)>1000:
        raise ValueError('The rules file must contain up to 1,000 rules.')
    prepared=[]
    current={(r['type'],r['id']):editable_rule_signature(r) for r in all_rules(db)}
    seen_ids=set()
    for i,item in enumerate(items,1):
        if not isinstance(item,dict): raise ValueError('Rule '+str(i)+' must be an object.')
        if set(item)-{'id','type','patterns','sourceCategory','sourceCategories','accountId','businessId','category','treatment','minAmount','maxAmount','mode','includeInTotals','active'}:
            raise ValueError('Rule '+str(i)+' has unsupported fields.')
        try:
            for field in ('type','mode','category','treatment'):
                if field in item and not isinstance(item[field],str): raise ValueError(field+' must be text.')
            for field in ('id','accountId','businessId'):
                if field in item and item[field] is not None and (not isinstance(item[field],str) or not item[field].strip() or len(item[field])>200):
                    raise ValueError(field+' must be a nonblank ID or null.')
            if 'active' in item and type(item['active']) is not bool: raise ValueError('active must be true or false.')
            if item.get('id'):
                key=(item.get('type','expense'),item['id'])
                if key in seen_ids: raise ValueError('The same rule ID appears twice.')
                if key not in current: raise ValueError('This ID is not in this profile. Remove id to create a new rule.')
                seen_ids.add(key)
            rule=values(db,item)
            rule['active']=int(item.get('active',True))
        except ValueError as exc:
            raise ValueError('Rule '+str(i)+': '+str(exc)) from exc
        prepared.append((bool(item.get('id')),rule))
    imported=updated=skipped=0
    for has_id,rule in prepared:
        table='merchant_rules' if rule['type']=='expense' else 'credit_rules'
        key=(rule['type'],rule['id'])
        signature=editable_rule_signature(rule)
        if (has_id and current[key]==signature) or (not has_id and signature in current.values()):
            skipped+=1
            continue
        fields=['pattern','account_id','business_id','category_name','conditions_json','automation_mode','include_expenses','active']
        if rule['type']=='credit': fields.append('treatment')
        if has_id:
            db.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',
                [rule[k] for k in fields]+[rule['id']])
            updated+=1
        else:
            fields+=['id','created_at']; rule['created_at']=now
            db.execute('INSERT INTO '+table+'('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',
                [rule[k] for k in fields])
            imported+=1
        current[key]=signature
    return {'ok':True,'imported':imported,'updated':updated,'skipped':skipped}


def rows(db):
    return db.execute('''SELECT t.*,o.source_category AS original_source_category FROM transactions t
        LEFT JOIN original_transactions o ON o.transaction_id=t.id ORDER BY t.date DESC,t.id''').fetchall()


def eligible(db, row):
    if row['status']=='approved' or row['excluded'] or row['duplicate_of'] or row['related_transaction_id']:
        return False
    if row['classification'] in ('personal', 'transfer'): return False
    if row['direction']!='credit' and row['transaction_kind']=='transfer': return False
    if row['direction']=='credit' and row['credit_treatment']: return False
    # A likely duplicate stays for a human decision, including duplicates in the same import.
    others=db.execute('SELECT id FROM transactions WHERE account_id=? AND source_fingerprint=? AND id<>?',
                      (row['account_id'],row['source_fingerprint'],row['id'])).fetchall()
    for other in others:
        decision=db.execute('''SELECT decision FROM duplicate_decisions WHERE
            (first_id=? AND second_id=?) OR (first_id=? AND second_id=?)''',
            (row['id'],other['id'],other['id'],row['id'])).fetchone()
        if not decision or decision['decision']!='distinct': return False
    return row['direction'] in ('debit', 'credit')


def cents(value):
    if value in ('', None): return None
    try:
        amount = Decimal(str(value))*100
        if not amount.is_finite() or amount<0 or amount>999999999999 or amount!=amount.to_integral_value(): raise ValueError()
        return int(amount)
    except (InvalidOperation, ValueError): raise ValueError('Use nonnegative amounts with at most two decimal places.')


def account_scope(db, body):
    """An omitted or blank account must never silently become a universal rule."""
    if 'accountId' not in body:
        raise ValueError('Choose a source account or explicitly choose Universal (accountId: null).')
    account = body['accountId']
    if account is not None and (not isinstance(account, str) or not account.strip()):
        raise ValueError('Choose a source account or explicitly choose Universal (accountId: null).')
    if account is not None and not db.execute('SELECT id FROM accounts WHERE active=1 AND id=?',(account,)).fetchone():
        raise ValueError('Choose an active source account.')
    return account


def values(db, body, allow_new_category=False):
    kind = body.get('type', 'expense')
    if kind not in ('expense', 'credit'): raise ValueError('Choose an expense or credit rule.')
    mode = body.get('mode', 'suggest')
    if mode not in MODES: raise ValueError('Choose a valid automation level.')
    patterns = body.get('patterns', [])
    if not isinstance(patterns, list) or len(patterns)>MAX_RULE_PHRASES or any(not isinstance(p,str) or not 2<=len(text(p))<=120 for p in patterns):
        raise ValueError('Enter up to '+str(MAX_RULE_PHRASES)+' merchant phrases, each between 2 and 120 characters.')
    patterns = list(dict.fromkeys(p.strip() for p in patterns))
    source = body.get('sourceCategory', '')
    if not isinstance(source,str) or len(source)>200: raise ValueError('Original category must be at most 200 characters.')
    source = source.strip()
    sources = body.get('sourceCategories', [source] if text(source) else [])
    if not isinstance(sources,list) or len(sources)>MAX_SOURCE_CATEGORIES or any(not isinstance(s,str) or not text(s) or len(s.strip())>200 for s in sources):
        raise ValueError('Choose up to '+str(MAX_SOURCE_CATEGORIES)+' nonblank original statement categories, each at most 200 characters.')
    sources = list({text(s):s.strip() for s in sources}.values())
    if not patterns and not sources: raise ValueError('Enter a merchant phrase or an original statement category.')
    low, high = cents(body.get('minAmount')), cents(body.get('maxAmount'))
    if low is not None and high is not None and low>high: raise ValueError('Minimum amount must not exceed maximum.')
    account = account_scope(db, body)
    treatment = body.get('treatment', '') if kind=='credit' else ''
    if kind=='credit' and treatment not in ('payment','refund','statement_credit','excluded_credit'): raise ValueError('Choose a credit decision.')
    business = body.get('businessId') or None
    category = body.get('category', '')
    needs_business = kind=='expense' or (treatment=='refund' and bool(business))
    if needs_business:
        if kind=='credit' and consistency.is_personal_category(category): raise ValueError(consistency.RULE_MESSAGE)
        if not db.execute('SELECT id FROM businesses WHERE active=1 AND id=?',(business,)).fetchone(): raise ValueError('Choose a business.')
        cat = db.execute('SELECT name FROM categories WHERE active=1 AND name=? COLLATE NOCASE AND (business_id=? OR business_id IS NULL)',(category,business)).fetchone()
        if (not cat and not allow_new_category) or 'uncategorized' in category.lower(): raise ValueError('Choose an existing expense category for this business.')
        category = cat['name'] if cat else category
    else: business, category = None, ''
    include = body.get('includeInTotals', False)
    if type(include) is not bool: raise ValueError('Inclusion must be true or false.')
    if include and kind=='expense' and personal_category(category):
        raise ValueError('Personal expense rules must stay excluded from business totals. Set includeInTotals to false.')
    if include and (mode!='review' or not needs_business): raise ValueError('Only an explicitly trusted business expense/refund rule can include totals.')
    c = {'patterns':patterns,'sourceCategory':sources[0] if len(sources)==1 else '',
        'direction':'credit' if kind=='credit' else 'debit','minCents':low,'maxCents':high}
    if len(sources)>1: c['sourceCategories']=sources
    return {'id':body.get('id') or str(uuid.uuid4()),'type':kind,'pattern':' | '.join(patterns or sources),
        'account_id':account,'business_id':business,'category_name':category,'treatment':treatment,'active':1,
        'automation_mode':mode,'conditions_json':json.dumps(c,sort_keys=True),'include_expenses':int(include)}


def decision_rule(db, body, rows, *, kind, business=None, category='', treatment='', reviewed=False, include=False, allow_new_category=False):
    """Prepare a future-import rule from an explicit transaction decision."""
    for key in ('rememberRule', 'ruleAllAccounts'):
        if key in body and type(body[key]) is not bool: raise ValueError('Rule options must be true or false.')
    if body.get('rememberRule') is not True: return None
    account = body.get('ruleAccountId') or None
    if account and body.get('ruleAllAccounts') is True:
        raise ValueError('Choose either one source account or Universal, not both.')
    if not account and body.get('ruleAllAccounts') is not True:
        raise ValueError('Choose the source account or explicitly choose all accounts for this rule.')
    mode = body.get('ruleMode', 'suggest')
    if mode == 'review' and not reviewed:
        raise ValueError('Review the selected decision before automatically reviewing future matches.')
    basis = body.get('ruleMatch','merchant')
    if basis not in ('merchant','sourceCategory'): raise ValueError('Choose merchant descriptions or original statement categories for this rule.')
    rule = values(db, {'type':kind, 'patterns':[] if basis=='sourceCategory' else body.get('rulePatterns',[body.get('rulePattern', '')]),
        'sourceCategories':body.get('ruleSourceCategories',[]) if basis=='sourceCategory' else [], 'accountId':account,
        'businessId':business, 'category':category, 'treatment':treatment, 'mode':mode,
        'includeInTotals':bool(include and mode=='review')}, allow_new_category=allow_new_category)
    if not rows or any(not matches(row,rule) for row in rows):
        raise ValueError('The rule descriptions or original statement categories and account must match every selected transaction. Narrow the selection or edit the conditions.')
    # Replace a prior decision with exactly these conditions and account scope.
    # More specific rules retain their existing precedence.
    rule['replacesRuleIds'] = [saved['id'] for saved in all_rules(db)
        if saved['type']==kind and saved['account_id']==account
        and {text(p) for p in conditions(saved).get('patterns',[saved['pattern']])}=={text(p) for p in conditions(rule)['patterns']}
        and {text(s) for s in source_categories(saved)}=={text(s) for s in source_categories(rule)}
        and conditions(saved).get('minCents') is None and conditions(saved).get('maxCents') is None]
    return rule


def save_decision_rule(db, rule, now):
    table = 'merchant_rules' if rule['type']=='expense' else 'credit_rules'
    fields = ['id','pattern','account_id','business_id','category_name','conditions_json','automation_mode','include_expenses']
    if rule['type']=='credit': fields.append('treatment')
    for previous in rule['replacesRuleIds']:
        db.execute('UPDATE '+table+' SET active=0 WHERE id=?',(previous,))
    db.execute('INSERT INTO '+table+'('+','.join(fields)+',created_at) VALUES('+','.join('?' for _ in fields)+',?)',
               [rule[k] for k in fields]+[now])
    return rule['id']


def save(db, body, now):
    kind = body.get('type','expense')
    if kind not in ('expense','credit'): raise ValueError('Choose a valid rule type.')
    table = 'merchant_rules' if kind=='expense' else 'credit_rules'
    if set(body)<= {'id','type','active'}:
        if type(body.get('active')) is not bool: raise ValueError('Choose whether this rule is enabled.')
        saved = db.execute('SELECT * FROM '+table+' WHERE id=?',(body.get('id'),)).fetchone()
        if not saved: raise ValueError('Rule not found.')
        if body['active']: consistency.validate_rule(saved)
        db.execute('UPDATE '+table+' SET active=? WHERE id=?',(int(body['active']),body['id']))
        return {'ok':True}
    rule = values(db,body)
    validate_selected_groups(db,body,rule)
    if body.get('id') and not db.execute('SELECT id FROM '+table+' WHERE id=?',(rule['id'],)).fetchone(): raise ValueError('Rule not found.')
    fields = ['pattern','account_id','business_id','category_name','conditions_json','automation_mode','include_expenses']
    if kind=='credit': fields.append('treatment')
    if body.get('id'):
        db.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*[rule[k] for k in fields],rule['id']))
    else:
        fields += ['id','created_at']; rule['created_at']=now
        db.execute('INSERT INTO '+table+'('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',[rule[k] for k in fields])
    return {'ok':True,'id':rule['id']}


def validate_selected_groups(db, body, rule):
    if 'selectedIds' not in body: return
    from categorization import selected_rows
    selected = selected_rows(db,{'ids':body['selectedIds']})
    if any(not matches(row,rule) for row in selected):
        raise ValueError('Some selected groups do not match this rule. Check the merchant phrases, source account, original category and amount limits, or go back to leave those groups out.')


def rule_preview(db, body):
    import credits
    rule = values(db,body)
    validate_selected_groups(db,body,rule)
    matched = [r for r in rows(db) if matches(r,rule)]
    return {'matched':len(matched),'eligible':sum(eligible(db,r) for r in matched),'rows':[
        {'id':r['id'],'description':r['description'],'date':r['date'],'amountCents':r['amount_cents'],
         'sourceCategory':source_category(r),'eligible':eligible(db,r),'reason':reason(rule),
         'destination':(credits.LABELS[rule['treatment']]+(' · '+rule['category_name'] if rule['business_id'] else '')) if rule['type']=='credit' else rule['category_name']} for r in matched[:50]]}


def overview(db):
    saved, existing = all_rules(db), rows(db)
    return {'rules':[r|{'conditions':conditions(r),'matchCount':sum(matches(t,r|{'active':1}) for t in existing),
                       'consistencyIssue':consistency.rule_issue(r)} for r in saved],
            'proposals':proposals(existing, saved),'maxPatterns':MAX_RULE_PHRASES,'maxSourceCategories':MAX_SOURCE_CATEGORIES,
            'actionStatuses':{r['id']:r['status'] for r in db.execute("SELECT id,status FROM review_actions WHERE action_type='automation'")}}


def proposals(existing, saved):
    groups = defaultdict(list)
    for r in existing:
        if consistency.transaction_issue(r): continue
        if r['status']!='approved' or r['duplicate_of'] or not r['merchant'].strip(): continue
        if r['direction']=='debit' and r['classification']=='business' and r['transaction_kind'] in ('expense','fee'):
            kind, treatment = 'expense',''
        elif r['direction']=='credit' and r['credit_treatment']:
            kind, treatment = 'credit',r['credit_treatment']
        else: continue
        groups[(r['account_id'],text(r['merchant']),kind)].append((r,treatment))
    result=[]
    for items in groups.values():
        if len(items)<2: continue
        targets={(t,r['business_id'],r['category_name']) for r,t in items}
        if len(targets)!=1: continue
        row,treatment=items[0]
        # Category mappings are fallbacks, so they must not hide more precise
        # merchant ideas. A conditional merchant rule may cover only some rows.
        if all(any(has_merchant_condition(rule) and matches(member,rule) for rule in saved)
               for member,_ in items): continue
        phrase=' '.join(row['merchant'].split())
        if not 2<=len(text(phrase))<=120: continue
        result.append({'type':'credit' if treatment else 'expense','patterns':[phrase],'accountId':row['account_id'],
            'businessId':row['business_id'],'category':row['category_name'],'treatment':treatment,'count':len(items)})
    return sorted(result,key=lambda r:(-r['count'],r['category'],r['patterns'][0]))


def plan(db, handler, ids=None):
    import credits
    from categorization import FIELDS
    saved=all_rules(db); changes=[]; buckets={'categorized':[],'reviewed':[],'suggested':[],'conflicts':[],'unmatched':[],'attention':[]}
    wanted=set(ids) if ids is not None else None
    for row in rows(db):
        if wanted is not None and row['id'] not in wanted: continue
        if not eligible(db,row):
            if wanted is not None: buckets['attention'].append(row['id'])
            continue
        match=choose(row,saved)
        if not match: buckets['unmatched'].append(row['id']); continue
        if match['conflict']: buckets['conflicts'].append(row['id']); continue
        rule=match['rule']; mode=rule.get('automation_mode','suggest')
        if mode=='suggest': buckets['suggested'].append(row['id']); continue
        try:
            if rule['type']=='credit':
                body={'ids':[row['id']],'treatment':rule['treatment'],'refundUsage':'business' if rule['business_id'] else 'outside',
                    'businessId':rule['business_id'],'category':rule['category_name'],'includeInTotals':bool(rule['include_expenses'])}
                change=credits.plan(db,body,handler.validate_transaction)[1][0]
                if mode!='review': change['new']['status']='suggested'
            else:
                if row['transaction_kind'] not in ('expense','fee'): raise ValueError('Review the movement and transaction kind before automatic categorization.')
                cat=db.execute('SELECT id,name FROM categories WHERE active=1 AND name=? AND (business_id=? OR business_id IS NULL) ORDER BY business_id IS NULL LIMIT 1',(rule['category_name'],rule['business_id'])).fetchone()
                if not cat: raise ValueError('Rule destination category is unavailable.')
                new={k:row[k] for k in FIELDS}
                new.update(category_id=cat['id'],category_name=cat['name'],business_id=rule['business_id'],classification='business',
                    status='approved' if mode=='review' else 'suggested',include_in_totals=int(rule['include_expenses']))
                if personal_category(cat['name']):
                    new.update(category_id=None,business_id=None,classification='personal',excluded=1,include_in_totals=0)
                change={'id':row['id'],'old':{k:row[k] for k in FIELDS},'new':new}
            handler.validate_transaction(db,dict(row)|change['new'])
            if all(row[k]==v for k,v in change['new'].items()): continue
            change.update(description=row['description'],date=row['date'],amountCents=row['amount_cents'],ruleId=rule['id'],
                reason=match['reason']+' '+('Automatically reviewed under your trusted rule.' if mode=='review' else 'Automatically categorized; awaiting review, outside expense totals.'),
                version=dict(row))
            if rule['type']=='expense' and personal_category(rule['category_name']):
                change['reason']+=' Classified as personal, excluded from business totals, with no business assignment.'
            changes.append(change); buckets['reviewed' if mode=='review' else 'categorized'].append(row['id'])
        except ValueError:
            buckets['attention'].append(row['id'])
    revision=hashlib.sha256(json.dumps({'rules':saved,'changes':changes,'buckets':buckets},sort_keys=True).encode()).hexdigest()
    return {'revision':revision,'counts':{k:len(v) for k,v in buckets.items()},'groups':buckets,
        'rows':[{k:v for k,v in c.items() if k!='version'} for c in changes]},changes


def apply(db, handler, now, ids=None, revision=None):
    public,changes=plan(db,handler,ids)
    if revision is not None and revision!=public['revision']: raise ValueError('Transactions or rules changed. Preview automation again.')
    action=None
    if changes:
        action=str(uuid.uuid4())
        db.execute('INSERT INTO review_actions(id,action_type,description,created_at) VALUES(?,?,?,?)',
            (action,'automation','Apply import rules to '+str(len(changes))+' transactions',now))
        for c in changes:
            new=c['new']
            db.execute('UPDATE transactions SET '+','.join(k+'=?' for k in new)+',updated_at=? WHERE id=?',(*new.values(),now,c['id']))
            handler.record_change(db,c['id'],c['old'],new,action,'automation',now)
            db.execute('UPDATE transaction_history SET reason=? WHERE action_id=? AND transaction_id=?',(c['reason'],action,c['id']))
    return public|{'actionId':action}
