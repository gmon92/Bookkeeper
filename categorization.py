"""Previewed bulk categorization and local, account-scoped merchant rules."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
import automation
import consistency
from decimal import Decimal

FIELDS = ('category_id','category_name','classification','business_id','status','include_in_totals','excluded')


def merchant_text(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    return ' '.join(re.sub(r'[^\w]+',' ',value).split())


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS merchant_rules (
      id TEXT PRIMARY KEY, pattern TEXT NOT NULL, account_id TEXT REFERENCES accounts(id),
      business_id TEXT NOT NULL REFERENCES businesses(id), category_name TEXT NOT NULL,
      active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created_at TEXT NOT NULL
    )''')


def rules(db):
    return [dict(r) for r in db.execute('SELECT * FROM merchant_rules ORDER BY created_at DESC,id')]


def matching_rules(row, active_rules):
    if row['status'] == 'approved' or row['excluded'] or row['duplicate_of'] or row['classification'] in {'personal','transfer'} or row['transaction_kind'] == 'transfer':
        return []
    return [rule for rule in active_rules if automation.matches(row,rule)]


def suggestion(row, active_rules):
    matches = matching_rules(row,active_rules)
    if not matches:
        return None
    choice = automation.choose(row,matches)
    if choice['conflict']: return choice
    rule = choice['rule']
    if row['business_id'] == rule['business_id'] and row['classification']=='business' and row['category_name'] == rule['category_name']:
        return None
    return {'conflict':False,'category':rule['category_name'],'businessId':rule['business_id'],
            'reason':choice['reason'], 'ruleIds':choice['ruleIds']}


def suggestions(db):
    active_rules = rules(db)
    if not any(r['active'] for r in active_rules): return {}
    result = {}
    for row in db.execute("SELECT * FROM transactions WHERE status<>'approved' AND excluded=0 AND duplicate_of IS NULL"):
        value = suggestion(row,active_rules)
        if value: result[row['id']] = value
    return result


def rule_values(db, body):
    pattern = body.get('pattern','')
    category = body.get('category','')
    account, business = automation.account_scope(db, body), body.get('businessId')
    if not isinstance(pattern,str) or not 2 <= len(merchant_text(pattern)) or len(pattern.strip()) > 120:
        raise ValueError('Enter a merchant phrase between 2 and 120 characters.')
    if not isinstance(category,str) or not category.strip() or 'uncategorized' in category.lower():
        raise ValueError('Choose an expense category for this rule.')
    if consistency.is_personal_category(category):
        raise ValueError(consistency.RULE_MESSAGE)
    if not db.execute('SELECT id FROM businesses WHERE active=1 AND id=?',(business,)).fetchone():
        raise ValueError('Choose a business for this rule.')
    if account and not db.execute('SELECT id FROM accounts WHERE active=1 AND id=?',(account,)).fetchone():
        raise ValueError('Choose a valid source account.')
    existing_category = db.execute('SELECT name FROM categories WHERE active=1 AND name=? COLLATE NOCASE AND (business_id=? OR business_id IS NULL)',(category.strip(),business)).fetchone()
    if not existing_category:
        raise ValueError('Choose an existing category for this business.')
    return {'id':'preview','pattern':pattern.strip(),'category_name':existing_category['name'],'account_id':account,'business_id':business,'active':1}


def preview_rule(db, body):
    rule = rule_values(db,body)
    rows = [row for row in db.execute('SELECT * FROM transactions ORDER BY date DESC,id') if matching_rules(row,[rule])]
    return {'count':len(rows),'amountCents':sum(r['amount_cents'] for r in rows),
            'rows':[{'id':r['id'],'date':r['date'],'description':r['description'],'amountCents':r['amount_cents'],'category':r['category_name'],
                     'rawAmount':r['raw_amount_text'],'direction':r['direction'],'sourceRow':r['source_row'],
                     'reason':'Description contains “'+rule['pattern']+'”; '+('source account matches the rule.' if rule['account_id'] else 'the rule explicitly covers all source accounts.')} for r in rows[:30]]}


def selected_rows(db, body):
    ids = body.get('ids')
    if not isinstance(ids,list) or not ids or len(ids)>5000 or any(not isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)):
        raise ValueError('Select between 1 and 5,000 unique transactions.')
    # Avoid depending on SQLite's platform-specific SQL variable limit.
    rows = []
    for tx_id in sorted(ids):
        row = db.execute('SELECT * FROM transactions WHERE id=?',(tx_id,)).fetchone()
        if row is None: raise ValueError('A selected transaction no longer exists. Refresh the list.')
        rows.append(row)
    return rows


def plan(db, body, validate):
    rows = selected_rows(db,body)
    mode = body.get('mode','categorize')
    if mode not in {'categorize','suggestions'}: raise ValueError('Choose a valid categorization action.')
    for key in ('markReviewed','includeInTotals','createCategory','rememberRule','ruleAllAccounts'):
        if key in body and not isinstance(body[key],bool): raise ValueError('Review options must be true or false.')
    reviewed, include = body.get('markReviewed',False), body.get('includeInTotals',False)
    if include and not reviewed: raise ValueError('Mark the rows reviewed before including expenses.')
    if mode == 'suggestions' and (reviewed or include): raise ValueError('Apply suggestions first, then explicitly review them.')
    category = body.get('category','')
    target = body.get('businessId') or None
    if mode == 'categorize' and (not isinstance(category,str) or not category.strip() or len(category)>100 or 'uncategorized' in category.lower()):
        raise ValueError('Enter an expense category with at most 100 characters.')
    if target and not db.execute('SELECT id FROM businesses WHERE active=1 AND id=?',(target,)).fetchone():
        raise ValueError('Choose an active business.')
    all_rules, changes, exceptions, creates = rules(db), [], [], set()
    selected_total = format(Decimal(sum(r['amount_cents'] for r in rows))/100,'.2f')
    for row in rows:
        try:
            if row['duplicate_of'] or row['classification']=='transfer' or row['transaction_kind']=='transfer':
                raise ValueError('Duplicate or transfer: use its separate review action.')
            if row['direction']=='credit' and row['credit_treatment']!='refund':
                raise ValueError('Use Credits & payments to choose whether this is a payment, refund or excluded credit.')
            new = {key:row[key] for key in FIELDS}
            if mode == 'suggestions':
                match = suggestion(row,all_rules)
                if not match or match.get('conflict'):
                    raise ValueError('No unambiguous active merchant rule matches this row.')
                name, business = match['category'],match['businessId']
                new.update(classification='business',business_id=business,status='suggested',include_in_totals=0)
            else:
                name, business = category.strip(), target or row['business_id']
                if target:
                    new.update(classification='business',business_id=target)
                if new['classification'] != 'business' or not business:
                    raise ValueError('Choose a business to categorize unassigned or personal activity.')
                new.update(status='approved' if reviewed else 'needs_review',include_in_totals=int(include))
                # Categorization alone preserves an explicit exclusion. Only the
                # separately checked reporting decision can remove it.
                if include: new['excluded'] = 0
            cat = db.execute('SELECT id,name FROM categories WHERE active=1 AND name=? COLLATE NOCASE AND (business_id=? OR business_id IS NULL) ORDER BY business_id IS NULL LIMIT 1',(name,business)).fetchone()
            if not cat and not (mode=='categorize' and body.get('createCategory') is True):
                raise ValueError('Category does not exist for this business. Enable creation or choose another category.')
            if not cat: creates.add((business,name))
            new.update(category_name=cat['name'] if cat else name,category_id=cat['id'] if cat else None)
            if mode == 'suggestions' and automation.personal_category(new['category_name']):
                new.update(category_id=None,classification='personal',business_id=None,excluded=1,include_in_totals=0)
            candidate = dict(row) | new
            consistency.validate_transaction(candidate)
            if reviewed:
                # The category's explicit creation is checked separately in the
                # preview and its actual membership is checked again at commit.
                validate(db,candidate,check_category=bool(cat))
            changes.append({'id':row['id'],'date':row['date'],'description':row['description'],'amountCents':row['amount_cents'],
                            'accountId':row['account_id'],'old':{key:row[key] for key in FIELDS},'new':new,
                            'reason':match['reason']+'; rule IDs: '+', '.join(match['ruleIds']) if mode=='suggestions' else
                                'You assigned '+str(len(rows))+' selected transactions to “'+new['category_name']+'” in one batch. Combined selected activity: '+selected_total+' USD. '+('Explicitly reviewed and included in totals.' if include else 'Explicitly reviewed, outside totals.' if reviewed else 'Saved for review, outside totals.'),
                            'version':dict(row) | {'_history_revision':db.execute('SELECT coalesce(max(rowid),0) FROM transaction_history WHERE transaction_id=?',(row['id'],)).fetchone()[0]}})
        except ValueError as exc:
            exceptions.append({'id':row['id'],'description':row['description'],'reason':str(exc)})
    # Includes source state and effective suggestions, so a preview cannot be
    # applied after another edit or a changed rule produces a different result.
    remembered_rule = None
    if body.get('rememberRule') and not exceptions:
        if mode != 'categorize': raise ValueError('Save rules from a chosen category, not from multiple suggestions.')
        destinations = {c['new']['business_id'] for c in changes}
        if len(destinations) != 1: raise ValueError('A merchant rule needs a single destination business.')
        remembered_rule = automation.decision_rule(db,body,rows,kind='expense',business=changes[0]['new']['business_id'],
            category=changes[0]['new']['category_name'],reviewed=reviewed,include=include,allow_new_category=bool(creates))
    rule_revision = {k:v for k,v in remembered_rule.items() if k!='id'} if remembered_rule else None
    revision = hashlib.sha256(json.dumps({'changes':changes,'exceptions':exceptions,'create':sorted(creates),'rule':rule_revision,'options':{k:v for k,v in body.items() if k!='revision'}},sort_keys=True).encode()).hexdigest()
    accounts = {r['id']:r['nickname'] for r in db.execute('SELECT id,nickname FROM accounts')}
    businesses = {r['id']:r['display_name'] for r in db.execute('SELECT id,display_name FROM businesses')}
    public = {'revision':revision,'selectedCount':len(rows),'applicableCount':len(changes),'exceptionCount':len(exceptions),
              'amountCents':sum(c['amountCents'] for c in changes),'exceptions':exceptions,
              'accounts':sorted({accounts[c['accountId']] for c in changes}),
        'businesses':sorted({businesses[c['new']['business_id']] if c['new']['business_id'] else 'Personal / non-business' for c in changes}),
              'newCategories':[{'businessId':b,'name':n} for b,n in sorted(creates)],'rememberedRule':remembered_rule,
              'rows':[{k:v for k,v in c.items() if k!='version'} for c in changes[:40]]}
    return public, changes, creates


def commit(db, body, handler, now):
    public, changes, creates = plan(db,body,handler.validate_transaction)
    if body.get('revision') != public['revision']:
        raise ValueError('Selected rows or rules changed. Preview the changes again.')
    if public['exceptionCount']:
        raise ValueError('Some selected rows need attention. Remove them from the selection and preview again.')
    if not changes: raise ValueError('No transactions can receive these changes.')
    for business,name in creates:
        db.execute('INSERT INTO categories(id,business_id,name) VALUES(?,?,?)',(str(uuid.uuid4()),business,name))
    rule_id = automation.save_decision_rule(db,public['rememberedRule'],now) if public['rememberedRule'] else None
    action_id = str(uuid.uuid4())
    description = 'Apply merchant suggestions' if body.get('mode')=='suggestions' else 'Categorize '+str(len(changes))+' transactions as '+body['category'].strip()
    db.execute('INSERT INTO review_actions(id,action_type,description,created_at) VALUES(?,?,?,?)',(action_id,'batch_categorize',description,now))
    for change in changes:
        new = change['new']
        cat = db.execute('SELECT id FROM categories WHERE active=1 AND name=? AND (business_id=? OR business_id IS NULL) ORDER BY business_id IS NULL LIMIT 1',(new['category_name'],new['business_id'])).fetchone()
        new['category_id'] = cat['id']
        if body.get('markReviewed'): handler.validate_transaction(db,change['version'] | new)
        db.execute('UPDATE transactions SET '+','.join(k+'=?' for k in FIELDS)+',updated_at=? WHERE id=?',(*[new[k] for k in FIELDS],now,change['id']))
        handler.record_change(db,change['id'],change['old'],new,action_id,'categorize',now)
        db.execute('UPDATE transaction_history SET reason=? WHERE action_id=? AND transaction_id=?',(change['reason'],action_id,change['id']))
    return {'ok':True,'actionId':action_id,'count':len(changes),'ruleId':rule_id}
