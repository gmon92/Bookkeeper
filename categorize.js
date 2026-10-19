'use strict';

const triage = {sourceCategory:'',category:'',classification:'',direction:'',from:'',to:'',min:'',max:'',focus:'all',sort:'date-desc',view:'rows',merchant:'',sourceGroup:null,grouping:'merchant',groups:[],bulk:null,rule:null};

function merchantFamily(t){
  return (t.merchant||t.description).normalize('NFKC').toUpperCase().replace(/\b\d{4,}\b/g,' ').replace(/[^\p{L}\p{N}]+/gu,' ').trim().replace(/\s+/g,' ') || t.description;
}
function merchantGroupKey(t){return t.accountId+'|'+merchantFamily(t);}
function quickOptions(items,value){return items.map(([id,label])=>'<option value="'+e(id)+'"'+(id===value?' selected':'')+'>'+e(label)+'</option>').join('');}
function quickBase(){let rows=scopedTransactions().filter(inYear);return state.page==='review'?rows.filter(isReview):rows;}
function quickFilters(rows){
  if(triage.sourceCategory)rows=rows.filter(t=>t.sourceCategory===triage.sourceCategory);
  if(triage.category)rows=rows.filter(t=>t.category===triage.category);
  if(triage.classification)rows=rows.filter(t=>t.classification===triage.classification);
  if(triage.direction)rows=rows.filter(t=>t.direction===triage.direction);
  if(triage.from)rows=rows.filter(t=>t.date>=triage.from);
  if(triage.to)rows=rows.filter(t=>t.date<=triage.to);
  if(triage.min!=='')rows=rows.filter(t=>t.amountCents>=Math.round(Number(triage.min)*100));
  if(triage.max!=='')rows=rows.filter(t=>t.amountCents<=Math.round(Number(triage.max)*100));
  if(triage.focus==='uncategorized')rows=rows.filter(t=>!t.category||/uncategorized/i.test(t.category));
  if(triage.focus==='unassigned')rows=rows.filter(t=>t.classification==='unknown');
  if(triage.focus==='suggestions')rows=rows.filter(t=>state.suggestions?.[t.id]&&!state.suggestions[t.id].conflict);
  if(triage.focus==='duplicates')rows=rows.filter(t=>t.duplicateCandidate||t.duplicateOf);
  if(triage.focus==='review')rows=rows.filter(isReview);
  if(triage.merchant)rows=rows.filter(t=>merchantGroupKey(t)===triage.merchant);
  if(triage.sourceGroup!==null)rows=rows.filter(t=>(t.sourceCategory||'')===triage.sourceGroup);
  return rows.sort((a,b)=>triage.sort==='amount-desc'?b.amountCents-a.amountCents:triage.sort==='amount-asc'?a.amountCents-b.amountCents:triage.sort==='merchant'?merchantFamily(a).localeCompare(merchantFamily(b)):triage.sort==='date-asc'?a.date.localeCompare(b.date):b.date.localeCompare(a.date));
}
function quickWorkbench(){
  const rows=quickBase(), counts={all:rows.length,uncategorized:rows.filter(t=>/uncategorized/i.test(t.category)).length,unassigned:rows.filter(t=>t.classification==='unknown').length,suggestions:rows.filter(t=>state.suggestions?.[t.id]&&!state.suggestions[t.id].conflict).length,duplicates:rows.filter(t=>t.duplicateCandidate||t.duplicateOf).length,review:rows.filter(isReview).length};
  const choices=[['all','All'],['uncategorized','Uncategorized'],['unassigned','Unassigned'],['suggestions','Rule suggestions'],['duplicates','Duplicates']];
  if(state.page!=='review')choices.push(['review','Needs review']);
  const active=['sourceCategory','category','classification','direction','from','to','min','max'].some(k=>triage[k]!=='');
  const categories=[...new Set(rows.map(t=>t.category).filter(Boolean))].sort();
  const sourceCategories=[...new Set(rows.map(t=>t.sourceCategory).filter(Boolean))].sort();
  return '<section class="quick-workbench"><div class="quick-heading"><div><h2>Make one decision for many transactions.</h2><p>Filter a set, group repeat merchants, then categorize together.</p></div><button class="button button-secondary button-small" data-quick="rules">'+icon('tag')+'Merchant rules <span class="quick-rule-count">'+(state.rules||[]).filter(r=>r.active).length+'</span></button></div><div class="quick-chips">'+choices.map(([key,label])=>'<button data-quick-focus="'+key+'" aria-pressed="'+(triage.focus===key)+'" class="quick-chip '+(triage.focus===key?'active':'')+'">'+label+' <span>'+counts[key]+'</span></button>').join('')+'</div><details class="quick-filters"'+(active?' open':'')+'><summary>'+icon('search')+'More filters'+(active?' · active':'')+'</summary><div class="quick-filter-grid"><label class="field">Statement category<select data-quick-filter="sourceCategory">'+quickOptions([['','Any statement category'],...sourceCategories.map(c=>[c,c])],triage.sourceCategory)+'</select></label><label class="field">Your category<select data-quick-filter="category">'+quickOptions([['','All categories'],...categories.map(c=>[c,c])],triage.category)+'</select></label><label class="field">Books assignment<select data-quick-filter="classification">'+quickOptions([['','Any assignment'],['unknown','Unassigned'],['business','Business'],['personal','Personal'],['transfer','Transfer']],triage.classification)+'</select></label><label class="field">Money movement<select data-quick-filter="direction">'+quickOptions([['','Any movement'],['debit','Money out'],['credit','Money in'],['unknown','Needs direction']],triage.direction)+'</select></label><label class="field">From date<input type="date" data-quick-filter="from" value="'+e(triage.from)+'"></label><label class="field">To date<input type="date" data-quick-filter="to" value="'+e(triage.to)+'"></label><label class="field">Minimum USD<input type="number" min="0" step="0.01" data-quick-filter="min" value="'+e(triage.min)+'" placeholder="0.00"></label><label class="field">Maximum USD<input type="number" min="0" step="0.01" data-quick-filter="max" value="'+e(triage.max)+'" placeholder="No limit"></label></div></details><div class="quick-view-row"><div class="segmented" aria-label="Transaction display"><button data-quick-view="rows" aria-pressed="'+(triage.view==='rows')+'" class="'+(triage.view==='rows'?'active':'')+'">Transactions</button><button data-quick-view="groups" aria-pressed="'+(triage.view==='groups'&&triage.grouping==='merchant')+'" class="'+(triage.view==='groups'&&triage.grouping==='merchant'?'active':'')+'">Merchant groups</button><button data-quick-view="sourceCategories" aria-pressed="'+(triage.view==='groups'&&triage.grouping==='sourceCategory')+'" class="'+(triage.view==='groups'&&triage.grouping==='sourceCategory'?'active':'')+'">Statement category groups</button></div><label class="quick-sort">Sort<select data-quick-filter="sort" aria-label="Sort transactions">'+quickOptions([['date-desc','Newest first'],['date-asc','Oldest first'],['amount-desc','Largest amount'],['amount-asc','Smallest amount'],['merchant','Merchant A–Z']],triage.sort)+'</select></label><button class="text-button" data-quick="select-results">Select all results</button><button class="text-button" data-quick="reset">Clear filters</button></div>'+(triage.merchant||triage.sourceGroup!==null?'<div class="filter-note">'+(triage.sourceGroup!==null?'Statement category: '+e(triage.sourceGroup||'No statement category'):'Merchant: '+e(triage.merchant.split('|').slice(1).join('|')))+'<button class="text-button" data-quick="clear-merchant">Show all groups</button></div>':'')+'<div id="quick-result-action" hidden></div></section>';
}
function updateQuickGroups(rows){
  const target=$('#merchant-groups');if(!target)return;
  const source=triage.grouping==='sourceCategory';
  const label=t=>source?(t.sourceCategory||'No statement category'):merchantFamily(t);
  const grouped=new Map();for(const t of rows){const key=source?(t.sourceCategory||''):merchantGroupKey(t);if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(t);}
  triage.groups=[...grouped].sort((a,b)=>b[1].length-a[1].length||label(a[1][0]).localeCompare(label(b[1][0])));
  target.hidden=triage.view!=='groups';$('#ledger-table-wrap').hidden=triage.view==='groups';
  const action=$('#quick-result-action');
  action.hidden=triage.view!=='groups'&&!triage.merchant&&triage.sourceGroup===null;
  action.innerHTML='<div><strong>'+rows.length+' listed transactions'+(triage.view==='groups'?' across '+triage.groups.length+(source?' statement category groups':' merchant groups'):'')+'</strong><p>Your category and business choice will apply to every listed transaction. Current filters define this set.</p></div><button class="button button-ink" data-quick="categorize-listed"'+(!rows.length?' disabled':'')+'>Categorize all '+rows.length+'</button>'+(triage.merchant||triage.sourceGroup!==null?'<button class="text-button" data-quick="back-groups">Back to groups</button>':'');
  if(triage.view!=='groups')return;
  target.innerHTML=triage.groups.length?'<div class="merchant-group-intro">'+(source?'Transactions are batched by the category description supplied in the original statement, across merchants and source accounts. Choose a batch to apply one decision to every listed transaction. Blank source categories form their own group.':'Choose Categorize entire group to make one decision for every transaction in that card. View rows lets you inspect the group first. Groups keep source accounts separate.')+'</div><div class="merchant-group-grid">'+triage.groups.map(([key,items],i)=>{
    const t=items[0],selected=items.every(t=>state.selected.has(t.id)),cats=[...new Set(items.map(t=>t.category))],selectedCount=items.filter(t=>state.selected.has(t.id)).length;
    const sourceMerchants=new Set(items.map(merchantFamily)).size;
    return '<article class="merchant-group '+(selected?'selected':'')+'"><div class="merchant-group-top"><input type="checkbox" data-group-select="'+i+'" aria-label="Select '+(source?'statement category group ':'merchant group ')+e(label(t))+'"'+(selected?' checked':'')+'><span class="merchant-group-count">'+items.length+' transaction'+(items.length===1?'':'s')+(selectedCount&&!selected?' · '+selectedCount+' selected':'')+'</span><strong>'+money(items.reduce((n,r)=>n+r.amountCents,0))+'</strong></div><h3>'+e(label(t))+'</h3><p>'+e(source?[...new Set(items.map(r=>r.account))].join(', '):t.account)+'</p>'+(source?'<p class="source-group-merchants">'+sourceMerchants+' merchant'+(sourceMerchants===1?'':'s')+'</p>':'')+'<div class="merchant-group-categories">'+e(cats.length===1?cats[0]:cats.length+' categories')+'</div><div class="merchant-group-actions"><button class="text-button" data-group-open="'+i+'">View rows '+icon('arrow-right')+'</button><button class="button button-ink button-small" data-group-categorize="'+i+'">Categorize entire group ('+items.length+')</button></div></article>';
  }).join('')+'</div>':emptyState('search','No groups match.','Clear a filter or try another search.','','compact');
  $$('[data-group-select]',target).forEach(input=>{const items=triage.groups[Number(input.dataset.groupSelect)][1];input.indeterminate=items.some(t=>state.selected.has(t.id))&&!items.every(t=>state.selected.has(t.id));});
}
function categorizeListed(){
  const rows=filteredLedger();
  const source=triage.grouping==='sourceCategory';
  const label=triage.sourceGroup!==null?'Statement category: '+(triage.sourceGroup||'No statement category'):triage.merchant?merchantFamily(rows[0]||{description:''}):'All listed '+(source?'statement category groups':'merchant groups');
  openCategorize(rows.map(t=>t.id),'categorize',{label,sourceCategory:triage.sourceGroup});
}
function quickSuggestion(t){const s=state.suggestions?.[t.id];return s?'<button class="quick-suggestion '+(s.conflict?'conflict':'')+'" data-suggest-row="'+e(t.id)+'" title="'+e(s.reason)+'">'+icon(s.conflict?'warning':'tag')+e(s.conflict?'Rule conflict':s.category+' suggested')+'</button>':'';}

