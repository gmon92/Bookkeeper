'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const paths = {
  overview: '<rect x="3" y="3" width="7" height="7" rx="1.2"/><rect x="14" y="3" width="7" height="7" rx="1.2"/><rect x="3" y="14" width="7" height="7" rx="1.2"/><rect x="14" y="14" width="7" height="7" rx="1.2"/>',
  review: '<path d="M8 4H5a1 1 0 0 0-1 1v15h16V5a1 1 0 0 0-1-1h-3"/><rect x="8" y="2" width="8" height="4" rx="1"/><path d="m8 13 3 3 5-6"/>',
  transactions: '<path d="M4 6h16M4 12h16M4 18h16"/><path d="M7 3v6m10 0v6m-7 0v6"/>',
  import: '<path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5"/>',
  accounts: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h4"/>',
  reports: '<path d="M4 3v18h17M9 16v-5m5 5V6m5 10V9"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
  settings: '<path d="m9 3-.7 2.1-2 .9-2-.4-1.5 2.6 1.3 1.6.1 2.2L3 13.7l1.5 2.6 2.1-.3 1.9 1.1.5 2.1h3l.7-2.1 2-.9 2 .4 1.5-2.6-1.3-1.6-.1-2.2 1.2-1.7-1.5-2.6-2.1.3L12.5 5 12 3z"/><circle cx="10.8" cy="11.1" r="3"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 6a8 8 0 0 1 13 3M18 18a8 8 0 0 1-13-3"/>',
  'arrow-right': '<path d="M4 12h15m-5-5 5 5-5 5"/>',
  'arrow-up-right': '<path d="M6 18 18 6M6 6h12v12"/>',
  'chevron-down': '<path d="m6 9 6 6 6-6"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  file: '<path d="M14 3H5v18h14V8z"/><path d="M14 3v5h5M8 12h8m-8 4h5"/>',
  folder: '<path d="M3 6h7l2 2h9v12H3z"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18"/>',
  business: '<path d="M4 21V6h11v15M8 6V3h7v3m0 6h5v9M8 10h3m-3 4h3m-3 4h3M2 21h20"/>',
  warning: '<path d="m12 3 10 18H2z"/><path d="M12 9v4m0 3v.1"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v2"/>',
  download: '<path d="M12 3v12m-4-4 4 4 4-4M4 17v4h16v-4"/>',
  tag: '<path d="M3 3h8l10 10-8 8L3 11z"/><circle cx="7.5" cy="7.5" r=".7"/>',
  coffee: '<path d="M4 8h12v10a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3zM16 9h2a3 3 0 0 1 0 6h-2M7 3v2m5-2v2"/>',
  receipt: '<path d="m5 3 2 1 2-1 3 1 3-1 2 1 2-1v18l-2-1-2 1-3-1-3 1-2-1-2 1z"/><path d="M9 8h6m-6 4h6m-6 4h4"/>',
};
const icon = name => '<svg viewBox="0 0 24 24" aria-hidden="true">' + (paths[name] || paths.file) + '</svg>';
const e = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pageNames = { overview: 'Overview', review: 'Review queue', transactions: 'Transactions', imports: 'Imports', accounts: 'Accounts', reports: 'Reports', settings: 'Data & storage' };
const state = { transactions: [], accounts: [], businesses: [], categories: [], documents: [], health: null, connected: false, ready: false, page: 'overview', workspace: 'all', year: String(new Date().getFullYear()), query: '', account: '', tab: 'all', document: '', selected: new Set(), preview: null, batchAction: '', loadingFile: false };
try { state.workspace = localStorage.getItem('bookkeeper.workspace') || 'all'; } catch {}

function hydrateIcons(root = document) { $$('[data-icon]', root).forEach(el => { el.innerHTML = icon(el.dataset.icon); }); }
function money(cents = 0) { return (cents < 0 ? '−' : '') + (Math.abs(cents) / 100).toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }); }
function formatDate(value, options) { if (!value) return 'Date needs review'; const date = new Date(value.length === 10 ? value + 'T12:00:00' : value); return Number.isNaN(+date) ? value : date.toLocaleDateString('en-US', options || { month: 'short', day: 'numeric', year: 'numeric' }); }
function isReview(t) { return ['needs_review', 'suggested'].includes(t.status); }
function included(t) { return !t.excluded && t.status === 'approved' && t.classification === 'business' && t.includeInTotals && ((t.direction === 'debit' && ['expense','fee'].includes(t.kind)) || (t.direction === 'credit' && t.kind === 'refund')) && !t.duplicateOf; }
function contribution(t) { return t.direction === 'credit' ? -t.amountCents : t.amountCents; }
function accountName(account) { return account.nickname + (account.last_four ? ' ···· ' + account.last_four : ''); }
function businessName(id) { return state.businesses.find(b => b.id === id)?.display_name || 'Personal or shared'; }
function workspaceName() { return state.workspace === 'all' ? 'All businesses' : state.workspace === 'personal' ? 'Personal holding' : businessName(state.workspace); }
function scopedTransactions() {
  if (state.workspace === 'all') return state.transactions;
  if (state.workspace === 'personal') return state.transactions.filter(t => t.classification === 'personal' || (t.classification === 'unknown' && !state.accounts.find(a => a.id === t.accountId)?.business_id));
  return state.transactions.filter(t => t.businessId === state.workspace || (!t.businessId && state.accounts.find(a => a.id === t.accountId)?.business_id === state.workspace));
}
function inYear(t) { return state.year === 'all' || t.date?.startsWith(state.year + '-'); }
function scopedAccounts() { return state.accounts.filter(a => state.workspace === 'all' || (state.workspace === 'personal' ? !a.business_id || state.transactions.some(t=>t.accountId===a.id&&t.classification==='personal') : a.business_id === state.workspace || state.transactions.some(t => t.accountId === a.id && t.businessId === state.workspace))); }
function scopedDocuments() { if (state.workspace === 'all') return state.documents; const ids = new Set(scopedTransactions().map(t => t.documentId)); return state.documents.filter(d => ids.has(d.id)); }
function reportRows() { return scopedTransactions().filter(t => included(t) && inYear(t)); }
function totalsByCategory(rows) { const groups = new Map(); for (const t of rows) groups.set(t.category || 'Uncategorized / review', (groups.get(t.category || 'Uncategorized / review') || 0) + contribution(t)); return [...groups].sort((a, b) => b[1] - a[1]); }
function statusMarkup(t) { const review = isReview(t); const label = t.duplicateOf ? 'Duplicate' : review ? 'Needs review' : t.excluded ? 'Excluded' : 'Reviewed'; return '<span class="status ' + (review ? 'review' : t.excluded ? 'excluded' : '') + '"><i></i>' + label + '</span>'; }
function signedMoney(t) { return (t.direction === 'unknown' ? '? ' : t.direction === 'credit' ? '+ ' : '− ') + money(t.amountCents); }
function yearOptions() { const years = new Set([String(new Date().getFullYear()), ...state.transactions.map(t => /^\d{4}-/.test(t.date) ? t.date.slice(0, 4) : null).filter(Boolean)]); return '<option value="all">All years</option>' + [...years].sort().reverse().map(y => '<option value="' + y + '"' + (state.year === y ? ' selected' : '') + '>' + y + '</option>').join(''); }
function yearSelect() { return '<select class="period-control" data-year aria-label="Reporting year">' + yearOptions() + '</select>'; }
function button(label, action, style = 'primary', symbol = 'plus') { return '<button class="button button-' + style + '" data-action="' + action + '">' + (symbol ? icon(symbol) : '') + label + '</button>'; }
function heading(title, subtitle, actions = '', kicker = '') { return '<div class="page-heading"><div>' + (kicker ? '<div class="page-kicker"><i class="orange-dot"></i>' + kicker + '</div>' : '') + '<h1 class="page-title">' + title + '</h1><p class="page-subtitle">' + subtitle + '</p></div><div class="page-heading-actions">' + actions + '</div></div>'; }
function emptyState(symbol, title, text, action = '', size = '') { return '<div class="empty-state ' + size + '"><div class="empty-graphic">' + icon(symbol) + '</div><h3>' + title + '</h3><p>' + text + '</p>' + action + '</div>'; }
function statementArt() { return '<div class="statement-art" aria-hidden="true"><svg viewBox="0 0 170 195"><ellipse cx="86" cy="173" rx="63" ry="9" fill="#e9dfcc"/><circle cx="85" cy="90" r="73" fill="#efe4ce"/><path d="M43 17h85v153l-8-5-8 5-9-5-9 5-8-5-9 5-8-5-9 5-8-5-9 5z" fill="#fffcf5" stroke="#ddd3bd"/><rect x="57" y="33" width="23" height="5" rx="1" fill="#d7c9b0"/><rect x="57" y="46" width="54" height="3" rx="1" fill="#e5dcc9"/><path d="M57 63h57" stroke="#e4dac5" stroke-dasharray="3 3"/><path d="M57 79h29m15 0h13M57 92h38m6 0h13M57 105h24m20 0h13" stroke="#d7cbb4" stroke-width="3"/><path d="M57 120h57" stroke="#e4dac5" stroke-dasharray="3 3"/><path d="M57 135h19m17 0h21" stroke="#b49b77" stroke-width="4"/><circle cx="133" cy="136" r="21" fill="#ce5b36"/><path d="m123 136 6 6 13-14" stroke="#fff8ee" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/><path d="m23 49 4-10m-11 4 10 4m112-17 6-7m-4 7 7 4" stroke="#c6b48f" stroke-width="1.5"/></svg></div>'; }

