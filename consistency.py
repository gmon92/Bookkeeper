"""Read-only consistency checks shared by review and mutation paths."""
import re
import unicodedata


PERSONAL_MESSAGE = ('Personal / non-business cannot be assigned to business books or included in expense totals. '
                    'Mark the transaction Personal, or choose a business category.')
RULE_MESSAGE = ('This rule assigns Personal / non-business to business books. '
                'Pause the rule or choose a business category.')


def is_personal_category(name):
    if not isinstance(name, str):
        return False
    normalized = unicodedata.normalize('NFKC', name).casefold()
    return ' '.join(re.sub(r'[^\w]+', ' ', normalized).split()) == 'personal non business'


def transaction_issue(row):
    if is_personal_category(row['category_name']) and (row['classification'] == 'business' or row['include_in_totals']):
        return PERSONAL_MESSAGE
    return None


def rule_issue(rule):
    if rule['business_id'] and is_personal_category(rule['category_name']):
        return RULE_MESSAGE
    return None


def validate_transaction(row):
    issue = transaction_issue(row)
    if issue:
        raise ValueError(issue)


def validate_rule(rule):
    issue = rule_issue(rule)
    if issue:
        raise ValueError(issue)