// The dialogs share the existing visual language and are kept outside re-rendered pages.
document.body.insertAdjacentHTML('beforeend',`
<dialog id="categorize-dialog" class="modal quick-modal"><form id="categorize-form"><div class="modal-top"><span class="eyebrow">QUICK CATEGORIZE</span><button type="button" class="icon-button" data-close="categorize-dialog" aria-label="Close categorization">×</button></div><h2 id="categorize-title">One category. Many rows.</h2><p class="modal-description" id="categorize-description"></p><details id="categorize-scope" class="bulk-scope"><summary id="categorize-scope-summary"></summary><div id="categorize-scope-rows" class="quick-preview-table"></div></details><div id="categorize-controls"><div class="field-grid"><label class="field">Business books<select id="bulk-business" required></select></label><label class="field">Category for every transaction<select id="bulk-category" required></select></label></div><label class="field" id="bulk-custom-field" hidden>New category name<input id="bulk-custom-category" maxlength="100" autocomplete="off" placeholder="e.g. Vehicle maintenance"><span class="field-hint">This category will be created in the selected business books.</span></label><div class="quick-review-options"><label class="quick-check"><input type="checkbox" id="bulk-reviewed"><span><strong>Mark selected transactions reviewed</strong><small>Leave unchecked to save categories for later review.</small></span></label><label class="quick-check"><input type="checkbox" id="bulk-include" disabled><span><strong>Include eligible expenses in business totals</strong><small>Only reviewed business expenses, fees and refunds qualify.</small></span></label></div><details class="quick-remember"><summary>Remember this merchant for next time</summary><label class="quick-check"><input type="checkbox" id="bulk-remember"><span>Save a merchant rule with these changes.</span></label><div class="field-grid"><label class="field">Merchant description contains<input id="bulk-rule-pattern" maxlength="120" placeholder="e.g. SHELL OIL"></label><label class="field">Source account scope<select id="bulk-rule-account"></select></label></div><p class="field-hint">The phrase must match every selected row. Rules suggest a category and business; they never approve or include expenses. Undo reverses transaction changes; saved rules can be disabled in Merchant rules.</p></details></div><div id="categorize-preview" class="quick-preview" hidden></div><p class="form-error" role="alert" hidden></p><div class="modal-footer"><button type="button" class="button button-secondary" data-close="categorize-dialog">Cancel</button><button type="submit" class="button button-primary" id="categorize-submit">Preview changes</button></div></form></dialog>
<dialog id="rules-dialog" class="modal quick-modal"><div class="modal-top"><span class="eyebrow">MERCHANT RULES</span><button type="button" class="icon-button" data-close="rules-dialog" aria-label="Close merchant rules">×</button></div><h2>Teach your books the repeat work.</h2><p class="modal-description">A saved merchant phrase suggests a category for new or unreviewed transactions. Existing approvals stay in place.</p><button class="button button-secondary" data-quick="new-rule">Add merchant rule</button><div id="rules-list"></div><p class="form-error" role="alert" hidden></p></dialog>
<dialog id="rule-editor-dialog" class="modal quick-modal"><form id="rule-editor-form"><div class="modal-top"><span class="eyebrow">MERCHANT RULE</span><button type="button" class="icon-button" data-close="rule-editor-dialog" aria-label="Close rule editor">×</button></div><h2>Recognize a repeat merchant.</h2><label class="field">Merchant description contains<input id="rule-pattern" required minlength="2" maxlength="120" placeholder="e.g. SHELL OIL"></label><label class="field">Source account scope<select id="rule-account" required></select></label><div class="field-grid"><label class="field">Business books<select id="rule-business" required></select></label><label class="field">Suggested category<select id="rule-category" required></select></label></div><div id="rule-preview" class="quick-preview" hidden></div><p class="field-hint">Matching ignores case and punctuation and uses whole words. Reviewed transactions, transfers and confirmed duplicates are not changed. Conflicting rules need your review.</p><p class="form-error" role="alert" hidden></p><div class="modal-footer"><button type="button" class="button button-secondary" data-close="rule-editor-dialog">Cancel</button><button class="button button-primary" type="submit" id="rule-submit">Preview matches</button></div></form></dialog>
`);

