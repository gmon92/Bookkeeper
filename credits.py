"""Explicit, previewed handling of money-in rows and related card payments."""
import datetime as dt
import hashlib
import json
import re
import uuid
import automation

from categorization import merchant_text, selected_rows

LABELS = {'payment':'Card payment / transfer', 'refund':'Purchase refund',
          'statement_credit':'Statement credit / benefit', 'excluded_credit':'Other credit outside business books',
          '':'Needs a decision'}
FIELDS = ('transaction_kind','classification','business_id','category_id','category_name','status',
          'include_in_totals','excluded','credit_treatment','related_transaction_id')


def initialize(db):
    columns = {r['name'] for r in db.execute('PRAGMA table_info(transactions)')}
    if 'credit_treatment' not in columns:
        db.execute("ALTER TABLE transactions ADD COLUMN credit_treatment TEXT NOT NULL DEFAULT '' CHECK(credit_treatment IN ('','payment','refund','statement_credit','excluded_credit'))")
    if 'related_transaction_id' not in columns:
        db.execute('ALTER TABLE transactions ADD COLUMN related_transaction_id TEXT REFERENCES transactions(id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_related_transaction ON transactions(related_transaction_id)')
    db.execute('''CREATE TABLE IF NOT EXISTS credit_rules (
      id TEXT PRIMARY KEY, pattern TEXT NOT NULL, account_id TEXT REFERENCES accounts(id),
      treatment TEXT NOT NULL, business_id TEXT REFERENCES businesses(id), category_name TEXT NOT NULL DEFAULT '',
      active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created_at TEXT NOT NULL)''')
    for operation in ('INSERT','UPDATE'):
        db.execute(f'''CREATE TRIGGER IF NOT EXISTS validate_credit_{operation.lower()} BEFORE {operation} ON transactions
          WHEN (NEW.credit_treatment='payment' AND (NEW.transaction_kind<>'transfer' OR NEW.classification<>'transfer' OR NEW.include_in_totals<>0))
            OR (NEW.credit_treatment IN ('statement_credit','excluded_credit') AND
                (NEW.direction<>'credit' OR NEW.transaction_kind<>'adjustment' OR NEW.classification<>'personal' OR NEW.excluded<>1 OR NEW.include_in_totals<>0))
            OR (NEW.credit_treatment='refund' AND (NEW.direction<>'credit' OR NEW.transaction_kind<>'refund' OR NEW.classification NOT IN ('business','personal')))
          BEGIN SELECT RAISE(ABORT,'Use Credits & payments to change this credit decision'); END''')


def rules(db):
    return [dict(r) for r in db.execute('SELECT * FROM credit_rules ORDER BY created_at DESC,id')]


def suggestion(row, saved_rules):
    if row['direction'] != 'credit' or row['duplicate_of'] or row['credit_treatment']:
        return None
    text = ' ' + merchant_text(row['merchant'] or row['description']) + ' '
    matches = [r for r in saved_rules if automation.matches(row,r)]
    if matches:
        choice = automation.choose(row,matches)
        if choice['conflict']: return choice
        rule = choice['rule']
        return {'treatment':rule['treatment'],'businessId':rule['business_id'],'category':rule['category_name'],
                'reason':choice['reason']+' Review before applying.', 'ruleIds':choice['ruleIds']}
    if re.search(r'\b(mobile payment|online payment|payment thank you|autopay|auto pay|payment received|automatic payment|card payment)\b',text):
        return {'treatment':'payment','reason':'The description looks like a card payment. Confirm it is a transfer between accounts.'}
    if re.search(r'\b(statement credit|cash back|cashback|reward|rewards|benefit credit|digital entertainment credit|walmart credit)\b',text):
        return {'treatment':'statement_credit','reason':'The description looks like a statement benefit or reward. Confirm whether it is a benefit or a purchase refund.'}
    if re.search(r'\b(refund|refunded|return|reversal)\b',text):
        return {'treatment':'refund','reason':'The description mentions a return or refund. Compare with the original purchase before reducing business expenses.'}
    return None