function renderOverview() {
  const tx = scopedTransactions().filter(inYear), review = tx.filter(isReview), reports = tx.filter(included), total = reports.reduce((n, t) => n + contribution(t), 0);
  const accounts = scopedAccounts(), documents = scopedDocuments(), groups = totalsByCategory(reports), hasActivity = tx.length > 0;
  const setup = '<article class="panel step-panel"><h2>A simple rhythm for your books</h2><p class="step-intro">Three steps. Everything stays traceable.</p><div class="setup-steps">' +
    [[accounts.length > 0, 'Add a source account', 'The account behind each statement.', 'add-account'], [documents.length > 0, 'Bring in your statements', 'Originals kept with every import.', 'import'], [reports.length > 0, 'Review, then include', 'You decide what enters your books.', 'review']].map(([done, title, desc, action], i) => '<div class="setup-step ' + (done ? 'complete' : '') + '"><span class="step-number">' + (done ? icon('check') : String(i + 1).padStart(2, '0')) + '</span><div><strong>' + title + '</strong><p>' + desc + '</p></div><button class="text-button" data-action="' + (done?['accounts','imports','review'][i]:action) + '">' + (done ? 'View' : 'Start') + ' ' + icon('arrow-right') + '</button></div>').join('') + '</div></article>';
  const hero = hasActivity ? '<article class="panel review-focus"><div><div class="card-kicker">YOUR NEXT CHAPTER</div><h2>' + (review.length ? review.length + ' small decisions.<br>A clearer set of books.' : 'A little clarity goes a long way.') + '</h2><p>' + (review.length ? 'Take a moment to check the details. Every reviewed transaction brings your books into focus.' : 'Your review queue is clear for this period. Add your next statement whenever you’re ready.') + '</p>' + button(review.length ? 'Open review queue' : 'Import a statement', review.length ? 'review' : 'import', 'ink', 'arrow-right') + '</div><div class="review-orbit" aria-hidden="true"><strong>' + review.length + '</strong><i class="orbit-dot"></i></div></article>' : '<article class="panel onboarding-card"><div class="onboarding-copy"><div class="card-kicker">A FRESH PAGE</div><h2>Good books begin<br>with one statement.</h2><p>Bring in your expenses. We’ll keep the details together so you can make sense of every transaction.</p>' + button('Import a statement', 'import', 'primary', 'import') + '</div>' + statementArt() + '</article>';
  const categoryBody = groups.length ? '<div class="category-list">' + groups.slice(0, 4).map(([name, sum]) => '<div class="category-entry"><div class="category-entry-head"><span>' + e(name) + '</span><strong>' + money(sum) + '</strong></div><div class="category-track"><i style="width:' + Math.max(3, Math.min(100, Math.abs(sum) / Math.max(...groups.map(g => Math.abs(g[1])), 1) * 100)) + '%"></i></div></div>').join('') + '</div>' : emptyState('tag', 'A place for every expense', 'Your category breakdown will take shape as you review and include transactions.', '', 'compact');
  const recent = tx.slice(0, 4).map(t => '<a href="#transactions" class="recent-item" data-edit="' + e(t.id) + '"><span class="merchant-mark">' + e((t.merchant || t.description)[0]?.toUpperCase()) + '</span><div><strong>' + e(t.merchant || t.description) + '</strong><small>' + e(formatDate(t.date)) + ' · ' + e(t.category) + '</small></div><span class="recent-amount">' + signedMoney(t) + '<small>' + (isReview(t) ? 'Needs review' : included(t) ? 'In expense totals' : 'Outside totals') + '</small></span></a>').join('');
  return heading('A clear view of your books.', 'A little order today. A lot less work later.', '<span class="overview-date">' + e(new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })) + '</span>' + button('Import statement', 'import', 'primary', 'plus'), 'THE BIG PICTURE') +
    '<div class="scope-strip"><span class="scope-name">' + icon('business') + e(workspaceName()) + '</span>' + yearSelect() + '</div><div class="metrics"><article class="metric accent-metric"><div class="metric-label">' + icon('reports') + 'Included expenses</div><div class="metric-value">' + money(total) + '</div><div class="metric-note">' + reports.length + ' reviewed transaction' + (reports.length === 1 ? '' : 's') + ' in your totals</div></article><article class="metric"><div class="metric-label">' + icon('review') + 'Ready for your review</div><div class="metric-value">' + review.length + '</div><div class="metric-note">' + (review.length ? 'A few details to put in place' : 'Nothing waiting for you right now') + '</div><a href="#review" class="metric-link" aria-label="Open review queue">' + icon('arrow-up-right') + '</a></article><article class="metric"><div class="metric-label">' + icon('folder') + 'Statements on file</div><div class="metric-value">' + documents.length + '</div><div class="metric-note">Originals preserved on this device</div><a href="#imports" class="metric-link" aria-label="View imports">' + icon('arrow-up-right') + '</a></article></div><div class="workspace-grid">' + hero + setup + '</div><div class="overview-bottom-grid"><article class="panel recent-panel"><div class="panel-heading"><div><h2>Recent activity</h2><p>The latest entries in your books</p></div><a href="#transactions" class="text-button">View all ' + icon('arrow-right') + '</a></div>' + (recent || emptyState('receipt', 'Your first entry is a fresh start.', 'Imported transactions will appear here, with their source always a click away.', '', 'compact')) + '</article><article class="panel"><div class="panel-heading"><div><h2>Where it all goes</h2><p>Expenses by category</p></div>' + icon('tag') + '</div>' + categoryBody + '<div class="category-footer"><span>Reviewed & included only</span><a href="#reports" class="text-button">Reports ' + icon('arrow-right') + '</a></div></article></div>';
}

