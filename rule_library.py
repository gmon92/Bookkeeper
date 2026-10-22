"""Portable rules/categories with explicit scope mapping and previewed additive imports."""
import hashlib
import json
import uuid
from decimal import Decimal

import automation

FORMAT = 'local-bookkeeper-rules-and-categories'
MAX_BYTES = 5 * 1024 * 1024
MAX_ITEMS = 5000


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')


def export(db, now):
    result = {'format': FORMAT, 'version': 1, 'exportedAt': now,
        'businesses': [{'key': r['id'], 'name': r['display_name'], 'legalName': r['legal_name']}
            for r in db.execute('SELECT * FROM businesses ORDER BY id')],
        'accounts': [{'key': r['id'], 'name': r['nickname'], 'institution': r['institution']}
            for r in db.execute('SELECT * FROM accounts ORDER BY id')],
        'categories': [{'key': r['id'], 'businessKey': r['business_id'], 'name': r['name'],
            'taxGroup': r['tax_group'], 'requiresReview': bool(r['requires_review']), 'active': bool(r['active'])}
            for r in db.execute('SELECT * FROM categories ORDER BY id')], 'rules': []}
    for rule in automation.all_rules(db):
        c = automation.conditions(rule)
        result['rules'].append({'key': rule['id'], 'type': rule['type'],
            'patterns': c.get('patterns', [rule['pattern']]), 'sourceCategories': automation.source_categories(rule),
            'accountKey': rule['account_id'], 'businessKey': rule['business_id'], 'category': rule['category_name'],
            'treatment': rule.get('treatment', ''), 'mode': rule['automation_mode'],
            'includeInTotals': bool(rule['include_expenses']), 'active': bool(rule['active']),
            'minCents': c.get('minCents'), 'maxCents': c.get('maxCents')})
    validate(result)
    return result


def string(value, label, maximum=200, blank=False):
    if not isinstance(value, str) or len(value) > maximum or (not blank and not value.strip()):
        raise ValueError(label + ' must be text' + (' of at most ' if blank else ' between 1 and ') + str(maximum) + ' characters.')
    return value


def validate(bundle):
    if not isinstance(bundle, dict) or bundle.get('format') != FORMAT or type(bundle.get('version')) is not int or bundle['version'] != 1:
        raise ValueError('Choose a version 1 Local Bookkeeper rules-and-categories JSON file.')
    if len(encoded(bundle)) > MAX_BYTES:
        raise ValueError('The rules-and-categories file exceeds 5 MB.')
    indexes = {}
    for name in ('businesses', 'accounts', 'categories', 'rules'):
        items = bundle.get(name)
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise ValueError('The file must contain at most 5,000 ' + name + '.')
        index = {}
        for item in items:
            if not isinstance(item, dict): raise ValueError('Each ' + name + ' entry must be an object.')
            key = string(item.get('key'), 'Item key')
            if key in index: raise ValueError('Duplicate ' + name + ' key in the file.')
            index[key] = item
        indexes[name] = index
    for item in bundle['businesses'] + bundle['accounts']:
        string(item.get('name'), 'Business/account name')
    for item in bundle['categories'] + bundle['rules']:
        for field, collection in (('businessKey', 'businesses'), ('accountKey', 'accounts')):
            value = item.get(field)
            if value is not None and (not isinstance(value, str) or value not in indexes[collection]):
                raise ValueError('A category/rule references an unknown ' + collection + ' key.')
        if type(item.get('active')) is not bool: raise ValueError('Each category/rule must specify active as true or false.')
    for category in bundle['categories']:
        string(category.get('name'), 'Category name', 100)
        string(category.get('taxGroup', ''), 'Tax group', 200, blank=True)
        if type(category.get('requiresReview')) is not bool: raise ValueError('Category requiresReview must be true or false.')
    for rule in bundle['rules']:
        if rule.get('type') not in ('expense', 'credit'): raise ValueError('Choose an expense or credit rule type.')
        if rule.get('mode') not in automation.MODES: raise ValueError('Invalid rule automation level.')
        if type(rule.get('includeInTotals')) is not bool: raise ValueError('Rule includeInTotals must be true or false.')
        string(rule.get('category'), 'Rule category', 100, blank=True)
        string(rule.get('treatment', ''), 'Credit treatment', 100, blank=True)
        for field in ('patterns', 'sourceCategories'):
            values = rule.get(field)
            if not isinstance(values, list) or len(values) > 200 or any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in values):
                raise ValueError('Rule ' + field + ' must contain up to 200 nonblank text values.')
        for field in ('minCents', 'maxCents'):
            value = rule.get(field)
            if value is not None and (type(value) is not int or not 0 <= value <= 999999999999):
                raise ValueError('Amount limits must be nonnegative integer cents.')
    return indexes


