'use strict';

const creditLabels={'payment':'Card payment / transfer','refund':'Purchase refund','statement_credit':'Statement credit / benefit','excluded_credit':'Other credit outside business books','':'Needs a decision'};
const creditView={tab:'needs',query:'',account:'',view:'groups',sort:'date-desc',selected:new Set(),groups:[],bulk:null};

function creditScope(){
  return state.transactions.filter(t=>t.direction==='credit'&&inYear(t)&&(state.workspace==='all'||state.workspace==='personal'?(state.workspace==='all'||t.classification==='personal'||!state.accounts.find(a=>a.id===t.accountId)?.business_id):t.businessId===state.workspace||state.accounts.find(a=>a.id===t.accountId)?.business_id===state.workspace));
}
function creditsNeedingDecision(t){return !t.creditTreatment||isReview(t);}
function filteredCredits(){
  const words=creditView.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return sortTransactionRows(creditScope().filter(t=>(creditView.tab==='all'||creditView.tab==='needs'&&creditsNeedingDecision(t)||creditView.tab==='handled'&&!creditsNeedingDecision(t)||t.creditTreatment===creditView.tab)&&(!creditView.account||t.accountId===creditView.account)&&words.every(w=>[t.description,t.merchant,t.account,t.sourceCategory,t.category,creditLabels[t.creditTreatment||'']].join(' ').toLowerCase().includes(w))),creditView.sort);
}
function creditSuggestion(t){return state.creditSuggestions?.[t.id];}
function creditDecisionText(t){return creditLabels[t.creditTreatment||'']+(included(t)?' · reduces business expenses':' · outside totals');}
function renderCredits(){
  const rows=creditScope(),needs=rows.filter(creditsNeedingDecision).length;
  return heading('A clear place for credits and payments.','Review money coming back to an account. Keep card payments, purchase refunds and statement benefits traceable.',yearSelect(), 'CREDITS & PAYMENTS')+
    '<div class="credit-summary"><div><strong>'+needs+'</strong><span>need a credit decision</span></div><div><strong>'+rows.filter(t=>t.creditTreatment==='payment').length+'</strong><span>card payments / transfers</span></div><div><strong>'+rows.filter(t=>t.creditTreatment==='statement_credit').length+'</strong><span>statement benefits</span></div><button class="button button-secondary" data-credit-rules>Credit rules ('+(state.creditRules||[]).filter(r=>r.active).length+')</button></div>'+
    '<p class="credit-explainer">These are rows read as <strong>Money in</strong>. A bank’s original +/− sign can differ. A statement benefit can stay outside business books while its original charge keeps its own decision. '+(state.workspace!=='all'?'This view also shows credits on accounts owned by this workspace; excluded credits remain available here and in All businesses.':'All transactions remain available in the full ledger.')+'</p>'+
    '<section class="panel credit-workspace"><div class="credit-toolbar"><div class="quick-chips" aria-label="Credit review status">'+[['needs','Needs decision',needs],['all','All money in',rows.length],['handled','Handled',rows.length-needs],['payment','Payments',rows.filter(t=>t.creditTreatment==='payment').length],['statement_credit','Benefits',rows.filter(t=>t.creditTreatment==='statement_credit').length],['refund','Refunds',rows.filter(t=>t.creditTreatment==='refund').length],['excluded_credit','Other excluded',rows.filter(t=>t.creditTreatment==='excluded_credit').length]].map(([key,label,count])=>'<button class="quick-chip '+(creditView.tab===key?'active':'')+'" data-credit-tab="'+key+'" aria-pressed="'+(creditView.tab===key)+'">'+label+' <span>'+count+'</span></button>').join('')+'</div><div class="credit-filter-row"><label class="search-field">'+icon('search')+'<input id="credit-search" type="search" value="'+e(creditView.query)+'" placeholder="Search credit descriptions or categories" aria-label="Search credits"></label><select id="credit-account" aria-label="Credit source account">'+quickOptions([['','All source accounts'],...state.accounts.map(a=>[a.id,accountName(a)])],creditView.account)+'</select>'+transactionSortControl(creditView.sort,'credits',creditView.view==='groups')+'<div class="segmented" aria-label="Credit display">'+[['groups','Groups'],['rows','Rows']].map(([key,label])=>'<button data-credit-view="'+key+'" aria-pressed="'+(creditView.view===key)+'" class="'+(creditView.view===key?'active':'')+'">'+label+'</button>').join('')+'</div>'+(creditView.view==='groups'?groupLayoutControl():'')+'</div></div><div id="credit-results"></div></section>';
}
function creditGroupDetails(){
  const all=creditView.groups.flat(),allSelected=all.length&&all.every(t=>creditView.selected.has(t.id));
  return '<div class="table-wrap"><table class="group-details-table credit-group-details"><thead><tr><th><input type="checkbox" data-credit-group-all aria-label="Select all visible credit groups"'+(allSelected?' checked':'')+'></th><th>Credit group</th><th>Source account</th><th>Credits</th><th class="group-amount">Activity</th><th>Current decision</th><th>Suggestion</th><th>Actions</th></tr></thead><tbody>'+creditView.groups.map((items,i)=>{
    const t=items[0],suggestions=items.map(creditSuggestion),suggestion=suggestions[0],same=suggestion&&!suggestion.conflict&&suggestions.every(s=>s&&!s.conflict&&s.treatment===suggestion.treatment&&s.businessId===suggestion.businessId&&s.category===suggestion.category),decisions=[...new Set(items.map(creditDecisionText))],selected=items.every(t=>creditView.selected.has(t.id));
    return '<tr class="'+(selected?'selected':'')+'"><td><input type="checkbox" data-credit-group-select="'+i+'" aria-label="Select credit group '+e(merchantFamily(t))+'"'+(selected?' checked':'')+'></td><td><button class="text-button" data-credit-inspect="'+i+'">'+e(merchantFamily(t))+'</button><small>'+e([...new Set(items.map(t=>t.sourceCategory).filter(Boolean))].join(', ')||'No statement category')+'</small></td><td>'+e(t.account)+'</td><td>'+items.length+'</td><td class="group-amount">'+money(items.reduce((n,t)=>n+t.amountCents,0))+'</td><td>'+e(decisions.length===1?decisions[0]:'Mixed decisions')+'</td><td title="'+e(suggestion?.reason||'')+'">'+e(same?creditLabels[suggestion.treatment]:suggestion?.conflict?'Conflicting rules':suggestion?'Review each credit':'No suggestion')+'</td><td><div class="group-row-actions"><button class="text-button" data-credit-inspect="'+i+'">View rows</button><button class="button button-secondary button-small" data-credit-decide-group="'+i+'">Decide for group</button></div></td></tr>';
  }).join('')+'</tbody></table></div>';
}
function refreshCreditResults(){
  const target=$('#credit-results');if(!target)return;
  const rows=filteredCredits(),visible=new Set(rows.map(t=>t.id));creditView.selected.forEach(id=>{if(!visible.has(id))creditView.selected.delete(id);});
  const map=new Map();for(const t of rows){const key=merchantGroupKey(t);if(!map.has(key))map.set(key,[]);map.get(key).push(t);}
  creditView.groups=sortTransactionGroups([...map.values()],creditView.sort,merchantFamily);
  const top='<div class="credit-selection"><span><strong>'+rows.length+'</strong> matching credits · '+money(rows.reduce((n,t)=>n+t.amountCents,0))+'</span><button class="text-button" data-credit-select-all>Select all results</button><button class="text-button" data-credit-clear>Clear selection</button><button class="button button-ink" data-credit-decide-selected'+(!creditView.selected.size?' disabled':'')+'>Decide for selected ('+creditView.selected.size+')</button><button class="button button-secondary" data-selected-groups-rule="credit"'+(!creditView.selected.size?' disabled':'')+'>Create / add to rule</button></div>';
  const groups=creditView.groups.map((items,i)=>{
    const t=items[0],suggestions=items.map(creditSuggestion),suggestion=suggestions[0],same=suggestion&&suggestions.every(s=>s&&!s.conflict&&s.treatment===suggestion.treatment&&s.businessId===suggestion.businessId&&s.category===suggestion.category),decisions=[...new Set(items.map(creditDecisionText))];
    return '<article class="merchant-group credit-group"><div class="merchant-group-top"><input type="checkbox" data-credit-group-select="'+i+'" aria-label="Select credit group '+e(merchantFamily(t))+'"'+(items.every(r=>creditView.selected.has(r.id))?' checked':'')+'><span>'+items.length+' credit'+(items.length===1?'':'s')+'</span><strong>'+money(items.reduce((n,r)=>n+r.amountCents,0))+'</strong></div><h3>'+e(merchantFamily(t))+'</h3><p>'+e(t.account)+'</p><p>'+e([...new Set(items.map(r=>r.sourceCategory).filter(Boolean))].join(' · ')||'No statement category')+'</p><span class="category-tag">'+e(decisions.length===1?decisions[0]:'Mixed credit decisions')+'</span>'+(suggestion?'<div class="credit-suggestion"><strong>'+e(same?'Suggested: '+creditLabels[suggestion.treatment]:suggestion.conflict?'Conflicting credit rules':'Review each credit')+'</strong><p>'+e(same?suggestion.reason:suggestion.conflict?suggestion.reason:'This group has different suggestions. Choose a decision after comparing its rows.')+'</p></div>':'<p class="credit-no-suggestion">Choose whether this is a payment, refund or another credit.</p>')+'<div class="merchant-group-actions"><button class="text-button" data-credit-inspect="'+i+'">See these rows</button><button class="button button-ink button-small" data-credit-decide-group="'+i+'">Decide for entire group ('+items.length+')</button></div></article>';
  }).join('');
  const table='<div class="table-wrap"><table class="credit-table"><thead><tr><th></th><th>Credit / source</th><th>Date / amount</th><th>Current decision</th><th></th></tr></thead><tbody>'+rows.map(t=>'<tr><td><input type="checkbox" data-credit-select="'+e(t.id)+'" aria-label="Select credit '+e(t.description)+'"'+(creditView.selected.has(t.id)?' checked':'')+'></td><td><button class="text-button" data-edit="'+e(t.id)+'">'+e(t.description)+'</button><small>'+e(t.account)+' · '+e(t.sourceCategory||'No statement category')+'</small></td><td>'+e(formatDate(t.date))+'<small>+ '+money(t.amountCents)+'</small></td><td>'+e(creditDecisionText(t))+(creditSuggestion(t)?'<small>'+e(creditSuggestion(t).conflict?'Conflicting rules':'Suggested: '+creditLabels[creditSuggestion(t).treatment])+'</small>':'')+'</td><td><button class="button button-secondary button-small" data-credit-decide="'+e(t.id)+'">Choose handling</button></td></tr>').join('')+'</tbody></table></div>';
  target.innerHTML=top+(rows.length?(creditView.view==='groups'?(state.groupLayout==='details'?creditGroupDetails():'<div class="merchant-group-grid">'+groups+'</div>'):table):emptyState('check','No credits match this view.','Choose All money in, another source account or another year.','','compact'));
  $$('[data-credit-group-select]',target).forEach(el=>{const items=creditView.groups[Number(el.dataset.creditGroupSelect)];el.indeterminate=items.some(t=>creditView.selected.has(t.id))&&!items.every(t=>creditView.selected.has(t.id));});
  const selectAll=$('[data-credit-group-all]',target);if(selectAll)selectAll.indeterminate=creditView.selected.size>0&&!allCreditsSelected(rows);
}
function allCreditsSelected(rows){return rows.every(t=>creditView.selected.has(t.id));}