function filteredLedger() {
  let rows = scopedTransactions().filter(inYear);
  if (state.page === 'review') rows = rows.filter(isReview);
  else if (state.tab === 'approved') rows = rows.filter(t => t.status === 'approved');
  else if (state.tab === 'excluded') rows = rows.filter(t => t.excluded);
  if (state.account) rows = rows.filter(t => t.accountId === state.account);
  if (state.document) rows = rows.filter(t => t.documentId === state.document);
  if (state.query) { const alternatives=state.query.toLowerCase().split('|').map(q=>q.trim().split(/\s+/).filter(Boolean)).filter(q=>q.length);rows=rows.filter(t=>{const text=[t.merchant,t.description,t.account,t.category,t.sourceCategory,t.sourceFilename,t.notes].filter(Boolean).join(' ').toLowerCase();return alternatives.some(words=>words.every(word=>text.includes(word)));}); }
  return quickFilters(rows);
}
function ledgerRow(t) {
  const selected = state.selected.has(t.id), unset = /uncategorized/i.test(t.category);
  const account=state.accounts.find(a=>a.id===t.accountId);
  const books=t.classification==='business'?businessName(t.businessId):t.classification==='unknown'?'Unassigned':t.classification[0].toUpperCase()+t.classification.slice(1);
  return '<tr data-edit="' + e(t.id) + '" class="' + (selected ? 'selected' : '') + '"><td class="select-cell"><input type="checkbox" data-select="' + e(t.id) + '" aria-label="Select ' + e(t.merchant || t.description) + '"' + (selected ? ' checked' : '') + '></td><td><div class="table-merchant"><span class="merchant-mark">' + e((t.merchant || t.description)[0]?.toUpperCase()) + '</span><span><button class="transaction-name-button" data-edit="'+e(t.id)+'">' + e(t.merchant || t.description) + '</button><small class="desktop-detail">' + e(t.duplicateCandidate ? 'Possible duplicate · ' + t.detail : t.detail) + '</small><small class="mobile-detail">'+e(formatDate(t.date,{month:'short',day:'numeric'}))+' · '+(isReview(t)?'Needs review':included(t)?'Included':'Outside totals')+'</small></span></div></td><td class="cell-date date-col">' + e(formatDate(t.date, { month: 'short', day: 'numeric' })) + '<span class="cell-secondary">' + e(t.date?.slice(0, 4)) + '</span></td><td class="category-col"><button type="button" data-quick-category="' + e(t.id) + '" class="category-tag category-edit-button ' + (unset ? 'unset' : '') + '" title="Quick categorize">' + e(t.category) + '</button><span class="cell-secondary books-name" title="'+e(books)+'">' + e(books) + '</span>' + quickSuggestion(t) + '</td><td class="cell-account account-col"><span>'+e(account?.nickname||t.account)+'</span><span class="cell-secondary">'+(account?.last_four?'•••• '+e(account.last_four):'Source account')+'</span></td><td class="amount ' + (t.direction === 'credit' ? 'credit' : t.direction === 'unknown' ? 'unknown' : '') + '">' + signedMoney(t) + '</td><td class="state-col">' + statusMarkup(t) + '<span class="cell-secondary">' + (included(t) ? 'In expense totals' : 'Outside totals') + '</span></td><td class="row-arrow">' + icon('chevron') + '</td></tr>';
}
function renderLedger() {
  const isQueue = state.page === 'review', tx = scopedTransactions().filter(inYear);
  return heading(isQueue ? 'A little review. A lot of clarity.' : 'Every transaction, accounted for.', isQueue ? 'Check the source, choose where it belongs, and decide what enters your totals.' : 'The complete record, including personal items, transfers, and exclusions.', yearSelect() + button('Import statement', 'import', 'primary', 'plus'), isQueue ? 'PUT THE DETAILS IN PLACE' : 'YOUR EXPENSE LEDGER') +
    (state.document ? '<div class="filter-note">' + icon('file') + 'Showing rows from ' + e(state.documents.find(d => d.id === state.document)?.filename || 'a statement') + '<button class="text-button" data-action="clear-document">Clear filter</button></div>' : '') +
    quickWorkbench() + '<section class="panel table-panel"><div class="table-toolbar">' + (isQueue ? '<span class="filter-note" style="margin:0">' + icon('review') + '<span id="queue-scope-count"></span></span>' : '<div class="segmented" role="group" aria-label="Transaction status">' + [['all','All transactions',tx.length],['approved','Reviewed',tx.filter(t=>t.status==='approved').length],['excluded','Excluded',tx.filter(t=>t.excluded).length]].map(([key,label,count])=>'<button data-tab="' + key + '" class="' + (state.tab===key?'active':'') + '" aria-pressed="' + (state.tab===key) + '">' + label + '<span>' + count + '</span></button>').join('') + '</div>') +
    '<div class="toolbar-filters"><label class="search-field">' + icon('search') + '<input id="transaction-search" type="search" placeholder="Search merchant, notes… use | for OR" value="' + e(state.query) + '" aria-label="Search transactions"></label><select class="filter-select" id="account-filter" aria-label="Filter by account"><option value="">All accounts</option>' + scopedAccounts().map(a=>'<option value="' + e(a.id) + '"' + (state.account===a.id?' selected':'') + '>' + e(a.nickname) + '</option>').join('') + '</select></div></div><div id="batch-bar" class="batch-bar" hidden></div><div id="merchant-groups" hidden></div><div class="table-wrap" id="ledger-table-wrap"><table class="ledger-table"><thead><tr><th class="select-cell"><input type="checkbox" id="select-all" aria-label="Select all visible transactions"></th><th>Transaction</th><th class="date-col">Date</th><th class="category-col">Category & books</th><th class="account-col">Source account</th><th style="text-align:right">Amount</th><th class="state-col">Review state</th><th></th></tr></thead><tbody id="ledger-body"></tbody></table></div><div class="table-caption"><span id="ledger-count"></span><span>Click any transaction to review its details</span></div></section>';
}
function updateLedger() {
  const body = $('#ledger-body'); if (!body) return;
  const rows = filteredLedger();
  const visibleIds = new Set(rows.map(t=>t.id));state.selected.forEach(id=>{if(!visibleIds.has(id))state.selected.delete(id);});
  body.innerHTML = rows.length ? rows.map(ledgerRow).join('') : '<tr><td colspan="8" style="padding:0">' + emptyState(state.page==='review'?'check':'transactions', state.page==='review'?'A clear queue. A clearer mind.':'No transactions here yet.', state.query || state.account || state.document ? 'Try a different search, account, or year.' : state.page==='review'?'You have no transactions waiting for review in this workspace.':'Import a statement to start building your expense ledger.', !state.query && !state.account ? button('Import a statement','import','secondary','import') : '', 'large') + '</td></tr>';
  $('#ledger-count').textContent = rows.length + ' transaction' + (rows.length===1?'':'s') + (state.year==='all'?'':' · '+state.year);
  if($('#queue-scope-count'))$('#queue-scope-count').textContent=rows.length+' transaction'+(rows.length===1?'':'s')+' awaiting a decision';
  const selectAll = $('#select-all'); selectAll.checked = rows.length>0 && rows.every(t=>state.selected.has(t.id)); selectAll.indeterminate = !selectAll.checked && rows.some(t=>state.selected.has(t.id));
  updateBatchBar();
  updateQuickGroups(rows);
}
function updateBatchBar() {
  const bar = $('#batch-bar'); if (!bar) return;
  const count = state.selected.size; bar.hidden = !count;
  bar.innerHTML = '<span><strong>' + count + '</strong> selected <small class="quick-shortcut">C to categorize</small></span><button class="button button-ink" data-quick="categorize">Categorize & assign</button>' + ([...state.selected].some(id=>state.suggestions?.[id]&&!state.suggestions[id].conflict)?'<button class="button button-secondary" data-quick="suggestions">Apply rule suggestions</button>':'') + '<button class="button button-secondary" data-batch="personal">Personal</button><button class="button button-secondary" data-batch="transfer">Transfer</button><button class="button button-secondary" data-batch="exclude">Exclude</button><button class="button button-secondary" data-batch="approve">Review only</button><button class="button button-ink" data-batch="include">Review & include</button><button class="icon-button" data-action="clear-selection" aria-label="Clear selection">' + icon('close') + '</button>';
}