def signature(rule):
    c = automation.conditions(rule)
    return (rule['type'], rule['account_id'], tuple(sorted({automation.text(p) for p in c.get('patterns', [rule['pattern']])})),
        tuple(sorted({automation.text(s) for s in automation.source_categories(rule)})), c.get('minCents'), c.get('maxCents'))


def destination(rule):
    return (rule['business_id'], rule['category_name'], rule.get('treatment', ''),
        rule['automation_mode'], bool(rule['include_expenses']), bool(rule['active']))


def prepare(db, body, workspace_id=''):
    bundle = body.get('library')
    indexes = validate(bundle)
    preserve = body.get('preserveAutomation', False)
    if type(preserve) is not bool: raise ValueError('Choose whether to keep automation settings.')
    businesses = [dict(r) for r in db.execute('SELECT * FROM businesses ORDER BY id')]
    accounts = [dict(r) for r in db.execute('SELECT * FROM accounts ORDER BY id')]
    existing_categories = [dict(r) for r in db.execute('SELECT * FROM categories ORDER BY id')]
    existing_rules = automation.all_rules(db)
    maps = {}
    for collection, field, targets in (('businesses', 'businessMap', businesses), ('accounts', 'accountMap', accounts)):
        mapping = body.get(field, {})
        if not isinstance(mapping, dict) or any(key not in indexes[collection] for key in mapping):
            raise ValueError('Choose valid ' + collection + ' mappings.')
        allowed = {row['id'] for row in targets if row['active']}
        if any(value is not None and (not isinstance(value, str) or value not in allowed) for value in mapping.values()):
            raise ValueError('Map each source ' + collection + ' entry to an active destination or skip it.')
        maps[field] = mapping
    business_map, account_map = maps['businessMap'], maps['accountMap']
    items, categories, rules = [], [], []
    category_lookup = {(r['business_id'], r['name'].casefold()): r for r in existing_categories}
    canonical_categories = {}
    for source in bundle['categories']:
        business = business_map.get(source['businessKey']) if source.get('businessKey') else None
        item = {'kind': 'category', 'label': source['name'], 'status': 'add', 'reason': '', 'businessId': business,
            'active': source['active'], 'sourceBusiness': indexes['businesses'].get(source.get('businessKey'), {}).get('name')}
        if source.get('businessKey') and not business:
            item.update(status='skip', reason='Business not mapped.')
        else:
            key = (business, source['name'].casefold())
            if key in category_lookup:
                item.update(status='keep', reason='Existing category kept with its current settings.')
            else:
                category = {'business_id': business, 'name': source['name'], 'tax_group': source.get('taxGroup', ''),
                    'requires_review': int(source['requiresReview']), 'active': int(source['active'])}
                categories.append(category)
                category_lookup[key] = category
            canonical_categories[(source.get('businessKey'), source['name'].casefold())] = category_lookup[key]
        items.append(item)
    known_rules = {}
    for rule in existing_rules: known_rules.setdefault(signature(rule), []).append(rule)
    used_ids = {(r['type'], r['id']) for r in existing_rules}
    seed = hashlib.sha256(encoded({'library': bundle, **maps, 'preserveAutomation': preserve})).hexdigest()
    for source in bundle['rules']:
        business = business_map.get(source['businessKey']) if source.get('businessKey') else None
        account = account_map.get(source['accountKey']) if source.get('accountKey') else None
        label = ' OR '.join(source['patterns'] or source['sourceCategories'])
        item = {'kind': 'rule', 'label': label, 'status': 'add', 'reason': '', 'businessId': business,
            'accountId': account, 'mode': source['mode'] if preserve else 'suggest', 'active': source['active'],
            'category': source['category'], 'treatment': source.get('treatment', ''),
            'sourceBusiness': indexes['businesses'].get(source.get('businessKey'), {}).get('name'),
            'sourceAccount': indexes['accounts'].get(source.get('accountKey'), {}).get('name')}
        try:
            if source.get('businessKey') and not business: raise ValueError('Business not mapped.')
            if source.get('accountKey') and not account: raise ValueError('Source account not mapped; account-scoped rules are never widened automatically.')
            category_name = source['category']
            if category_name and business:
                category = canonical_categories.get((source.get('businessKey'), category_name.casefold())) or category_lookup.get((business, category_name.casefold())) or category_lookup.get((None, category_name.casefold()))
                if not category or not category['active']: raise ValueError('Rule category is missing or inactive in the destination.')
                category_name = category['name']
            payload = {'id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'local-bookkeeper-library:' + seed + ':' + source['type'] + ':' + source['key'])),
                'type': source['type'], 'patterns': source['patterns'], 'sourceCategories': source['sourceCategories'],
                'accountId': account, 'businessId': business, 'category': category_name, 'treatment': source.get('treatment', ''),
                'mode': item['mode'], 'includeInTotals': source['includeInTotals'] if preserve else False,
                'minAmount': str(Decimal(source['minCents']) / 100) if source.get('minCents') is not None else '',
                'maxAmount': str(Decimal(source['maxCents']) / 100) if source.get('maxCents') is not None else ''}
            rule = automation.values(db, payload, allow_new_category=True)
            rule['active'] = int(source['active'])
            item.update(businessId=rule['business_id'], accountId=rule['account_id'],
                category=rule['category_name'], treatment=rule.get('treatment', ''))
            matches = known_rules.get(signature(rule), [])
            if any(destination(other) == destination(rule) for other in matches):
                item.update(status='keep', reason='Identical rule already present.')
            elif matches or (rule['type'], rule['id']) in used_ids:
                item.update(status='skip', reason='Existing rule with these conditions kept. Review differences in Rules & automation.')
            else:
                rules.append(rule)
                known_rules.setdefault(signature(rule), []).append(rule)
                used_ids.add((rule['type'], rule['id']))
                item['includeInTotals'] = bool(rule['include_expenses'])
        except ValueError as exc:
            item.update(status='skip', reason=str(exc))
        items.append(item)
    counts = {kind + status.title(): sum(item['kind'] == kind and item['status'] == status for item in items)
        for kind in ('category', 'rule') for status in ('add', 'keep', 'skip')}
    counts['trustedRules'] = sum(r['active'] and r['automation_mode'] == 'review' for r in rules)
    counts['includeInTotalsRules'] = sum(r['active'] and r['include_expenses'] for r in rules)
    snapshot = {'workspaceId': workspace_id, 'library': bundle, **maps, 'preserveAutomation': preserve, 'businesses': businesses,
        'accounts': accounts, 'categories': existing_categories, 'rules': existing_rules, 'items': items}
    return {'revision': hashlib.sha256(encoded(snapshot)).hexdigest(), 'counts': counts, 'items': items}, categories, rules


def apply(db, body, now, workspace_id=''):
    preview, categories, rules = prepare(db, body, workspace_id)
    if not isinstance(body.get('revision'), str) or body['revision'] != preview['revision']:
        raise ValueError('The library, mappings, categories or rules changed. Preview the import again.')
    for category in categories:
        db.execute('INSERT INTO categories(id,business_id,name,tax_group,requires_review,active) VALUES(?,?,?,?,?,?)',
            (str(uuid.uuid4()), category['business_id'], category['name'], category['tax_group'], category['requires_review'], category['active']))
    for rule in rules:
        table = 'merchant_rules' if rule['type'] == 'expense' else 'credit_rules'
        fields = ['id', 'pattern', 'account_id', 'business_id', 'category_name', 'active', 'automation_mode', 'conditions_json', 'include_expenses']
        if rule['type'] == 'credit': fields.append('treatment')
        db.execute('INSERT INTO ' + table + '(' + ','.join(fields) + ',created_at) VALUES(' + ','.join('?' for _ in fields) + ',?)',
            [rule[field] for field in fields] + [now])
    return {'ok': True, 'counts': preview['counts']}