function bulkPayload(){
  const b=triage.bulk;
  if(b.mode==='suggestions')return {ids:b.ids,mode:'suggestions'};
  const account=$('#bulk-rule-account').value;
  return {ids:b.ids,mode:'categorize',businessId:$('#bulk-business').value||null,category:$('#bulk-category').value==='__custom__'?$('#bulk-custom-category').value.trim():$('#bulk-category').value,createCategory:$('#bulk-category').value==='__custom__',markReviewed:$('#bulk-reviewed').checked,includeInTotals:$('#bulk-include').checked,rememberRule:$('#bulk-remember').checked,rulePattern:$('#bulk-rule-pattern').value.trim(),ruleAccountId:account==='*'?null:account,ruleAllAccounts:account==='*'};
}
function bulkCategoryOptions(preferred=$('#bulk-category').value){
  const business=$('#bulk-business').value;
  const names=[...new Set(state.categories.filter(c=>(!business||!c.business_id||c.business_id===business)&&!/uncategorized/i.test(c.name)).map(c=>c.name))].sort();
  $('#bulk-category').innerHTML=quickOptions([['','Choose a category'],...names.map(n=>[n,n]),['__custom__','+ Create a new category…']],preferred);
  syncBulkCustom();
}
function syncBulkCustom(){
  const custom=triage.bulk?.mode!=='suggestions'&&$('#bulk-category').value==='__custom__';
  $('#bulk-custom-field').hidden=!custom;$('#bulk-custom-category').disabled=!custom;$('#bulk-custom-category').required=custom;
}
function openCategorize(ids=[...state.selected],mode='categorize',scope=null){
  if(!requireConnection()||!ids.length)return;
  const rows=[...new Set(ids)].map(id=>state.transactions.find(t=>t.id===id)).filter(Boolean);
  if(!rows.length)return;
  if(rows.length>5000){toast('This set has more than 5,000 transactions. Narrow the filters before categorizing.');return;}
  triage.bulk={ids:rows.map(r=>r.id),mode,revision:null,scope};
  $('#categorize-form').reset();$('#categorize-preview').hidden=true;$('#categorize-preview').innerHTML='';
  $('#categorize-title').textContent=mode==='suggestions'?'Put the suggestions in place.':scope?'Categorize all '+rows.length+' transactions.':'One category. Many rows.';
  $('#categorize-description').textContent=(scope?scope.label+' · ':'')+rows.length+' transactions · '+money(rows.reduce((n,t)=>n+t.amountCents,0))+' in activity. '+(mode==='suggestions'?'Preview each rule’s proposed category. Rows stay unapproved and outside totals.':'The same category and business decision will apply to every transaction below.');
  $('#categorize-scope-summary').textContent='See all '+rows.length+' transactions receiving this decision';
  $('#categorize-scope').open=!!scope&&rows.length<=10;
  $('#categorize-scope-rows').innerHTML='<table><thead><tr><th>Transaction / source account</th><th>Date / amount</th><th>Current category / books</th></tr></thead><tbody>'+rows.map(t=>'<tr><td>'+e(t.merchant||t.description)+'<small>'+e(t.account)+'</small></td><td>'+e(formatDate(t.date))+'<small>'+signedMoney(t)+'</small></td><td>'+e(t.category)+'<small>'+e(t.classification==='business'?businessName(t.businessId):t.classification)+'</small></td></tr>').join('')+'</tbody></table>';
  $('#categorize-controls').hidden=mode==='suggestions';
  const businessIds=[...new Set(rows.map(t=>t.businessId))],shared=businessIds.length===1&&businessIds[0],defaultBusiness=!['all','personal'].includes(state.workspace)?state.workspace:shared||'';
  const needsBusiness=rows.some(t=>t.classification!=='business'||!t.businessId);
  $('#bulk-business').innerHTML='<option value="">'+(needsBusiness?'Choose a business':'Keep current business assignments')+'</option>'+businessOptions(defaultBusiness);
  $('#bulk-business').value=defaultBusiness;$('#bulk-business').required=needsBusiness;
  const categories=[...new Set(rows.map(t=>t.category))];
  bulkCategoryOptions(categories.length===1?categories[0]:'');
  if(scope?.sourceCategory){const match=[...$('#bulk-category').options].find(o=>o.value.toLowerCase()===scope.sourceCategory.toLowerCase());$('#bulk-category').value=match?match.value:'__custom__';$('#bulk-custom-category').value=scope.sourceCategory.length<=100?scope.sourceCategory:'';syncBulkCustom();if(!match&&scope.sourceCategory.length>100)$('#bulk-custom-field .field-hint').textContent='The statement label is longer than the 100-character category limit. Enter a shorter category name; the full original label remains in source evidence.';}
  const accounts=[...new Set(rows.map(t=>t.accountId))];
  $('#bulk-rule-account').innerHTML='<option value="">Choose rule scope</option>'+quickOptions(accounts.map(id=>[id,accountName(state.accounts.find(a=>a.id===id))]),accounts.length===1?accounts[0]:'')+'<option value="*">All source accounts</option>';
  const families=[...new Set(rows.map(merchantFamily))];$('#bulk-rule-pattern').value=families.length===1?families[0]:'';
  $('#bulk-include').disabled=true;$('#categorize-submit').textContent='Preview changes for all '+rows.length;$('#categorize-submit').disabled=false;
  $('#bulk-business').disabled=mode==='suggestions';$('#bulk-category').disabled=mode==='suggestions';
  showDialog('categorize-dialog');
}
function invalidateBulk(){if(!triage.bulk)return;triage.bulk.revision=null;triage.bulk.blocked=false;$('#categorize-preview').hidden=true;$('#categorize-submit').textContent='Preview changes for all '+triage.bulk.ids.length;$('#categorize-submit').disabled=false;$('.form-error',$('#categorize-form')).hidden=true;}
function bulkPreviewMarkup(plan){
  return '<div class="batch-summary"><div><span>Rows to change</span><strong>'+plan.applicableCount+' / '+plan.selectedCount+'</strong></div><div><span>Combined activity</span><strong>'+money(plan.amountCents)+'</strong></div></div><p><strong>Accounts:</strong> '+e(plan.accounts.join(', ')||'—')+'<br><strong>Business books:</strong> '+e(plan.businesses.join(', ')||'—')+'</p>'+(plan.newCategories.length?'<p>New categories: '+plan.newCategories.map(c=>e(c.name)+' ('+e(businessName(c.businessId))+')').join(', ')+'</p>':'')+(plan.exceptionCount?'<div class="callout"><p><strong>'+plan.exceptionCount+' rows need attention. No changes will be saved.</strong></p></div>'+plan.exceptions.slice(0,10).map(r=>'<p>'+e(r.description)+' — '+e(r.reason)+'</p>').join(''):'')+'<div class="quick-preview-table"><table><thead><tr><th>Transaction</th><th>Category</th><th>Business / result</th></tr></thead><tbody>'+plan.rows.map(r=>'<tr><td>'+e(r.description)+'<small>'+e(r.date)+' · '+money(r.amountCents)+'</small>'+'<small>'+e(r.reason.split('; rule IDs:')[0])+'</small>'+'</td><td>'+e(r.old.category_name)+' → <strong>'+e(r.new.category_name)+'</strong></td><td>'+e(businessName(r.new.business_id))+'<small>'+e(r.new.status==='approved'?'Reviewed':r.new.status==='suggested'?'Suggested':'Needs review')+' · '+(r.new.include_in_totals?'Included in totals':'Outside totals')+'</small></td></tr>').join('')+'</tbody></table></div><p class="field-hint">Showing '+plan.rows.length+' of '+plan.applicableCount+' proposed changes. '+(triage.bulk.mode==='suggestions'?'Suggestions remain unapproved.':'Only the selected rows will change.')+' Every saved change can be undone in Data & storage.</p>';
}