function renderImports() {
  const docs = scopedDocuments();
  return heading('Bring the paperwork together.', 'Import a statement once. Keep the original and every extracted row within reach.', button('Choose a file','import','primary','plus'), 'YOUR SOURCE LIBRARY') +
    '<section class="upload-zone" id="dropzone" role="button" tabindex="0" aria-label="Choose a CSV or Excel statement to import"><span class="upload-corner">A PLACE FOR THE ORIGINALS</span><div><div class="empty-graphic">' + icon('import') + '</div><h2>Drop your statement here.</h2><p>Or choose a file from your computer. We’ll preview it together.</p><span class="button button-secondary">' + icon('folder') + 'Choose a CSV or Excel file</span><small>CSV & XLSX statements · up to 20 MB · processed on this device</small></div></section><div class="section-title-row"><h2>Imported statements</h2><small>' + docs.length + ' original' + (docs.length===1?'':'s') + ' retained</small></div><section class="panel">' + (docs.length ? '<div class="table-wrap"><table><thead><tr><th>Source document</th><th>Imported</th><th>Transactions</th><th>Source account</th><th></th></tr></thead><tbody>' + docs.map(d => { const rows = state.transactions.filter(t=>t.documentId===d.id), accountIds=[...new Set(rows.map(t=>t.account))]; return '<tr><td><div class="file-label"><span class="file-badge">' + e(d.format.toUpperCase()) + '</span><span><strong>' + e(d.filename) + '</strong><small>Original retained · ' + e(d.file_hash?.slice(0,12)) + '</small></span></div></td><td class="cell-date">' + e(formatDate(d.imported_at)) + '</td><td>' + rows.length + '<span class="cell-secondary">' + rows.filter(isReview).length + ' awaiting review</span></td><td class="cell-account">' + e(accountIds.join(', ') || '—') + '</td><td><button class="text-button" data-document="' + e(d.id) + '">View rows ' + icon('arrow-right') + '</button></td></tr>'; }).join('') + '</tbody></table></div>' : emptyState('folder','A library starts with one document.','Your imported originals will live here, linked to the transactions they contain.','','compact')) + '</section><div class="info-strip">' + icon('shield') + '<p><strong>Evidence, always attached.</strong> Original statements stay on your computer. New rows enter the review queue before they affect any expense total.</p></div>';
}
function renderAccounts() {
  const accounts = scopedAccounts();
  return heading('Know where it came from.', 'Keep source accounts organized, even when an expense belongs to another business.', button('Add account','add-account','primary','plus'), 'SOURCE ACCOUNTS') +
    '<div class="scope-strip"><span>' + accounts.length + ' source account' + (accounts.length===1?'':'s') + '</span><span>Nickname & last four digits only</span></div><div class="account-grid">' + accounts.map(a => '<article class="account-card"><div class="account-card-top"><span class="account-monogram">' + e((a.institution || a.nickname)[0]?.toUpperCase()) + '</span><span class="account-type">' + e(a.account_type==='credit'?'Credit card':a.account_type) + '</span></div><h2>' + e(a.nickname) + '</h2><div class="account-number">' + (a.last_four?'•••• '+e(a.last_four):e(a.institution || 'No account digits stored')) + '</div><div class="account-card-footer"><span>' + e(businessName(a.business_id)) + '</span><span>' + state.transactions.filter(t=>t.accountId===a.id).length + ' entries</span></div></article>').join('') + '<button class="account-card add-account-card" data-action="add-account"><div>' + icon('plus') + '<strong>' + (accounts.length?'Another account, one place.':'Add your first source account.') + '</strong><p>Checking, savings, or credit card</p></div></button></div><div class="info-strip">' + icon('accounts') + '<p><strong>The source stays with the transaction.</strong> A personal card can pay a business expense. Assign the transaction to the right business when you review it.</p></div>';
}
function renderReports() {
  const rows=reportRows(), total=rows.reduce((n,t)=>n+contribution(t),0), groups=totalsByCategory(rows), pending=scopedTransactions().filter(t=>isReview(t)&&inYear(t)).length;
  const personal=state.workspace==='personal';
  return heading('Ready when you need the numbers.', 'A reviewable expense ledger for your records and tax preparation.', yearSelect(), 'REPORTS & EXPORTS') +
    '<section class="report-summary"><div><span class="eyebrow">' + e(workspaceName()) + ' / ' + (state.year==='all'?'ALL YEARS':state.year) + '</span><div class="report-total">' + money(total) + '</div><p>' + rows.length + ' approved business transaction' + (rows.length===1?'':'s') + ' included in expense totals</p></div><button class="button" data-action="export"' + (!rows.length||personal?' disabled':'') + '>' + icon('download') + 'Export expense ledger</button></section><div class="report-grid"><section class="panel"><div class="panel-heading"><div><h2>Category summary</h2><p>Refunds and reviewed credits reduce category totals</p></div>' + icon('reports') + '</div>' + (groups.length?'<div style="padding:16px 0 4px">' + groups.map(([name,amount],i)=>'<div class="report-category-row"><span class="category-index">' + String(i+1).padStart(2,'0') + '</span><strong>' + e(name) + '</strong><span>' + money(amount) + '</span></div>').join('') + '</div>':emptyState('reports','The numbers will come together.','Review and include business transactions to build your expense summary.',button('Go to review queue','review','secondary','arrow-right'),'large')) + '</section><aside class="panel report-details"><h2>Behind the report</h2><div class="report-detail-row"><span>Business scope</span><strong>' + e(workspaceName()) + '</strong></div><div class="report-detail-row"><span>Reporting period</span><strong>' + (state.year==='all'?'All recorded years':state.year) + '</strong></div><div class="report-detail-row"><span>Included transactions</span><strong>' + rows.length + '</strong></div><div class="report-detail-row"><span>Source accounts</span><strong>' + new Set(rows.map(t=>t.accountId)).size + '</strong></div><div class="report-detail-row"><span>Still awaiting review</span><strong>' + pending + '</strong></div><div class="report-detail-row"><span>File format</span><strong>Excel · 7 worksheets</strong></div><div class="info-strip">' + icon('file') + '<p>The ledger includes source accounts, document names, and source rows. Personal items, transfers, and excluded entries stay outside expense totals.</p></div></aside></div><p class="export-note">Prepared for bookkeeping and tax preparation support. Review tax treatment with your preparer.</p>';
}
function renderSettings() {
  return heading('A place for everything.', 'Your local storage, businesses, and app information.', '', 'DATA & STORAGE') +
    '<div class="settings-grid"><section class="panel settings-panel"><h2>Saved on this computer</h2><span class="status ' + (state.connected?'':'review') + '"><i></i>' + (state.connected?'Connected to your local database':'Local server is not connected') + '</span><p>Database</p><code>' + e(state.health?.database || 'Start the local app to view its database location.') + '</code><p>Original statements & app data</p><code>' + e(state.health?.dataDirectory || 'Available when the local server is running.') + '</code><button class="button button-secondary" style="margin-top:16px" data-action="choose-database">Choose or move books</button><h2>A copy for safekeeping</h2><p>Download a consistent copy of the database and retained originals. Store the ZIP somewhere safe. Restore instructions are in the README.</p><button class="button button-secondary" data-action="backup">Download backup</button>' + renderConfirmedLayouts() + '<h2>Recent review actions</h2><div id="recent-actions">Open settings to view review history.</div></section><section class="panel settings-panel"><h2>Your business workspaces</h2><p>Each business has its own categories. Accounts and transactions keep their source identity.</p><ul class="settings-list">' + state.businesses.map(b=>'<li>' + icon('business') + '<span>' + e(b.legal_name) + '</span></li>').join('') + '</ul><button class="text-button" data-action="add-business" style="margin-top:10px">Add a business ' + icon('plus') + '</button><div class="info-strip" style="margin-top:28px">' + icon('shield') + '<p>All normal processing happens on this device. No bank sign-in or cloud service is required.</p></div></section></div>';
}

