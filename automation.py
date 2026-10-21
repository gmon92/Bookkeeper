"""Deterministic import automation, explicit rule settings and reversible decisions."""
import hashlib
import json
import uuid
from collections import defaultdict
from decimal import Decimal, InvalidOperation

import source_archive

MODES = ('suggest', 'categorize', 'review')
MAX_RULE_PHRASES = 200


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


def conditions(rule):
    return json.loads(rule.get('conditions_json', '{}'))


def source_category(row):
    if 'original_source_category' in row.keys(): return row['original_source_category'] or ''
    return source_archive.category(json.loads(row['source_raw_json']))


def matches(row, rule):
    c = conditions(rule)
    movement = c.get('direction', 'credit' if rule.get('treatment') else 'debit')
    phrases = c.get('patterns', [rule['pattern']])
    description = ' '+text(row['merchant'] or row['description'])+' '
    return (rule['active'] and row['direction'] == movement
        and (not rule['account_id'] or rule['account_id'] == row['account_id'])
        and (not phrases or any(' '+text(p)+' ' in description for p in phrases))
        and (not c.get('sourceCategory') or text(c['sourceCategory']) == text(source_category(row)))
        and (c.get('minCents') is None or row['amount_cents'] >= c['minCents'])
        and (c.get('maxCents') is None or row['amount_cents'] <= c['maxCents']))


def rank(rule):
    c = conditions(rule)
    return (bool(c.get('patterns', [rule['pattern']])), bool(rule['account_id']),
            bool(c.get('sourceCategory')), int(c.get('minCents') is not None)+int(c.get('maxCents') is not None))


def reason(rule):
    c = conditions(rule)
    phrases = c.get('patterns', [rule['pattern']])
    parts = [('Description contains '+ ' or '.join('“'+p+'”' for p in phrases))] if phrases else []
    if c.get('sourceCategory'): parts.append('original statement category equals “'+c['sourceCategory']+'”')
    if rule['account_id']: parts.append('source account matches')
    if c.get('minCents') is not None: parts.append('amount ≥ '+format(c['minCents']/100, '.2f')+' USD')
    if c.get('maxCents') is not None: parts.append('amount ≤ '+format(c['maxCents']/100, '.2f')+' USD')
    parts.append('money in' if rule.get('treatment') else 'money out')
    return '; '.join(parts)+'. Rule '+rule['id']+'.'


def choose(row, rules):
    found = [r for r in rules if matches(row, r)]
    if not found: return None
    best = max(rank(r) for r in found)
    found = [r for r in found if rank(r) == best]
    targets = {(r.get('treatment', ''), r['business_id'], r['category_name'], bool(r.get('include_expenses'))) for r in found}
    if len(targets) > 1:
        return {'conflict': True, 'reason': 'Equally specific rules disagree. Review the destination or pause a conflicting rule.', 'ruleIds': [r['id'] for r in found]}
    # Identical destinations use the least automatic setting when modes differ.
    rule = min(found, key=lambda r: MODES.index(r.get('automation_mode', 'suggest')))
    return {'rule': rule, 'reason': reason(rule), 'ruleIds': [r['id'] for r in found], 'conflict': False}