document.body.insertAdjacentHTML('beforeend',`<dialog id="credit-dialog" class="modal quick-modal"><form id="credit-form"><div class="modal-top"><span class="eyebrow">CREDIT DECISION</span><button type="button" class="icon-button" data-close="credit-dialog" aria-label="Close credit decision">×</button></div><h2 id="credit-title">Choose how to handle these credits.</h2><p class="modal-description" id="credit-description"></p><details class="bulk-scope"><summary id="credit-scope-summary"></summary><div id="credit-scope" class="quick-preview-table"></div></details><label class="field">What does this money-in represent?<select id="credit-treatment"><option value="__choose__" disabled>Choose a decision…</option><option value="payment">Card payment / transfer</option><option value="refund">Purchase refund / reversal</option><option value="statement_credit">Statement credit / account benefit</option><option value="excluded_credit">Other credit outside business books</option><option value="">Leave unclear — needs review</option></select></label><p id="credit-guidance" class="credit-guidance"></p><div id="credit-refund-fields" hidden><label class="field">Where does this refund belong?<select id="credit-refund-usage"><option value="outside">Outside business books</option><option value="business">Business purchase refund</option></select></label><div id="credit-refund-business" hidden><div class="field-grid"><label class="field">Business books<select id="credit-business"></select></label><label class="field">Expense category to offset<select id="credit-category"></select></label></div><label class="quick-check"><input id="credit-include" type="checkbox"><span><strong>Reduce business expense totals by this refund</strong><small>This is an explicit reporting decision. Leave unchecked to keep it outside expense totals.</small></span></label></div></div><div id="credit-related-fields" hidden><label class="field">Find a related transaction<input id="credit-related-search" type="search" maxlength="200" placeholder="Description, date or amount (optional)"></label><label class="field">Related transaction (optional)<select id="credit-related"><option value="">No linked transaction</option></select></label><p id="credit-related-reason" class="field-hint"></p><button type="button" class="text-button" id="credit-unlink" hidden data-credit-unlink>Remove related link</button></div>${decisionRuleFields('credit')}<div id="credit-preview" class="quick-preview" hidden></div><p class="form-error" role="alert" hidden></p><div class="modal-footer"><button type="button" class="button button-secondary" data-close="credit-dialog">Cancel</button><button type="submit" id="credit-submit" class="button button-primary">Preview credit decision</button></div></form></dialog><dialog id="credit-rules-dialog" class="modal quick-modal"><div class="modal-top"><span class="eyebrow">CREDIT RULES</span><button type="button" class="icon-button" data-close="credit-rules-dialog" aria-label="Close credit rules">×</button></div><h2>Recognize recurring credits.</h2><p class="modal-description">Save a rule while making a credit decision. Choose its account scope and whether future matches are handled automatically or suggested for review.</p><div id="credit-rules-list"></div><p class="form-error" role="alert" hidden></p></dialog>`);