function render() {
  if(state.setupRequired||state.setupEditing){renderBooksSetup();return;}
  setupGate(false);
  const renderers={overview:renderOverview,review:renderLedger,transactions:renderLedger,imports:renderImports,accounts:renderAccounts,reports:renderReports,settings:renderSettings};
  $('#page').innerHTML=(renderers[state.page]||renderOverview)();
  $('#breadcrumb').textContent=pageNames[state.page];
  $$('[data-nav]').forEach(a=>{a.classList.toggle('active',a.dataset.nav===state.page); if(a.dataset.nav===state.page) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');});
  $('#review-badge').textContent=scopedTransactions().filter(isReview).length;
  $('#import-dot').hidden=!scopedDocuments().length;
  if(state.page==='transactions'||state.page==='review') updateLedger();
  $$('[data-year]').forEach(select=>select.value=state.year);
  hydrateIcons();
  if(state.page==='settings'&&state.connected)loadReviewActions();
}
function route() { const page=location.hash.slice(1);state.page=pageNames[page]?page:'overview';state.selected.clear();document.body.classList.remove('nav-open');$('#menu-button').setAttribute('aria-expanded','false');render();window.scrollTo(0,0); }
function navigate(page) { if(location.hash==='#'+page){state.page=page;render();}else location.hash=page; }
function toast(message) { $('#toast-message').textContent=message;$('#toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').hidden=true,5000); }
async function api(path,options={}) {
  if(location.protocol==='file:') throw new Error('Open the app at http://127.0.0.1:8765 to use your database.');
  const response=await fetch(path,{signal:AbortSignal.timeout(10000),...options,headers:{'Content-Type':'application/json',...(state.health?.workspaceId?{'X-Bookkeeper-Workspace':state.health.workspaceId}:{}),...(options.headers||{})}});
  const contentType=response.headers.get('content-type')||'';
  if(!contentType.includes('application/json')) throw new Error('The local app server is not responding.');
  const payload=await response.json();if(!response.ok)throw new Error(payload.error||'The request could not be completed.');return payload;
}
function post(path,body,method='POST') { return api(path,{method,body:JSON.stringify(body)}); }
function connectionUI(error) {
  if(state.setupRequired){$('#connection-banner').hidden=true;return;}
  const status=$('#connection-status');status.className='connection-status '+(state.connected?'connected':'disconnected');status.innerHTML='<i></i>'+(state.connected?'On this device':'Server offline');
  const banner=$('#connection-banner');banner.hidden=state.connected;
  if(!state.connected)banner.innerHTML=icon('warning')+'<div><strong>'+(location.protocol==='file:'?'Open your local workspace.':'Your books are safe. The local server is offline.')+'</strong><p>'+(location.protocol==='file:'?'This file is a preview. Start <code>run_local_bookkeeper.bat</code>, then open the app at its local address.':'Start <code>run_local_bookkeeper.bat</code> and refresh to reconnect to your books.')+'</p></div>'+(location.protocol==='file:'?'<a class="button button-secondary button-small" href="http://127.0.0.1:8765">Open local app '+icon('arrow-right')+'</a>':'<button class="button button-secondary button-small" data-action="refresh">Try again '+icon('refresh')+'</button>');
  if(error)console.info('Local Bookkeeper connection:',error.message);
}
async function loadData({quiet=false}={}) {
  $('#refresh-button').classList.add('is-busy');
  try {
    const health=await api('/api/health');state.health=health;
    if(health.setupRequired){Object.assign(state,{setupRequired:true,connected:false,ready:true,transactions:[],accounts:[],businesses:[],categories:[],documents:[],rules:[],suggestions:{},importProfiles:[]});booksSetup.info=health.setup;render();return;}
    const [transactions,accounts,businesses,categories,documents,rules,suggestions,importProfiles]=await Promise.all(['/api/transactions','/api/accounts','/api/businesses','/api/categories','/api/documents','/api/rules','/api/suggestions','/api/import-profiles'].map(path=>api(path)));
    Object.assign(state,{health,transactions,accounts,businesses,categories,documents,rules,suggestions,importProfiles,setupRequired:false,connected:true,ready:true});
    if(!['all','personal',...businesses.map(b=>b.id)].includes(state.workspace))state.workspace='all';
    populateWorkspaces();connectionUI();render();if(!quiet)toast('Your books are up to date.');
  } catch(error) {state.connected=false;state.ready=true;connectionUI(error);render();if(!quiet&&location.protocol!=='file:')toast(error.message);}
  finally {$('#refresh-button').classList.remove('is-busy');}
}
function populateWorkspaces() {
  $('#workspace-select').innerHTML='<option value="all">All businesses</option>'+state.businesses.map(b=>'<option value="'+e(b.id)+'">'+e(b.display_name)+'</option>').join('')+'<option value="personal">Personal holding</option>';
  $('#workspace-select').value=state.workspace;
}
function requireConnection() { if(state.connected)return true;toast('Start the local app server and open http://127.0.0.1:8765 to save changes.');return false; }
function accountOptions(selected='') { return '<option value="">Choose the source account</option>'+state.accounts.map(a=>'<option value="'+e(a.id)+'"'+(selected===a.id?' selected':'')+'>'+e(accountName(a))+'</option>').join(''); }
function businessOptions(selected='',personal=false) { return (personal?'<option value="">Personal or shared account</option>':'')+state.businesses.map(b=>'<option value="'+e(b.id)+'"'+(selected===b.id?' selected':'')+'>'+e(b.display_name)+'</option>').join(''); }
function showDialog(id) { const dialog=$('#'+id);document.body.classList.remove('nav-open');$('#menu-button').setAttribute('aria-expanded','false');$('.form-error',dialog).hidden=true;if(!dialog.open)dialog.showModal();hydrateIcons(dialog); }
function showError(form,error) { const target=$('.form-error',form);target.textContent=error.message||String(error);target.hidden=false;target.scrollIntoView({block:'nearest',behavior:'smooth'}); }
function busy(form,value) { $$('button[type=submit]',form).forEach(button=>{button.disabled=value;button.classList.toggle('is-busy',value);});form.setAttribute('aria-busy',String(value)); }
function openAccount() { if(!requireConnection())return;$('#account-business').innerHTML=businessOptions(state.workspace==='all'||state.workspace==='personal'?'':state.workspace,true);showDialog('account-dialog'); }
function openBusiness() { if(!requireConnection())return;showDialog('business-dialog'); }
async function readStatement(file) {
  if(!requireConnection()||!file)return;
  if(state.loadingFile)return;
  if(!/\.(csv|xlsx)$/i.test(file.name))return toast('Choose a CSV or XLSX statement.');
  if(file.size>20*1024*1024)return toast('Choose a statement smaller than 20 MB.');
  state.loadingFile=true;toast('Reading your statement on this device…');
  try {
    const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
    state.preview=await post('/api/imports/preview',{filename:file.name,contentBase64:btoa(binary)});
    openImportPreview();
  }catch(error){toast(error.message);}finally{state.loadingFile=false;}
}
function openImportPreview() {
  const p=state.preview;if(!p)return;
  $('#import-description').textContent=p.filename+' · Check the extracted rows and select the account this statement came from.';
  const warnings=[];
  if(p.reconciliation?.matched)warnings.push('Statement totals match the workbook summary.');
  if(p.requiresMappingConfirmation)warnings.push('American Express layout detected. Confirm the amount mapping below. Negative merchant credits still require review.');
  if(p.alreadyImported)warnings.push('<strong>This exact file is already in your library.</strong> Importing again will add another set of rows for duplicate review.');
  if(p.warnings.total)warnings.push(e(p.warnings.total)+' parsing warning'+(p.warnings.total===1?'':'s')+'. Check dates, amounts, and descriptions before including these rows in totals.');
  if(p.possibleDuplicates)warnings.push(e(p.possibleDuplicates)+' rows may match existing activity.');
  $('#import-warning').innerHTML=warnings.map(text=>'<div class="callout">'+icon('warning')+'<p>'+text+'</p></div>').join('')+importExplanationMarkup(p);
  $('#import-metrics').innerHTML=[['Rows extracted',p.rowCount],['Money out',money(p.debitCents)],['Money in',money(p.creditCents)],['Warnings',p.warnings.total]].map(([label,value])=>'<div class="import-metric"><span>'+label+'</span><strong>'+value+'</strong></div>').join('');
  $('#import-preview').innerHTML='<table><thead><tr><th>Source row</th><th>Date</th><th>Description</th><th style="text-align:right">Amount</th></tr></thead><tbody>'+p.rows.map(t=>'<tr><td>'+t.sourceRow+'</td><td>'+e(t.date||'Needs review')+'</td><td>'+e(t.description)+importRowReason(t)+'</td><td class="amount">'+(t.direction==='unknown'?'? ':t.direction==='credit'?'+ ':'− ')+money(t.amountCents)+'</td></tr>').join('')+'</tbody></table>';
  $('#import-account').innerHTML='<option value="">Choose the source account…</option>'+accountOptions();
  $('#mapping-confirmation').hidden=false;
  $('#mapping-confirm').required=true;$('#mapping-confirm').checked=false;
  $('#mapping-confirm-label').textContent='I confirm the source columns, selected rows and amount interpretation shown above.';
  $('#duplicate-confirmation').hidden=!p.alreadyImported;
  $('#duplicate-confirm').required=!!p.alreadyImported;$('#duplicate-confirm').checked=false;
  showDialog('import-dialog');
  updateLayoutMemory();
}

function setCategories(businessId,selected='') {
  const names=[...new Set(state.categories.filter(c=>!c.business_id||c.business_id===businessId).map(c=>c.name))];
  if(selected&&!names.includes(selected))names.push(selected);
  $('#edit-category').innerHTML=names.sort().map(name=>'<option'+(name===selected?' selected':'')+'>'+e(name)+'</option>').join('');
}
function syncEditor() {
  const form=$('#transaction-form'),classification=new FormData(form).get('classification'),kind=form.elements.kind.value,direction=form.elements.direction.value;
  $('#edit-business-field').hidden=classification!=='business';
  const valid=classification==='business'&&((direction==='debit'&&['expense','fee'].includes(kind))||(direction==='credit'&&kind==='refund'));
  form.elements.includeInTotals.disabled=!valid;if(!valid)form.elements.includeInTotals.checked=false;
  $('#include-help').textContent=valid?'Inclusion is your explicit decision. Saving marks the transaction reviewed.':classification!=='business'?'Personal items and transfers remain outside business expense totals.':'Choose a transaction kind and money movement before including it in expense totals.';
}
function openEditor(id) {
  const t=state.transactions.find(tx=>tx.id===id);if(!t)return;
  const form=$('#transaction-form');form.reset();
  $('#editor-title').textContent=t.merchant||t.description;
  form.elements.id.value=t.id;form.elements.description.value=t.description;form.elements.date.value=/^\d{4}-\d{2}-\d{2}$/.test(t.date)?t.date:'';form.elements.amount.value=(t.amountCents/100).toFixed(2);
  $('#edit-account').innerHTML=accountOptions(t.accountId);
  const business=t.businessId||(!['all','personal'].includes(state.workspace)?state.workspace:state.businesses[0]?.id||'');
  $('#edit-business').innerHTML=businessOptions(business);
  form.elements.direction.value=t.direction;form.elements.kind.value=t.kind;form.elements.notes.value=t.notes||'';
  const radio=$('input[name=classification][value="'+t.classification+'"]',form);if(radio)radio.checked=true;
  setCategories(business,t.category);syncEditor();form.elements.includeInTotals.checked=included(t);
  $('#editor-amount').innerHTML='<strong>'+signedMoney(t)+'</strong>'+statusMarkup(t);
  $('#editor-warnings').innerHTML=t.duplicateOf?'<div class="callout"><p>This is a confirmed duplicate of '+e(t.duplicateOf)+'. It remains outside expense totals.</p></div>':t.duplicateCandidate?'<div class="callout">'+icon('warning')+'<p><strong>Possible duplicate.</strong> This matches another transaction on the same source account. Compare the evidence before including it in totals.</p></div>':'';
  $('#source-evidence').innerHTML=[['Original document',t.sourceFilename||'Manual entry'],['Statement category',t.sourceCategory||'—'],['Source sheet',t.sourceSheet||'—'],['Source row',t.sourceRow||'—'],['Original amount',t.rawAmountText||'—'],['Source cents',t.sourceAmountCents??'—'],['Source account',t.account],['Transaction ID',t.id]].map(([label,value])=>'<dt>'+label+'</dt><dd>'+e(value)+'</dd>').join('');
  if(t.duplicateCandidate&&!t.duplicateOf){
    const other=state.transactions.find(r=>r.id===t.duplicateCandidate);
    $('#editor-warnings').innerHTML+='<p>'+e(other?.sourceFilename||'Other document')+' · row '+e(other?.sourceRow||'—')+' · '+e(other?.date||'')+' · '+e(other?.description||'')+'</p><div class="modal-footer"><button type="button" class="button button-secondary" data-duplicate="distinct" data-row="'+e(t.id)+'" data-canonical="'+e(t.duplicateCandidate)+'">Keep both as distinct</button><button type="button" class="button button-secondary" data-duplicate="duplicate" data-row="'+e(t.id)+'" data-canonical="'+e(t.duplicateCandidate)+'">Mark this row duplicate</button></div>';
  }
  $('#transaction-history').textContent='Loading history…';
  api('/api/transactions/'+encodeURIComponent(id)+'/history').then(rows=>{if(form.elements.id.value!==id)return;$('#transaction-history').innerHTML=rows.length?rows.map(r=>'<p><strong>'+e(r.action)+' · '+e(r.field_name)+'</strong><br>'+e(r.old_value)+' → '+e(r.new_value)+'<br><small>'+e(formatDate(r.changed_at))+'</small></p>').join(''):'No review changes yet.';}).catch(error=>{$('#transaction-history').textContent=error.message;});
  loadTransactionExplanation(id);
  showDialog('transaction-dialog');
}
function openBatch(action) {
  const rows=state.transactions.filter(t=>state.selected.has(t.id));if(!rows.length)return;
  state.batchAction=action;
  const definitions={approve:['Mark these transactions reviewed?','This accepts the transaction data while keeping selected rows outside expense totals.'],include:['Review and include these expenses?','Existing business assignments are retained. Unassigned rows will be placed in the business you select.'],personal:['Move these items to Personal?','The source account stays attached. These transactions will remain outside business expense totals.'],transfer:['Mark these as transfers?','The selected rows stay in your ledger for reconciliation and are excluded from expense totals.'],exclude:['Keep these outside the totals?','These rows remain searchable, along with their original source documents.']};
  $('#batch-title').textContent=definitions[action][0];$('#batch-description').textContent=definitions[action][1];
  const invalid=action==='include'?rows.filter(t=>t.direction==='unknown'||['unknown','transfer'].includes(t.kind)||['personal','transfer'].includes(t.classification)||/uncategorized/i.test(t.category)||t.duplicateOf):[];
  const duplicates=rows.filter(t=>t.duplicateCandidate);
  $('#batch-preview').innerHTML='<div class="batch-summary"><div><span>Affected rows</span><strong>'+rows.length+'</strong></div><div><span>Combined amount</span><strong>'+money(rows.reduce((n,t)=>n+t.amountCents,0))+'</strong></div></div><div class="batch-accounts"><strong>Source accounts</strong><ul class="batch-accounts-list">'+[...new Set(rows.map(t=>t.account))].map(a=>'<li>'+e(a)+'</li>').join('')+'</ul></div>'+
    (action==='include'&&rows.some(t=>t.classification==='unknown')?'<label class="field">Business for unassigned rows<select id="batch-business" required>'+businessOptions(!['all','personal'].includes(state.workspace)?state.workspace:state.businesses[0]?.id)+'</select></label>':'')+
    (invalid.length?'<div class="callout">'+icon('warning')+'<p>'+invalid.length+' selected rows need a category, money movement, or transaction classification before inclusion. Review them individually first.</p></div>':'')+
    (duplicates.length?'<div class="callout">'+icon('warning')+'<p>'+duplicates.length+' selected rows match possible duplicates. Review the source evidence before proceeding.</p></div>':'');
  $('#batch-form button[type=submit]').disabled=invalid.length>0;
  showDialog('batch-dialog');
}

document.addEventListener('click',event=>{
  if(document.body.classList.contains('nav-open')&&!event.target.closest('.sidebar,#menu-button')){document.body.classList.remove('nav-open');$('#menu-button').setAttribute('aria-expanded','false');}
  const close=event.target.closest('[data-close]');if(close){$('#'+close.dataset.close).close();return;}
  const edit=event.target.closest('[data-edit]');if(edit&&!event.target.closest('input')){event.preventDefault();openEditor(edit.dataset.edit);return;}
  const batch=event.target.closest('[data-batch]');if(batch){openBatch(batch.dataset.batch);return;}
  const doc=event.target.closest('[data-document]');if(doc){state.document=doc.dataset.document;state.query='';state.account='';state.tab='all';state.year='all';navigate('transactions');return;}
  const tab=event.target.closest('[data-tab]');if(tab){state.tab=tab.dataset.tab;state.selected.clear();render();return;}
  const action=event.target.closest('[data-action]')?.dataset.action;
  if(action==='import'){if(requireConnection())$('#file-input').click();}
  else if(action==='add-account')openAccount();
  else if(action==='add-business')openBusiness();
  else if(action==='review')navigate('review');
  else if(action==='accounts')navigate('accounts');
  else if(action==='imports')navigate('imports');
  else if(action==='close-nav'){document.body.classList.remove('nav-open');$('#menu-button').setAttribute('aria-expanded','false');$('#menu-button').focus();}
  else if(action==='refresh')loadData();
  else if(action==='clear-selection'){state.selected.clear();updateLedger();}
  else if(action==='clear-document'){state.document='';render();}
  else if(action==='backup'){const a=document.createElement('a');a.href='/api/backup';a.download='bookkeeper-backup.zip';a.click();}
  else if(action==='export'){
    const params=new URLSearchParams();if(!['all','personal'].includes(state.workspace))params.set('businessId',state.workspace);if(state.year!=='all')params.set('year',state.year);
    const anchor=document.createElement('a');anchor.href='/api/export.xlsx?'+params;anchor.download='bookkeeper-report.xlsx';anchor.click();
  }
  const zone=event.target.closest('#dropzone');if(zone&&!action&&requireConnection())$('#file-input').click();
});
document.addEventListener('change',event=>{
  const target=event.target;
  if(target.matches('[data-year]')){state.year=target.value;state.selected.clear();render();}
  if(target.id==='account-filter'){state.account=target.value;state.selected.clear();updateLedger();}
  if(target.matches('[data-select]')){target.checked?state.selected.add(target.dataset.select):state.selected.delete(target.dataset.select);target.closest('tr').classList.toggle('selected',target.checked);updateBatchBar();const rows=filteredLedger();$('#select-all').checked=rows.length>0&&rows.every(t=>state.selected.has(t.id));$('#select-all').indeterminate=!$('#select-all').checked&&rows.some(t=>state.selected.has(t.id));}
  if(target.id==='select-all'){filteredLedger().forEach(t=>target.checked?state.selected.add(t.id):state.selected.delete(t.id));updateLedger();}
});
document.addEventListener('input',event=>{if(event.target.id==='transaction-search'){state.query=event.target.value;state.selected.clear();updateLedger();}});
$('#workspace-select').addEventListener('change',event=>{state.workspace=event.target.value;state.selected.clear();state.document='';state.account='';state.query='';try{localStorage.setItem('bookkeeper.workspace',state.workspace);}catch{}render();});
$('#transaction-form').addEventListener('change',event=>{if(['classification','kind','direction'].includes(event.target.name))syncEditor();if(event.target.name==='businessId')setCategories(event.target.value,$('#edit-category').value);});
$('#account-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;busy(form,true);
  try{const data=Object.fromEntries(new FormData(form));data.businessId=data.businessId||null;const saved=await post('/api/accounts',data);await loadData({quiet:true});form.reset();$('#account-dialog').close();if($('#import-dialog').open){$('#import-account').innerHTML=accountOptions(saved.id);}toast('Source account added.');}catch(error){showError(form,error);}finally{busy(form,false);}
});
$('#business-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;busy(form,true);
  try{const saved=await post('/api/businesses',Object.fromEntries(new FormData(form)));state.workspace=saved.id;state.document='';state.account='';state.query='';state.selected.clear();try{localStorage.setItem('bookkeeper.workspace',state.workspace);}catch{}await loadData({quiet:true});$('#business-dialog').close();form.reset();toast('Business workspace created.');}catch(error){showError(form,error);}finally{busy(form,false);}
});
$('#import-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;if(!state.preview)return;busy(form,true);
  try{const saved=await post('/api/imports/commit',{token:state.preview.token,accountId:$('#import-account').value,confirmMapping:$('#mapping-confirm').checked,confirmExtraction:$('#mapping-confirm').checked,rememberLayout:$('#remember-import-layout').checked,allowDuplicate:$('#duplicate-confirm').checked});state.preview=null;$('#import-dialog').close();await loadData({quiet:true});state.workspace='all';try{localStorage.setItem('bookkeeper.workspace','all');}catch{}$('#workspace-select').value='all';state.year='all';state.document=saved.documentId;state.query='';state.account='';navigate('review');toast(saved.rowCount+' transactions imported for review.');}catch(error){showError(form,error);}finally{busy(form,false);}
});
$('#transaction-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;busy(form,true);
  try{
    const data=Object.fromEntries(new FormData(form)),match=data.amount.match(/^(\d+)(?:\.(\d{1,2}))?$/);
    if(!match)throw new Error('Enter an amount with no more than two decimal places.');
    const amountCents=Number(match[1])*100+Number((match[2]||'').padEnd(2,'0'));if(!Number.isSafeInteger(amountCents)||amountCents<=0)throw new Error('Enter a positive amount.');
    const includeInTotals=form.elements.includeInTotals.checked&&!form.elements.includeInTotals.disabled;
    if(includeInTotals&&/uncategorized/i.test(data.category))throw new Error('Choose an expense category before including this transaction in totals.');
    await post('/api/transactions/'+encodeURIComponent(data.id),{description:data.description,merchant:data.description,date:data.date,amountCents,accountId:data.accountId,businessId:data.classification==='business'?data.businessId:null,direction:data.direction,kind:data.kind,classification:data.classification,category:data.category,includeInTotals,notes:data.notes,status:'approved'},'PATCH');
    $('#transaction-dialog').close();await loadData({quiet:true});toast(includeInTotals?'Reviewed and included in expense totals.':'Transaction reviewed and saved outside totals.');
  }catch(error){showError(form,error);}finally{busy(form,false);}
});
$('#batch-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;busy(form,true);
  try{await post('/api/review/batch',{ids:[...state.selected],action:state.batchAction,businessId:$('#batch-business')?.value});state.selected.clear();$('#batch-dialog').close();await loadData({quiet:true});toast('Your review changes were saved.');}catch(error){showError(form,error);}finally{busy(form,false);}
});
$('#file-input').addEventListener('change',event=>{readStatement(event.target.files[0]);event.target.value='';});
document.addEventListener('dragover',event=>{const zone=event.target.closest('#dropzone');if(zone){event.preventDefault();zone.classList.add('drag-over');}});
document.addEventListener('dragleave',event=>{const zone=event.target.closest('#dropzone');if(zone&&!zone.contains(event.relatedTarget))zone.classList.remove('drag-over');});
document.addEventListener('drop',event=>{const zone=event.target.closest('#dropzone');if(zone){event.preventDefault();zone.classList.remove('drag-over');readStatement(event.dataTransfer.files[0]);}});
document.addEventListener('keydown',event=>{if(event.target.id==='dropzone'&&['Enter',' '].includes(event.key)){event.preventDefault();if(requireConnection())$('#file-input').click();}if(event.key==='Escape'){document.body.classList.remove('nav-open');$('#menu-button').setAttribute('aria-expanded','false');}});
$('#refresh-button').addEventListener('click',()=>loadData());
$('#menu-button').addEventListener('click',event=>{event.stopPropagation();const open=document.body.classList.toggle('nav-open');$('#menu-button').setAttribute('aria-expanded',String(open));});
$('.content-shell').addEventListener('click',event=>{if(document.body.classList.contains('nav-open')&&!event.target.closest('#menu-button')){document.body.classList.remove('nav-open');$('#menu-button').setAttribute('aria-expanded','false');}});
$('#dismiss-toast').addEventListener('click',()=>$('#toast').hidden=true);
$('.skip-link').addEventListener('click',event=>{event.preventDefault();$('#main').focus();});
window.addEventListener('hashchange',route);
hydrateIcons();route();loadData({quiet:true});