function renderRuleList(){
  $('#rules-list').innerHTML=(state.rules||[]).length?state.rules.map(r=>'<article class="quick-rule"><div><strong>'+e(r.pattern)+'</strong><p>'+e(r.account_id?accountName(state.accounts.find(a=>a.id===r.account_id)):'All source accounts')+' · '+e(businessName(r.business_id))+'</p><span class="category-tag">'+e(r.category_name)+'</span> <small>'+(r.active?'Active':'Paused')+'</small></div><div><button class="text-button" data-rule-edit="'+e(r.id)+'">Edit</button><button class="text-button" data-rule-toggle="'+e(r.id)+'">'+(r.active?'Pause':'Enable')+'</button></div></article>').join(''):emptyState('tag','One saved decision can do the repeat work.','Create a merchant rule here, or remember a merchant while categorizing a group.','','compact');
}
function openRuleEditor(id=''){
  const rule=state.rules?.find(r=>r.id===id);triage.rule={id,revision:null};$('#rule-editor-form').reset();
  $('#rule-pattern').value=rule?.pattern||'';
  $('#rule-account').innerHTML='<option value="">Choose rule scope</option>'+quickOptions(state.accounts.map(a=>[a.id,accountName(a)]),rule?.account_id||state.account)+'<option value="*">All source accounts</option>';
  if(rule&&!rule.account_id)$('#rule-account').value='*';
  $('#rule-business').innerHTML='<option value="">Choose a business</option>'+businessOptions(rule?.business_id||(!['all','personal'].includes(state.workspace)?state.workspace:''));
  if(!rule&&['all','personal'].includes(state.workspace))$('#rule-business').value='';
  ruleCategoryOptions(rule?.category_name||'');$('#rule-preview').hidden=true;$('#rule-submit').textContent='Preview matches';showDialog('rule-editor-dialog');
}
function ruleCategoryOptions(selected=''){
  const business=$('#rule-business').value;
  $('#rule-category').innerHTML='<option value="">Choose a category</option>'+quickOptions([...new Set(state.categories.filter(c=>(!c.business_id||c.business_id===business)&&!/uncategorized/i.test(c.name)).map(c=>c.name))].sort().map(n=>[n,n]),selected);
}
function rulePayload(){return {id:triage.rule.id||undefined,pattern:$('#rule-pattern').value.trim(),accountId:$('#rule-account').value==='*'?null:$('#rule-account').value,businessId:$('#rule-business').value,category:$('#rule-category').value};}