def suggestions(db):
    saved = rules(db)
    return {row['id']:value for row in db.execute("SELECT * FROM transactions WHERE direction='credit'")
            if (value:=suggestion(row,saved)) is not None}


def validate_treatment(values):
    treatment = values.get('credit_treatment','')
    if treatment not in LABELS: raise ValueError('Choose a valid credit decision.')
    if treatment == 'payment' and (values['transaction_kind']!='transfer' or values['classification']!='transfer' or values['include_in_totals']):
        raise ValueError('Use Credits & payments to change a card payment decision.')
    if treatment in {'statement_credit','excluded_credit'} and (values['direction']!='credit' or values['transaction_kind']!='adjustment' or values['classification']!='personal' or not values['excluded'] or values['include_in_totals']):
        raise ValueError('Use Credits & payments to change a credit kept outside business books.')
    if treatment=='refund' and (values['direction']!='credit' or values['transaction_kind']!='refund' or values['classification'] not in {'business','personal'}):
        raise ValueError('Use Credits & payments to change a refund decision.')
    if values['direction']=='credit' and values['include_in_totals'] and treatment!='refund':
        raise ValueError('Review this money-in row in Credits & payments before including it as a business refund.')


def related_row(db, row, target_id, treatment):
    target = db.execute('SELECT * FROM transactions WHERE id=?',(target_id,)).fetchone()
    if not target or target['id']==row['id'] or target['direction']!='debit' or target['duplicate_of']:
        raise ValueError('Choose an original money-out transaction that is not a confirmed duplicate.')
    if treatment=='payment':
        if target['account_id']==row['account_id'] or target['amount_cents']!=row['amount_cents']:
            raise ValueError('A linked card payment needs an equal withdrawal on a different source account.')
        if target['related_transaction_id'] not in (None,row['id']):
            raise ValueError('That withdrawal is already linked to another payment.')
        if target['credit_treatment'] not in ('','payment'):
            raise ValueError('That withdrawal already has a different credit decision.')
    elif treatment=='refund':
        if target['account_id']!=row['account_id'] or target['amount_cents']<row['amount_cents'] or target['transaction_kind'] not in {'expense','fee','unknown'}:
            raise ValueError('Choose a purchase on this source account for at least the refund amount.')
    else:
        raise ValueError('Links are available for payments and purchase refunds.')
    return target


def candidates(db, transaction_id, treatment, query=''):
    row = db.execute('SELECT * FROM transactions WHERE id=?',(transaction_id,)).fetchone()
    if not row or row['direction']!='credit': raise ValueError('Choose a money-in transaction.')
    if treatment not in {'payment','refund'}: return []
    if not isinstance(query,str) or len(query)>200: raise ValueError('Search related transactions with at most 200 characters.')
    words = query.lower().split()
    found = []
    for target in db.execute("SELECT * FROM transactions WHERE direction='debit' AND id<>? ORDER BY date DESC,id",(row['id'],)):
        try: related_row(db,row,target['id'],treatment)
        except ValueError: continue
        try: days = (dt.date.fromisoformat(row['date'])-dt.date.fromisoformat(target['date'])).days
        except (ValueError,TypeError): continue
        same_merchant = merchant_text(row['merchant'] or row['description']) == merchant_text(target['merchant'] or target['description'])
        matched = abs(days)<=7 if treatment=='payment' else 0<=days<=365 and (same_merchant or target['amount_cents']==row['amount_cents'])
        if words:
            text = (target['date']+' '+target['description']+' '+format(target['amount_cents']/100,'.2f')).lower()
            if not all(word in text for word in words): continue
        elif not matched and target['id']!=row['related_transaction_id']: continue
        distance = str(abs(days))+' day'+('' if abs(days)==1 else 's')
        purchase_match = 'Same merchant' if same_merchant else 'Equal purchase amount' if target['amount_cents']==row['amount_cents'] else 'Purchase amount covers this partial refund'
        reason = ('Equal amount on another account; '+distance+' apart. Confirm this pair.' if treatment=='payment' else
                  purchase_match+'; '+distance+(' before' if days>=0 else ' after')+' this credit. Compare the source details.')
        found.append({'id':target['id'],'date':target['date'],'description':target['description'],'accountId':target['account_id'],
                      'amountCents':target['amount_cents'],'businessId':target['business_id'],'category':target['category_name'],'reason':reason})
    return found[:100]