def all_rules(db):
    return [dict(r)|{'type': kind} for table, kind in (('merchant_rules', 'expense'), ('credit_rules', 'credit'))
            for r in db.execute('SELECT * FROM '+table+' ORDER BY created_at DESC,id')]


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
    if not patterns and not text(source): raise ValueError('Enter a merchant phrase or an original statement category.')
    low, high = cents(body.get('minAmount')), cents(body.get('maxAmount'))
    if low is not None and high is not None and low>high: raise ValueError('Minimum amount must not exceed maximum.')
    account = body.get('accountId') or None
    if account and not db.execute('SELECT id FROM accounts WHERE active=1 AND id=?',(account,)).fetchone(): raise ValueError('Choose an active source account.')
    treatment = body.get('treatment', '') if kind=='credit' else ''
    if kind=='credit' and treatment not in ('payment','refund','statement_credit','excluded_credit'): raise ValueError('Choose a credit decision.')
    business = body.get('businessId') or None
    category = body.get('category', '')
    needs_business = kind=='expense' or (treatment=='refund' and bool(business))
    if needs_business:
        if not db.execute('SELECT id FROM businesses WHERE active=1 AND id=?',(business,)).fetchone(): raise ValueError('Choose a business.')
        cat = db.execute('SELECT name FROM categories WHERE active=1 AND name=? COLLATE NOCASE AND (business_id=? OR business_id IS NULL)',(category,business)).fetchone()
        if (not cat and not allow_new_category) or 'uncategorized' in category.lower(): raise ValueError('Choose an existing expense category for this business.')
        category = cat['name'] if cat else category
    else: business, category = None, ''
    include = body.get('includeInTotals', False)
    if type(include) is not bool: raise ValueError('Inclusion must be true or false.')
    if include and (mode!='review' or not needs_business): raise ValueError('Only an explicitly trusted business expense/refund rule can include totals.')
    c = {'patterns':patterns,'sourceCategory':source,'direction':'credit' if kind=='credit' else 'debit','minCents':low,'maxCents':high}
    return {'id':body.get('id') or str(uuid.uuid4()),'type':kind,'pattern':' | '.join(patterns) or source,
        'account_id':account,'business_id':business,'category_name':category,'treatment':treatment,'active':1,
        'automation_mode':mode,'conditions_json':json.dumps(c,sort_keys=True),'include_expenses':int(include)}


def decision_rule(db, body, rows, *, kind, business=None, category='', treatment='', reviewed=False, include=False, allow_new_category=False):
    """Prepare a future-import rule from an explicit transaction decision."""
    for key in ('rememberRule', 'ruleAllAccounts'):
        if key in body and type(body[key]) is not bool: raise ValueError('Rule options must be true or false.')
    if body.get('rememberRule') is not True: return None
    account = body.get('ruleAccountId') or None
    if not account and body.get('ruleAllAccounts') is not True:
        raise ValueError('Choose the source account or explicitly choose all accounts for this rule.')
    mode = body.get('ruleMode', 'suggest')
    if mode == 'review' and not reviewed:
        raise ValueError('Review the selected decision before automatically reviewing future matches.')
    rule = values(db, {'type':kind, 'patterns':body.get('rulePatterns',[body.get('rulePattern', '')]), 'accountId':account,
        'businessId':business, 'category':category, 'treatment':treatment, 'mode':mode,
        'includeInTotals':bool(include and mode=='review')}, allow_new_category=allow_new_category)
    if not rows or any(not matches(row,rule) for row in rows):
        raise ValueError('The rule description and account must match every selected transaction. Narrow the selection or edit the phrase.')
    # Replace a prior decision with exactly these conditions and account scope.
    # More specific rules retain their existing precedence.
    rule['replacesRuleIds'] = [saved['id'] for saved in all_rules(db)
        if saved['type']==kind and saved['account_id']==account
        and {text(p) for p in conditions(saved).get('patterns',[saved['pattern']])}=={text(p) for p in conditions(rule)['patterns']}
        and not conditions(saved).get('sourceCategory')
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
        if not db.execute('SELECT id FROM '+table+' WHERE id=?',(body.get('id'),)).fetchone(): raise ValueError('Rule not found.')
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
    return {'rules':[r|{'conditions':conditions(r),'matchCount':sum(matches(t,r|{'active':1}) for t in existing)} for r in saved],
            'proposals':proposals(existing, saved),'maxPatterns':MAX_RULE_PHRASES,
            'actionStatuses':{r['id']:r['status'] for r in db.execute("SELECT id,status FROM review_actions WHERE action_type='automation'")}}


def proposals(existing, saved):
    groups = defaultdict(list)
    for r in existing:
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
        if any(matches(row,r) for r in saved): continue
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
                change={'id':row['id'],'old':{k:row[k] for k in FIELDS},'new':new}
            handler.validate_transaction(db,dict(row)|change['new'])
            if all(row[k]==v for k,v in change['new'].items()): continue
            change.update(description=row['description'],date=row['date'],amountCents=row['amount_cents'],ruleId=rule['id'],
                reason=match['reason']+' '+('Automatically reviewed under your trusted rule.' if mode=='review' else 'Automatically categorized; awaiting review, outside expense totals.'),
                version=dict(row))
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