document.addEventListener('click',event=>{
  const quick=event.target.closest('[data-quick]');
  if(quick){
    const action=quick.dataset.quick;
    if(action==='categorize')openCategorize();
    if(action==='categorize-listed')categorizeListed();
    if(action==='back-groups'){triage.merchant='';triage.sourceGroup=null;triage.view='groups';state.selected.clear();render();}
    if(action==='suggestions')openCategorize([...state.selected],'suggestions');
    if(action==='rules'){renderRuleList();showDialog('rules-dialog');}
    if(action==='new-rule')openRuleEditor();
    if(action==='select-results'){const results=filteredLedger();results.slice(0,5000).forEach(t=>state.selected.add(t.id));updateLedger();if(results.length>5000)toast('Selected the first 5,000 matching rows. Categorize these before selecting the next set.');}
    if(action==='clear-merchant'){triage.merchant='';triage.sourceGroup=null;state.selected.clear();render();}
    if(action==='reset'){Object.assign(triage,{sourceCategory:'',category:'',classification:'',direction:'',from:'',to:'',min:'',max:'',focus:'all',merchant:'',sourceGroup:null});state.query='';state.account='';state.document='';state.tab='all';state.selected.clear();render();}
  }
  const focus=event.target.closest('[data-quick-focus]');if(focus){triage.focus=focus.dataset.quickFocus;state.selected.clear();render();}
  const view=event.target.closest('[data-quick-view]');if(view){const choice=view.dataset.quickView;if(choice!=='rows'){triage.grouping=choice==='sourceCategories'?'sourceCategory':'merchant';triage.merchant='';triage.sourceGroup=null;}triage.view=choice==='rows'?'rows':'groups';state.selected.clear();render();}
  const open=event.target.closest('[data-group-open]');if(open){const key=triage.groups[Number(open.dataset.groupOpen)][0];if(triage.grouping==='sourceCategory'){triage.sourceGroup=key;triage.merchant='';}else{triage.merchant=key;triage.sourceGroup=null;}triage.view='rows';state.selected.clear();render();}
  const group=event.target.closest('[data-group-categorize]');if(group){const rows=triage.groups[Number(group.dataset.groupCategorize)][1];const source=triage.grouping==='sourceCategory';openCategorize(rows.map(r=>r.id),'categorize',{label:source?'Statement category: '+(rows[0].sourceCategory||'No statement category'):merchantFamily(rows[0])+' · '+rows[0].account,sourceCategory:source?rows[0].sourceCategory:null});}
  const category=event.target.closest('[data-quick-category]');if(category){event.stopImmediatePropagation();openCategorize([category.dataset.quickCategory]);}
  const suggest=event.target.closest('[data-suggest-row]');if(suggest){event.stopImmediatePropagation();const s=state.suggestions?.[suggest.dataset.suggestRow];if(s?.conflict){renderRuleList();showDialog('rules-dialog');}else openCategorize([suggest.dataset.suggestRow],'suggestions');}
  const edit=event.target.closest('[data-rule-edit]');if(edit)openRuleEditor(edit.dataset.ruleEdit);
});
document.addEventListener('change',event=>{
  const el=event.target;
  if(el.matches('[data-quick-filter]')){triage[el.dataset.quickFilter]=el.value;state.selected.clear();updateLedger();}
  if(el.matches('[data-group-select]')){triage.groups[Number(el.dataset.groupSelect)][1].forEach(t=>el.checked?state.selected.add(t.id):state.selected.delete(t.id));updateLedger();}
  if(el.closest('#categorize-controls')){if(el.id==='bulk-business')bulkCategoryOptions();if(el.id==='bulk-category')syncBulkCustom();if(el.id==='bulk-reviewed'){$('#bulk-include').disabled=!el.checked;if(!el.checked)$('#bulk-include').checked=false;}invalidateBulk();}
  if(el.closest('#rule-editor-form')){if(el.id==='rule-business')ruleCategoryOptions();triage.rule.revision=null;$('#rule-preview').hidden=true;$('#rule-submit').textContent='Preview matches';}
});
document.addEventListener('input',event=>{
  if(event.target.closest('#categorize-controls'))invalidateBulk();
  if(event.target.closest('#rule-editor-form')){triage.rule.revision=null;$('#rule-preview').hidden=true;$('#rule-submit').textContent='Preview matches';}
});
document.addEventListener('keydown',event=>{
  if(event.ctrlKey||event.metaKey||event.altKey||event.target.closest('input,textarea,select,[contenteditable=true]')||document.querySelector('dialog[open]'))return;
  if(event.key==='/'&&$('#transaction-search')){event.preventDefault();$('#transaction-search').focus();}
  if(event.key.toLowerCase()==='c'&&state.selected.size&&$('#ledger-body')){event.preventDefault();openCategorize();}
});
// This file loads before app.js defines its shared helpers. Register directly
// against the DOM; helpers are available by the time the user submits a form.
document.querySelector('#categorize-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,button=$('#categorize-submit'),payload=bulkPayload();busy(form,true);
  try{
    if(!triage.bulk.revision){const plan=await post('/api/categorization/preview',payload);triage.bulk.revision=plan.revision;$('#categorize-preview').innerHTML=bulkPreviewMarkup(plan);$('#categorize-preview').hidden=false;button.textContent=triage.bulk.mode==='suggestions'?'Apply suggestions':'Apply to all '+plan.applicableCount+' transactions';triage.bulk.blocked=!!plan.exceptionCount||!plan.applicableCount;}
    else{const saved=await post('/api/categorization/apply',{...payload,revision:triage.bulk.revision});state.selected.clear();$('#categorize-dialog').close();await loadData({quiet:true});toast(saved.count+' transactions categorized as '+(triage.bulk.mode==='categorize'?payload.category:'suggested')+'. Undo is available in Data & storage.');}
  }catch(error){triage.bulk.revision=null;button.textContent='Preview changes';triage.bulk.blocked=false;showError(form,error);}finally{busy(form,false);if($('#categorize-dialog').open&&triage.bulk.blocked)button.disabled=true;}
});
document.querySelector('#rule-editor-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,payload=rulePayload();busy(form,true);
  try{
    if(!triage.rule.revision){const preview=await post('/api/rules/preview',payload);triage.rule.revision=JSON.stringify(payload);$('#rule-preview').innerHTML='<p><strong>'+preview.count+' unreviewed transactions match.</strong> '+money(preview.amountCents)+' in activity. Saving this rule will make suggestions available; it will not change transactions.</p><div class="quick-preview-table"><table><thead><tr><th>Matched merchant</th><th>Amount / movement</th><th>Why this matches</th><th>Current category</th></tr></thead><tbody>'+preview.rows.map(r=>'<tr><td>'+e(r.description)+'<small>'+e(r.date)+' · source row '+e(r.sourceRow||'—')+'</small></td><td>'+money(r.amountCents)+'<small>'+e(r.direction)+' · original '+e(r.rawAmount)+'</small></td><td>'+e(r.reason)+'</td><td>'+e(r.category)+'</td></tr>').join('')+'</tbody></table></div><p class="field-hint">Showing up to 30 matches. Future matching imports will receive the same suggestion.</p>';$('#rule-preview').hidden=false;$('#rule-submit').textContent='Save merchant rule';}
    else{await post('/api/rules',payload);$('#rule-editor-dialog').close();await loadData({quiet:true});renderRuleList();toast('Merchant rule saved. Review its suggestions before applying.');}
  }catch(error){showError(form,error);}finally{busy(form,false);}
});
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-rule-toggle]');if(!button)return;const rule=state.rules.find(r=>r.id===button.dataset.ruleToggle);button.disabled=true;
  try{await post('/api/rules',{id:rule.id,active:!rule.active});await loadData({quiet:true});renderRuleList();}catch(error){toast(error.message);button.disabled=false;}
});