function creditCategoryOptions(selected=''){
  const business=$('#credit-business').value;
  $('#credit-category').innerHTML=quickOptions([['','Choose an expense category'],...[...new Set(state.categories.filter(c=>(!c.business_id||c.business_id===business)&&!/uncategorized/i.test(c.name)).map(c=>c.name))].sort().map(n=>[n,n])],selected);
}
function openCreditDecision(ids,context=null){
  if(!requireConnection())return;
  const rows=[...new Set(ids)].map(id=>state.transactions.find(t=>t.id===id)).filter(Boolean);
  if(!rows.length||rows.some(t=>t.direction!=='credit')){toast('Select money-in credits separately from charges.');return;}
  if(rows.length>5000){toast('Narrow this set to at most 5,000 credits.');return;}
  creditView.bulk={ids:rows.map(t=>t.id),revision:null,candidates:[],linkRequest:0};
  initializeBatchSelection(creditView.bulk,rows.map(t=>t.id));
  const form=$('#credit-form');form.reset();$('#credit-preview').hidden=true;$('#credit-preview').innerHTML='';$('#credit-submit').textContent='Preview credit decision';
  showSuggestedCreditContext(context);
  $('#credit-title').textContent='One decision for '+rows.length+' credit'+(rows.length===1?'':'s')+'.';
  $('#credit-description').textContent=money(rows.reduce((n,t)=>n+t.amountCents,0))+' in money-in activity. Compare the selected rows, preview the reporting effect, then apply.';
  $('#credit-scope-summary').textContent='See all '+rows.length+' selected credits';

  const decisions=[...new Set(rows.map(t=>t.creditTreatment||''))],suggestions=rows.map(creditSuggestion),sharedSuggestion=suggestions[0]&&!suggestions[0].conflict&&suggestions.every(s=>s&&!s.conflict&&s.treatment===suggestions[0].treatment&&s.businessId===suggestions[0].businessId&&s.category===suggestions[0].category)?suggestions[0]:null;
  const treatment=decisions.length===1&&decisions[0]?decisions[0]:sharedSuggestion?.treatment||context?.treatment||'__choose__';
  $('#credit-treatment').value=treatment;
  const business=sharedSuggestion?.businessId||(rows.every(t=>t.businessId===rows[0].businessId)?rows[0].businessId:'')||(!['all','personal'].includes(state.workspace)?state.workspace:'');
  $('#credit-business').innerHTML='<option value="">Choose a business</option>'+businessOptions(business);
  const category=sharedSuggestion?.category||(rows.every(t=>t.category===rows[0].category)?rows[0].category:'');creditCategoryOptions(category);
  $('#credit-refund-usage').value=treatment==='refund'&&business?'business':'outside';
  initializeDecisionRule('credit',rows,state.page!=='credits'&&triage.grouping==='sourceCategory'?'sourceCategory':'merchant');
  $('#credit-related').innerHTML='<option value="">No linked transaction</option>';
  $('#credit-unlink').hidden=rows.length!==1||!rows[0].relatedTransactionId;
  renderBatchScope('credit');showDialog('credit-dialog');syncCreditDecision();loadCreditCandidates(rows.length===1?rows[0].relatedTransactionId:null);
}
function syncCreditDecision(){
  const treatment=$('#credit-treatment').value,refund=treatment==='refund',business=refund&&$('#credit-refund-usage').value==='business';
  $('#credit-refund-fields').hidden=!refund;$('#credit-refund-business').hidden=!business;
  $('#credit-business').disabled=!business;$('#credit-business').required=business;$('#credit-category').disabled=!business;$('#credit-category').required=business;
  $('#credit-include').disabled=!business;if(!business)$('#credit-include').checked=false;
  $('#credit-related-fields').hidden=creditView.bulk?.ids.length!==1||!['payment','refund'].includes(treatment);
  $('#credit-guidance').textContent=({payment:'Card payments move money between accounts and stay outside income and expense totals. Linking a matching bank withdrawal marks both sides as transfers.',statement_credit:'Keep this account benefit outside business books. Its original charge keeps its current category and reporting decision.',excluded_credit:'Keep this credit in the full activity history and outside business books.',refund:business?'Choose the business and expense category. Only the explicit reporting checkbox reduces expenses.':'Record this purchase refund outside business books. The original purchase keeps its own reporting decision.','':'Leave these credits in Needs decision and outside expense totals.'})[treatment]||'Choose a payment, refund or credit decision. A suggestion is ready for your review.';
  syncDecisionRule('credit',true,business&&$('#credit-include').checked,!!treatment&&treatment!=='__choose__');
}
function invalidateCredit(){if(!creditView.bulk)return;creditView.bulk.revision=null;$('#credit-preview').hidden=true;$('#credit-submit').textContent='Preview '+creditView.bulk.ids.length+' selected credits';$('.form-error',$('#credit-form')).hidden=true;syncBatchScope('credit');}
async function loadCreditCandidates(selected=null){
  const bulk=creditView.bulk,treatment=$('#credit-treatment').value;if(!bulk||bulk.ids.length!==1||!['payment','refund'].includes(treatment))return;
  const request=++bulk.linkRequest;bulk.linkLoading=true;$('#credit-related').disabled=true;$('#credit-related-reason').textContent='Finding possible matches…';
  try{
    const candidates=await api('/api/credits/'+encodeURIComponent(bulk.ids[0])+'/candidates?treatment='+treatment+'&q='+encodeURIComponent($('#credit-related-search').value));
    if(creditView.bulk!==bulk||request!==bulk.linkRequest||$('#credit-treatment').value!==treatment)return;
    bulk.candidates=candidates;$('#credit-related').innerHTML=quickOptions([['','No linked transaction'],...candidates.map(t=>[t.id,t.date+' · '+t.description+' · '+money(t.amountCents)+' · '+accountName(state.accounts.find(a=>a.id===t.accountId))])],selected||'');
    $('#credit-related-reason').textContent=selected?candidates.find(t=>t.id===selected)?.reason||'The old link is unavailable; choose a new match.':candidates.length?'These are possible matches. Compare account, amount and dates before linking.':'No likely match was found. You can record the decision without a related transaction.';
  }catch(error){if(creditView.bulk===bulk&&request===bulk.linkRequest)showError($('#credit-form'),error);}
  finally{if(creditView.bulk===bulk&&request===bulk.linkRequest){bulk.linkLoading=false;$('#credit-related').disabled=false;}}
}
function creditPayload(){
  const treatment=$('#credit-treatment').value,business=treatment==='refund'&&$('#credit-refund-usage').value==='business',remember=$('#credit-remember-rule').checked&&!!treatment;
  const body={ids:creditView.bulk.ids,treatment,includeInTotals:business&&$('#credit-include').checked};
  if(treatment==='refund')Object.assign(body,{refundUsage:$('#credit-refund-usage').value,businessId:business?$('#credit-business').value:null,category:business?$('#credit-category').value:''});
  if(creditView.bulk.ids.length===1&&['payment','refund'].includes(treatment))body.relatedId=$('#credit-related').value||null;
  if(remember)Object.assign(body,decisionRulePayload('credit',true));
  return body;
}
function creditPreviewMarkup(plan){
  return '<div class="batch-summary"><div><span>Selected credits</span><strong>'+plan.selectedCount+'</strong></div><div><span>Rows affected, including linked payments</span><strong>'+plan.affectedCount+'</strong></div></div><p><strong>'+e(plan.label)+'</strong> · '+(plan.includeInTotals?'Reduces business expenses by '+money(plan.amountCents):'Outside business expense totals')+'</p><div class="quick-preview-table"><table><thead><tr><th>Transaction</th><th>Decision / reporting effect</th></tr></thead><tbody>'+plan.rows.map(r=>'<tr><td>'+e(r.description)+'<small>'+e(r.date)+' · '+money(r.amountCents)+'</small></td><td>'+e(r.reason)+'<small>'+e(r.old.category_name)+' → '+e(r.new.category_name)+'</small></td></tr>').join('')+'</tbody></table></div>'+decisionRulePreview(plan.rememberedRule)+'<p class="field-hint">Review this exact set before applying. This decision is recorded in history and can be undone in Data & storage.</p>';
}
function renderCreditRules(){
  $('#credit-rules-list').innerHTML=(state.creditRules||[]).length?state.creditRules.map(r=>'<article class="quick-rule"><div><strong>'+e(r.pattern)+'</strong><p>'+e(r.account_id?accountName(state.accounts.find(a=>a.id===r.account_id)):'All source accounts')+'</p><span class="category-tag">'+e(creditLabels[r.treatment])+'</span> <small>'+(r.active?'Active':'Paused')+'</small></div><div><button class="text-button" data-auto-edit="'+e(r.id)+'" data-rule-type="credit">Edit / automate</button><button class="text-button" data-credit-rule-toggle="'+e(r.id)+'">'+(r.active?'Pause':'Enable')+'</button></div></article>').join(''):emptyState('tag','No saved credit rules yet.','Handle a recurring credit and choose Save this decision as a rule.','','compact');
}
document.addEventListener('click',async event=>{
  const el=event.target;
  if(el.closest('[data-review-selected-credits]')){openCreditDecision(state.transactions.filter(t=>state.selected.has(t.id)&&t.direction==='credit').map(t=>t.id));return;}
  const editor=el.closest('[data-editor-credit]');if(editor){event.stopImmediatePropagation();if(routeEditorCreditFromBatch(editor.dataset.editorCredit))return;$('#transaction-dialog').close();if(editor.dataset.editorCredit)openCreditDecision([editor.dataset.editorCredit]);else navigate('credits');return;}
  const listed=el.closest('[data-review-listed-credits]');if(listed){openCreditDecision(filteredLedger().filter(t=>t.direction==='credit').map(t=>t.id));return;}
  const quickGroup=el.closest('[data-review-group-credits]');if(quickGroup){openCreditDecision(triage.groups[Number(quickGroup.dataset.reviewGroupCredits)][1].filter(t=>t.direction==='credit').map(t=>t.id));return;}
  const decide=el.closest('[data-credit-decide]');if(decide){event.stopImmediatePropagation();openCreditDecision([decide.dataset.creditDecide]);return;}
  const tab=el.closest('[data-credit-tab]');if(tab){creditView.tab=tab.dataset.creditTab;creditView.selected.clear();render();}
  const view=el.closest('[data-credit-view]');if(view){creditView.view=view.dataset.creditView;render();}
  if(el.closest('[data-credit-select-all]')){filteredCredits().slice(0,5000).forEach(t=>creditView.selected.add(t.id));refreshCreditResults();if(filteredCredits().length>5000)toast('Selected the first 5,000 credits. Narrow the filters for a smaller batch.');}
  if(el.closest('[data-credit-clear]')){creditView.selected.clear();refreshCreditResults();}
  if(el.closest('[data-credit-decide-selected]'))openCreditDecision([...creditView.selected]);
  const group=el.closest('[data-credit-decide-group]');if(group)openCreditDecision(creditView.groups[Number(group.dataset.creditDecideGroup)].map(t=>t.id));
  const inspect=el.closest('[data-credit-inspect]');if(inspect){const t=creditView.groups[Number(inspect.dataset.creditInspect)][0];creditView.query=merchantFamily(t);creditView.account=t.accountId;creditView.view='rows';render();}
  if(el.closest('[data-credit-unlink]')){$('#credit-related').value='';invalidateCredit();$('#credit-related-reason').textContent='The preview will remove the related link.';}
  if(el.closest('[data-credit-rules]')){ruleDesk.type='credit';navigate('automation');}
  const toggle=el.closest('[data-credit-rule-toggle]');if(toggle){try{const rule=state.creditRules.find(r=>r.id===toggle.dataset.creditRuleToggle);await post('/api/credits/rules',{id:rule.id,active:!rule.active});await loadData({quiet:true});renderCreditRules();}catch(error){showError($('#credit-rules-dialog'),error);}}
});
document.addEventListener('change',event=>{
  const el=event.target;
  if(el.matches('[data-credit-group-all]')){filteredCredits().forEach(t=>el.checked?creditView.selected.add(t.id):creditView.selected.delete(t.id));refreshCreditResults();}
  if(el.matches('[data-credit-select]')){el.checked?creditView.selected.add(el.dataset.creditSelect):creditView.selected.delete(el.dataset.creditSelect);refreshCreditResults();}
  if(el.matches('[data-credit-group-select]')){creditView.groups[Number(el.dataset.creditGroupSelect)].forEach(t=>el.checked?creditView.selected.add(t.id):creditView.selected.delete(t.id));refreshCreditResults();}
  if(el.id==='credit-account'){creditView.account=el.value;creditView.selected.clear();refreshCreditResults();}
  if(el.closest('#credit-form')&&!el.matches('[data-batch-row-select],[data-batch-select-all],[data-transaction-sort]')){
    invalidateCredit();
    if(el.id==='credit-treatment'){$('#credit-related-search').value='';if(creditView.bulk){creditView.bulk.linkRequest++;creditView.bulk.linkLoading=false;}$('#credit-related').innerHTML='<option value="">No linked transaction</option>';loadCreditCandidates();}
    if(el.id==='credit-business')creditCategoryOptions();
    if(el.id==='credit-related'){
      const match=creditView.bulk.candidates.find(t=>t.id===el.value);$('#credit-related-reason').textContent=match?.reason||'No transaction will be linked.';
      if(match&&$('#credit-treatment').value==='refund'&&match.businessId){$('#credit-refund-usage').value='business';$('#credit-business').value=match.businessId;creditCategoryOptions(match.category);$('#credit-include').checked=false;}
    }
    syncCreditDecision();
  }
});
document.addEventListener('input',event=>{if(event.target.id==='credit-search'){creditView.query=event.target.value;creditView.selected.clear();refreshCreditResults();}if(event.target.closest('#credit-form')&&!event.target.matches('[data-batch-row-select],[data-batch-select-all],[data-transaction-sort]'))invalidateCredit();if(event.target.id==='credit-related-search'){clearTimeout(creditView.searchTimer);creditView.searchTimer=setTimeout(()=>loadCreditCandidates($('#credit-related').value),250);}});
document.querySelector('#credit-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,bulk=creditView.bulk;if(!bulk)return;
  if(!bulk.ids.length||bulk.busy)return;
  if(bulk.linkLoading){showError(form,new Error('Wait for related transaction matches to finish loading.'));return;}
  const body=creditPayload();setBatchBusy('credit',true);
  try{
    if(body.treatment==='__choose__')throw new Error('Choose a credit decision before previewing.');
    if(bulk.revision){await post('/api/credits/apply',{...body,revision:bulk.revision});$('#credit-dialog').close();creditView.selected.clear();state.selected.clear();await loadData({quiet:true});toast('Credit decision saved.'+(body.rememberRule?' Future-import rule saved.':'')+' Find it in All money in or undo it in Data & storage.');}
    else{const plan=await post('/api/credits/preview',body);bulk.revision=plan.revision;$('#credit-preview').innerHTML=creditPreviewMarkup(plan);$('#credit-preview').hidden=false;$('#credit-submit').textContent='Apply decision to '+plan.affectedCount+' row'+(plan.affectedCount===1?'':'s');$('#credit-preview').scrollIntoView({block:'nearest',behavior:'smooth'});}
  }catch(error){bulk.revision=null;$('#credit-submit').textContent='Preview credit decision';showError(form,error);}finally{setBatchBusy('credit',false);}
});