async function loadReviewActions(){
  const target=$('#recent-actions');if(!target)return;
  try{
    const actions=await api('/api/review/actions');
    if(!target.isConnected)return;
    target.innerHTML=actions.length?actions.slice(0,12).map(a=>'<div class="report-detail-row"><span>'+e(a.description)+'<small class="cell-secondary">'+e(formatDate(a.created_at))+' · '+e(a.status)+'</small></span>'+(a.status==='active'&&a.action_type!=='undo'?'<button class="text-button" data-undo="'+e(a.id)+'">Undo</button>':'')+'</div>').join(''):'No review actions yet.';
  }catch(error){target.textContent=error.message;}
}
document.addEventListener('click',async event=>{
  const undo=event.target.closest('[data-undo]');if(!undo)return;
  undo.disabled=true;
  try{const result=await post('/api/review/undo',{actionId:undo.dataset.undo});await loadData({quiet:true});toast(result.restored.length+' rows restored; '+result.conflicts.length+' later-edited rows kept for review.');}catch(error){toast(error.message);undo.disabled=false;}
});

document.addEventListener('click',async event=>{
  const choice=event.target.closest('[data-duplicate]');if(!choice)return;
  choice.disabled=true;
  try{await post('/api/duplicates/resolve',{transactionId:choice.dataset.row,canonicalId:choice.dataset.canonical,decision:choice.dataset.duplicate});$('#transaction-dialog').close();await loadData({quiet:true});toast('Duplicate decision saved. Both source records retained.');}catch(error){toast(error.message);choice.disabled=false;}
});