def rule_values(db, body, rows):
    business_refund = body.get('treatment')=='refund' and body.get('refundUsage')=='business'
    return automation.decision_rule(db,body,rows,kind='credit',treatment=body.get('treatment',''),
        business=body.get('businessId') if business_refund else None,category=body.get('category','') if business_refund else '',
        reviewed=True,include=body.get('includeInTotals',False))


def plan(db, body, validate):
    rows = selected_rows(db,body)
    treatment = body.get('treatment')
    if treatment not in LABELS: raise ValueError('Choose how to handle these credits.')
    for key in ('includeInTotals','rememberRule','ruleAllAccounts'):
        if key in body and type(body[key]) is not bool: raise ValueError('Credit review options must be true or false.')
    include = body.get('includeInTotals',False)
    business_refund = treatment=='refund' and body.get('refundUsage')=='business'
    if treatment=='refund' and body.get('refundUsage') not in {'business','outside'}:
        raise ValueError('Choose whether this refund belongs in business books.')
    if include and not business_refund: raise ValueError('Only a business purchase refund can reduce business expenses.')
    if 'relatedId' in body and len(rows)!=1: raise ValueError('Link related transactions one credit at a time.')
    if body.get('relatedId') and not isinstance(body['relatedId'],str): raise ValueError('Choose a valid related transaction.')
    category, business = None, None
    if business_refund:
        business = body.get('businessId')
        if not db.execute('SELECT id FROM businesses WHERE id=? AND active=1',(business,)).fetchone():
            raise ValueError('Choose the business receiving the purchase refund.')
        category = db.execute('SELECT id,name FROM categories WHERE active=1 AND name=? AND (business_id=? OR business_id IS NULL) ORDER BY business_id IS NULL LIMIT 1',(body.get('category'),business)).fetchone()
        if not category or 'uncategorized' in category['name'].lower(): raise ValueError('Choose a business expense category for this refund.')
    changes = {}

    def change(row, new, reason):
        validate_treatment(dict(row)|new)
        changes[row['id']] = {'id':row['id'],'description':row['description'],'date':row['date'],'amountCents':row['amount_cents'],
            'accountId':row['account_id'],'old':{k:row[k] for k in FIELDS},'new':new,'reason':reason,
            'version':dict(row)|{'historyRevision':db.execute('SELECT coalesce(max(rowid),0) FROM transaction_history WHERE transaction_id=?',(row['id'],)).fetchone()[0]}}

    for row in rows:
        if row['direction']!='credit': raise ValueError('This workspace handles money-in rows. Select credits separately from charges.')
        if row['duplicate_of'] and (include or body.get('relatedId')): raise ValueError('A confirmed duplicate cannot be included or linked as a separate payment.')
        new = {k:row[k] for k in FIELDS}
        new.update(credit_treatment=treatment,include_in_totals=0,business_id=None,category_id=None,status='approved',related_transaction_id=None)
        if treatment=='payment':
            new.update(transaction_kind='transfer',classification='transfer',excluded=0,category_name='Transfers')
        elif treatment in {'statement_credit','excluded_credit'}:
            new.update(transaction_kind='adjustment',classification='personal',excluded=1,
                       category_name='Statement credits / benefits' if treatment=='statement_credit' else 'Personal / non-business')
        elif treatment=='refund':
            new.update(transaction_kind='refund',classification='business' if business_refund else 'personal',excluded=0 if business_refund else 1,
                       business_id=business,category_id=category['id'] if category else None,category_name=category['name'] if category else 'Refunds outside business books',include_in_totals=int(include))
        else:
            new.update(transaction_kind='unknown',classification='unknown',excluded=0,status='needs_review',category_name='Uncategorized / review')
        link_id = body.get('relatedId',row['related_transaction_id'] if treatment==row['credit_treatment'] and treatment in {'payment','refund'} else None)
        target = related_row(db,row,link_id,treatment) if link_id else None
        if target:
            new['related_transaction_id'] = target['id']
        previous_id = row['related_transaction_id']
        if previous_id and previous_id!=link_id and row['credit_treatment']=='payment':
            previous = db.execute('SELECT * FROM transactions WHERE id=?',(previous_id,)).fetchone()
            if previous and previous['related_transaction_id']==row['id']:
                old_partner = {k:previous[k] for k in FIELDS}; old_partner['related_transaction_id']=None
                old_partner['credit_treatment']=''
                change(previous,old_partner,'Unlinked the prior payment pair; its recorded transfer decision remains outside expenses.')
        reason = 'You chose '+LABELS[treatment]+'. '+('Reduces the selected business expense category.' if include else 'Outside business expense totals.')
        if treatment in {'statement_credit','excluded_credit'}: reason += ' The original charge remains recorded separately.'
        if target: reason += ' Linked to '+target['description']+' ('+target['date']+').'
        if business_refund: validate(db,dict(row)|new)
        change(row,new,reason)
        if target and treatment=='payment':
            if target['id'] in changes: raise ValueError('The same withdrawal cannot be linked to multiple selected credits.')
            partner = {k:target[k] for k in FIELDS}
            partner.update(transaction_kind='transfer',classification='transfer',business_id=None,category_id=None,category_name='Transfers',
                           status='approved',include_in_totals=0,excluded=0,credit_treatment='payment',related_transaction_id=row['id'])
            change(target,partner,'You linked this withdrawal to a card payment. Both sides are transfers outside expense totals.')
    rule = rule_values(db,body,rows)
    items = list(changes.values())
    rule_revision = {k:v for k,v in rule.items() if k!='id'} if rule else None
    revision = hashlib.sha256(json.dumps({'changes':items,'options':{k:v for k,v in body.items() if k!='revision'},'rule':rule_revision},sort_keys=True).encode()).hexdigest()
    public = {'revision':revision,'selectedCount':len(rows),'affectedCount':len(items),'amountCents':sum(r['amount_cents'] for r in rows),
              'treatment':treatment,'label':LABELS[treatment],'includeInTotals':include,
              'rows':[{k:v for k,v in c.items() if k!='version'} for c in items], 'rememberedRule':rule}
    return public, items, rule


def commit(db, body, handler, now):
    public, changes, rule = plan(db,body,handler.validate_transaction)
    if body.get('revision')!=public['revision']: raise ValueError('These credits or related transactions changed. Preview the decision again.')
    action_id = str(uuid.uuid4())
    db.execute('INSERT INTO review_actions(id,action_type,description,created_at) VALUES(?,?,?,?)',
               (action_id,'credit_review','Handle '+str(public['selectedCount'])+' credits: '+public['label'],now))
    for c in changes:
        new = c['new']
        db.execute('UPDATE transactions SET '+','.join(k+'=?' for k in FIELDS)+',updated_at=? WHERE id=?',(*[new[k] for k in FIELDS],now,c['id']))
        handler.record_change(db,c['id'],c['old'],new,action_id,'credit_review',now)
        db.execute('UPDATE transaction_history SET reason=? WHERE action_id=? AND transaction_id=?',(c['reason'],action_id,c['id']))
    rule_id = automation.save_decision_rule(db,rule,now) if rule else None
    return {'ok':True,'count':public['selectedCount'],'affectedCount':len(changes),'actionId':action_id,'ruleId':rule_id}
