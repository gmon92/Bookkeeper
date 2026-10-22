'use strict';

const ruleDesk={query:'',category:'',type:'all',editor:null,run:null,checking:false,summary:null,combine:null};
const automationModes={suggest:'Suggest only',categorize:'Auto-categorize · review later',review:'Auto-review · trusted rule'};
function automationRules(){return state.automation?.rules||[];}
function autoSourceCategories(c={}){return c.sourceCategories||(c.sourceCategory?[c.sourceCategory]:[]);}
function ruleConsistencyMarkup(rule){return rule.consistencyIssue?'<p class="consistency-rule-warning">'+e(rule.consistencyIssue)+'</p>':'';}
function ruleDestination(r){return r.type==='credit'?(creditLabels[r.treatment]+(r.business_id?' · '+r.category_name:'')):r.category_name;}
function ruleConditionText(r){const c=r.conditions||{};return [(c.patterns||[r.pattern]).length?'Description: '+(c.patterns||[r.pattern]).join(' OR '):'',autoSourceCategories(c).length?'Original categories: '+autoSourceCategories(c).join(' OR '):'',c.minCents!=null?'Minimum '+money(c.minCents):'',c.maxCents!=null?'Maximum '+money(c.maxCents):''].filter(Boolean).join(' · ');}
function automationProposalGroups(){
  const groups=new Map();
  for(const p of state.automation?.proposals||[]){
    if(state.workspace!=='all'&&(state.workspace==='personal'?!!p.businessId:p.businessId!==state.workspace))continue;
    const key=JSON.stringify([p.type,p.businessId||'',p.category,p.accountId,p.treatment||'']);
    if(!groups.has(key))groups.set(key,{key,type:p.type,businessId:p.businessId,category:p.category,accountId:p.accountId,treatment:p.treatment,ideas:[]});
    groups.get(key).ideas.push(p);
  }
  return [...groups.values()].map(g=>({...g,label:g.type==='expense'?g.category:(creditLabels[g.treatment]+(g.businessId?' · '+g.category:'')),count:g.ideas.reduce((sum,p)=>sum+p.count,0)})).sort((a,b)=>a.label.localeCompare(b.label)||businessName(a.businessId).localeCompare(businessName(b.businessId))||a.accountId.localeCompare(b.accountId));
}
function proposalGroupScope(g){return (g.businessId?businessName(g.businessId):'Outside business books')+' · '+accountName(state.accounts.find(a=>a.id===g.accountId));}
function combinedIdeasMarkup(){
  const groups=automationProposalGroups();
  return '<section id="automation-rule-ideas" class="panel automation-proposals" tabindex="-1"><div class="combined-section-heading"><div><h2>Combine rule ideas by category</h2><p>Pick several stores for Meals, Fuel or another category and save one shared rule. Business books and source accounts stay with each group.</p></div><button class="button button-secondary" data-auto-combine'+(!groups.length?' disabled':'')+'>Combine rule ideas</button></div>'+(groups.length?'<div class="combined-idea-groups">'+groups.map(g=>'<article class="combined-idea-group"><span class="category-tag">'+e(g.label)+'</span><h3>'+g.ideas.length+' store idea'+(g.ideas.length===1?'':'s')+'</h3><p>'+e(proposalGroupScope(g))+'</p><small>'+g.count+' consistent reviewed transactions</small><p class="combined-store-examples">'+e(g.ideas.slice(0,3).map(p=>p.patterns.join(' OR ')).join(' · '))+(g.ideas.length>3?' · …':'')+'</p><button class="button button-secondary button-small" data-auto-combine-group="'+e(g.key)+'">Choose stores for '+e(g.label)+'</button></article>').join('')+'</div>':'<p class="field-hint">Ideas appear after at least two consistent reviewed decisions for the same merchant and account. Existing rules already cover some stores.</p>')+'</section>';
}
function renderAutomation(){
  const all=automationRules().filter(r=>state.workspace==='all'||(state.workspace==='personal'?!r.business_id:r.business_id===state.workspace));
  const words=ruleDesk.query.toLowerCase().split(/\s+/).filter(Boolean);
  const rules=all.filter(r=>(ruleDesk.type==='all'||r.type===ruleDesk.type)&&(!ruleDesk.category||r.category_name===ruleDesk.category)&&words.every(w=>[r.pattern,r.category_name,businessName(r.business_id),ruleConditionText(r)].join(' ').toLowerCase().includes(w)));
  const categories=[...new Set(state.categories.filter(c=>(state.workspace==='all'||!c.business_id||c.business_id===state.workspace)&&!/uncategorized/i.test(c.name)).map(c=>c.name))].sort();
  const groups=automationProposalGroups(),proposals=groups.flatMap(g=>g.ideas);
  return heading('Decide once. Put the repeat work on autopilot.','Rules recognize future imports, assign the right books and explain every decision.','<button class="button button-secondary" data-auto-run>Run rule check</button><button class="button button-secondary" data-auto-ideas>View rule ideas ('+proposals.length+')</button><button class="button button-primary" data-auto-new>Create rule</button>','RULES & AUTOMATION')+
    ruleLibraryPanel()+
    '<div class="automation-metrics"><article><strong>'+all.filter(r=>r.active).length+'</strong><span>enabled rules</span></article><article><strong>'+all.filter(r=>r.active&&!r.consistencyIssue&&r.automation_mode!=='suggest').length+'</strong><span>run automatically on import</span></article><article><strong>'+proposals.length+'</strong><span>rule ideas from reviewed activity</span></article></div>'+
    '<section class="panel automation-intro"><div><h2>Your rules run when you confirm an import.</h2><p>Merchant description rules always take priority over category group rules when both match an eligible row, even if the category rule is account-specific. Account-specific merchant rules win over otherwise identical merchant rules across accounts. Equally specific conflicting rules stay for review. New imports are checked automatically; choose Run rule check to preview existing rows across all businesses and years.</p></div></section>'+
    '<section class="panel automation-list"><div class="automation-toolbar"><label class="search-field">'+icon('search')+'<input id="automation-search" type="search" aria-label="Search rules" placeholder="Search merchant, category or business" value="'+e(ruleDesk.query)+'"></label><select id="automation-type" aria-label="Rule type">'+quickOptions([['all','All rules'],['expense','Expense categories'],['credit','Credits & payments']],ruleDesk.type)+'</select><select id="automation-category" aria-label="Rule category">'+quickOptions([['','All categories'],...categories.map(c=>[c,c])],ruleDesk.category)+'</select></div><div id="automation-rules">'+(rules.length?rules.map(r=>'<article class="automation-rule"><div><span class="category-tag">'+e(ruleDestination(r))+'</span> <span class="automation-mode">'+e(automationModes[r.automation_mode]||automationModes.suggest)+'</span><h3>'+e(ruleConditionText(r))+'</h3><p>'+e(r.account_id?accountName(state.accounts.find(a=>a.id===r.account_id)):'All source accounts')+' · '+e(r.business_id?businessName(r.business_id):'Outside business books')+' · '+(r.type==='credit'?'Money in':'Money out')+'</p><small>'+r.matchCount+' matching historical rows · '+(r.include_expenses?'Includes eligible expenses in totals':'Outside totals until included')+' · '+(r.active?'Enabled':'Paused')+'</small>'+ruleConsistencyMarkup(r)+'</div><div class="automation-actions"><button class="button button-secondary button-small" data-auto-edit="'+e(r.id)+'" data-rule-type="'+r.type+'">Edit / preview</button><button class="text-button" data-auto-toggle="'+e(r.id)+'" data-rule-type="'+r.type+'">'+(r.active?'Pause':'Enable')+'</button></div></article>').join(''):emptyState('tag','Create rules for your recurring activity.','Start with a category below, or create a merchant or credit rule.','','compact'))+'</div></section>'+
    '<section class="panel automation-categories"><h2>Build rules by category</h2><p>Several merchant descriptions can share one category rule. Original statement categories can provide a broader fallback.</p><div class="automation-category-grid">'+categories.map(c=>'<button class="automation-category" data-auto-category="'+e(c)+'"><strong>'+e(c)+'</strong><span>'+all.filter(r=>r.type==='expense'&&r.category_name===c).length+' rules · '+groups.filter(g=>g.type==='expense'&&g.category===c).reduce((n,g)=>n+g.ideas.length,0)+' store ideas '+icon('plus')+'</span></button>').join('')+'</div></section>'+
    combinedIdeasMarkup();
}

document.body.insertAdjacentHTML('beforeend',`<dialog id="automation-editor" class="modal quick-modal"><form id="automation-form"><div class="modal-top"><span class="eyebrow">RULE BUILDER</span><button type="button" class="icon-button" data-close="automation-editor" aria-label="Close rule builder">×</button></div><h2 id="automation-editor-title">Create an import rule.</h2><div id="auto-combined-origin" class="combined-origin" hidden><button type="button" class="text-button" data-combined-back>Back to store picker</button><p id="auto-combined-description"></p></div><p class="modal-description">Merchant text can appear anywhere in the merchant name or full description, ignoring case and punctuation. For example, Lowes matches Lowes123 and Lowes234. A row must also match every other condition you set.</p><label class="field">Rule type<select id="auto-kind"><option value="expense">Expense category · money out</option><option value="credit">Credit decision · money in</option></select></label><label class="field">Merchant descriptions · contains any text below<textarea id="auto-patterns" rows="3" placeholder="SHELL&#10;EXXON&#10;CHEVRON"></textarea><span class="field-hint">One text fragment per line, up to 200. No wildcard needed. Leave blank to use only an original statement category.</span></label><label class="field">Original statement categories · any label matches<textarea id="auto-source-category" rows="2" placeholder="Restaurants&#10;Groceries"></textarea><span class="field-hint">Optional: one original category per line, up to 200. Leave merchant phrases blank to match these categories across all merchants. Labels ignore case and punctuation.</span><datalist id="auto-source-categories"></datalist></label><label class="field">Source account<select id="auto-account"></select></label><div class="field-grid"><label class="field">Minimum amount · USD<input id="auto-min" type="number" min="0" step="0.01" placeholder="Optional"></label><label class="field">Maximum amount · USD<input id="auto-max" type="number" min="0" step="0.01" placeholder="Optional"></label></div><label class="field" id="auto-credit-field">Credit decision<select id="auto-treatment"><option value="" disabled>Choose a credit decision</option><option value="payment">Card payment / transfer</option><option value="statement_credit">Statement credit / account benefit</option><option value="excluded_credit">Other credit outside business books</option><option value="refund">Purchase refund / reversal</option></select></label><div id="auto-destination" class="field-grid"><label class="field">Business books<select id="auto-business"></select></label><label class="field" id="auto-category-field">Category<select id="auto-category"></select></label></div><label class="field">Automation level<select id="auto-mode"><option value="suggest">Suggest only</option><option value="categorize">Auto-categorize · leave for review</option><option value="review">Auto-review · trusted rule</option></select></label><p class="field-hint" id="auto-mode-help"></p><div id="auto-trust-fields"><label class="quick-check"><input id="auto-trust" type="checkbox"><span>I trust this rule to approve matching new transactions automatically.</span></label><label class="quick-check" id="auto-include-field"><input id="auto-include" type="checkbox"><span>Also include eligible business expenses / refunds in totals.<small>Refunds reduce expenses. Payments and benefits always stay outside totals.</small></span></label></div><div id="auto-rule-preview" class="quick-preview" hidden></div><p class="form-error" role="alert" hidden></p><div class="modal-footer"><button type="button" class="button button-secondary" data-close="automation-editor">Cancel</button><button type="submit" id="auto-rule-submit" class="button button-primary">Preview rule</button></div></form></dialog>
<dialog id="automation-run" class="modal quick-modal"><form id="automation-run-form"><div class="modal-top"><span class="eyebrow">RULE CHECK</span><button type="button" class="icon-button" data-close="automation-run" aria-label="Close automation preview">×</button></div><h2>Rule check results.</h2><p class="modal-description">This covers eligible unreviewed rows across all businesses and years. Reviewed, excluded, linked and possible duplicate rows are preserved. Merchant description rules take priority over category group rules. Suggest-only matches remain suggestions; apply them from Transactions → Rule suggestions or review them in Credits & payments.</p><div id="automation-run-preview"></div><p class="form-error" role="alert" hidden></p><div class="modal-footer"><button type="button" class="button button-secondary" data-close="automation-run">Cancel</button><button type="submit" class="button button-primary" id="automation-run-submit">Apply this preview</button></div></form></dialog>
<dialog id="automation-summary" class="modal quick-modal"><div class="modal-top"><span class="eyebrow">IMPORT RESULTS</span><button type="button" class="icon-button" data-close="automation-summary" aria-label="Close import results">×</button></div><h2 id="automation-summary-title">Your import is organized.</h2><p class="modal-description">These results record what happened at import. Open a group to review its transactions and decisions.</p><div id="automation-summary-body"></div><p class="form-error" role="alert" hidden></p><div class="modal-footer"><button class="button button-secondary" data-summary-undo>Undo automatic decisions</button><button class="button button-primary" data-close="automation-summary">Continue</button></div></dialog>`);

document.body.insertAdjacentHTML('beforeend',`<dialog id="combined-rule-dialog" class="modal quick-modal combined-rule-dialog"><form id="combined-rule-form"><div class="modal-top"><span class="eyebrow">COMBINED RULE MAKER</span><button type="button" class="icon-button" data-close="combined-rule-dialog" aria-label="Close combined rule maker">×</button></div><h2>One category. Your choice of stores.</h2><p class="modal-description">Check the stores you want to share a rule. The next step lets you preview their matches and choose how automatically the rule should run.</p><label class="field">Category, business and source account<select id="combined-rule-group"></select></label><p class="combined-scope" id="combined-rule-scope"></p><label class="search-field combined-search"><input id="combined-rule-search" type="search" placeholder="Find a store in this group" aria-label="Search store ideas"></label><div class="combined-selection-toolbar"><label><input type="checkbox" id="combined-rule-all"><span>Select all shown stores</span></label><button type="button" class="text-button" data-combined-clear>Clear selection</button></div><p id="combined-rule-visible" class="field-hint"></p><div id="combined-rule-stores" class="combined-store-picker"></div><div class="combined-selection-summary" role="status" aria-live="polite" id="combined-rule-summary"></div><p id="combined-rule-limit" class="form-error" hidden></p><div class="modal-footer"><button type="button" class="button button-secondary" data-close="combined-rule-dialog">Cancel</button><button type="submit" id="combined-rule-build" class="button button-primary" disabled>Continue with selected stores</button></div></form></dialog>`);

function combinedGroup(){return ruleDesk.combine?.groups.find(g=>g.key===ruleDesk.combine.key);}
document.body.insertAdjacentHTML('beforeend',`<dialog id="selected-groups-rule" class="modal quick-modal"><form id="selected-groups-rule-form"><div class="modal-top"><span class="eyebrow">SELECTED GROUPS</span><button type="button" class="icon-button" data-close="selected-groups-rule" aria-label="Close selected group rules">×</button></div><h2 id="selected-groups-title">Several groups. One rule.</h2><label id="selected-groups-direction-field" class="field" hidden>Money movement for this rule<select id="selected-groups-direction" disabled></select></label><p id="selected-groups-description" class="modal-description"></p><label class="field"><span id="selected-groups-target-label">Where should these merchants go?</span><select id="selected-groups-target"></select></label><p id="selected-groups-instructions" class="field-hint"></p><div class="combined-selection-toolbar"><button type="button" class="text-button" data-selected-groups-all>Select all groups</button><button type="button" class="text-button" data-selected-groups-none>Clear selection</button></div><div id="selected-groups-picker" class="combined-store-picker"></div><p id="selected-groups-summary" class="field-hint" aria-live="polite"></p><p class="form-error" role="alert" hidden></p><div class="modal-footer"><button type="button" class="button button-secondary" data-close="selected-groups-rule">Cancel</button><button type="submit" id="selected-groups-continue" class="button button-primary">Continue to rule builder</button></div></form></dialog>`);
function selectedGroupRuleChoices(){
  const source=ruleDesk.groupSelection.grouping==='sourceCategory';
  return automationRules().filter(r=>r.type===ruleDesk.groupSelection.type&&r.active&&(source?autoSourceCategories(r.conditions).length&&!(r.conditions?.patterns||[r.pattern]).length:(r.conditions?.patterns||[r.pattern]).length));
}
function selectedRuleLabels(rule){return ruleDesk.groupSelection.grouping==='sourceCategory'?autoSourceCategories(rule.conditions):(rule.conditions?.patterns||[rule.pattern]);}
function sourceCategoryRuleGroups(rows){
  const groups=new Map();for(const row of rows){const label=(row.sourceCategory||'').trim();if(!groups.has(label))groups.set(label,{pattern:label,ids:[]});groups.get(label).ids.push(row.id);}
  return [...groups.values()];
}
function refreshSelectedRulePicker(){
  const selection=ruleDesk.groupSelection,source=selection.grouping==='sourceCategory',allRows=selection.allIds.map(id=>state.transactions.find(t=>t.id===id)).filter(Boolean),rows=source?allRows.filter(t=>t.direction===$('#selected-groups-direction').value):allRows;
  selection.type=(source?$('#selected-groups-direction').value:rows[0].direction)==='credit'?'credit':'expense';
  selection.groups=source?sourceCategoryRuleGroups(rows):decisionRuleGroups(rows);selection.selected=new Set(selection.groups.filter(g=>g.pattern).map(g=>g.pattern));
  $('#selected-groups-title').textContent=source?'Rule by statement category.':'Several groups. One rule.';
  $('#selected-groups-target-label').textContent=source?'Where should these statement categories go?':'Where should these merchants go?';
  $('#selected-groups-instructions').textContent=source?'Map original statement categories to a bookkeeping category or credit decision, across merchants. Create a new rule or add labels to an existing category rule. Account scope and automation are confirmed next.':'Choose a new rule or add merchant phrases to an existing rule. Account scope, category or credit handling, and automation are confirmed next.';
  $('#selected-groups-description').textContent=selection.groups.length+(source?' original statement category groups':' merchant descriptions')+' from '+rows.length+' '+(selection.type==='credit'?'money-in':'money-out')+' transactions.'+(source&&rows.length!==allRows.length?' Other money movements need a separate rule.':'')+(selection.groups.some(g=>!g.pattern)?' Groups with no original category cannot be saved as category rules; use merchant rules for those.':'');
  $('#selected-groups-target').innerHTML=quickOptions([['','Create a new combined rule'],...selectedGroupRuleChoices().map(r=>[r.id,'Add to: '+ruleDestination(r)+' · '+selectedRuleLabels(r).join(' / ').slice(0,100)])],'');
  $('#selected-groups-picker').innerHTML=selection.groups.map((g,i)=>'<label class="combined-store-row '+(g.pattern?'selected':'')+'"><input type="checkbox" data-selected-rule-group="'+i+'"'+(g.pattern?' checked':' disabled')+'><span><strong>'+e(g.pattern||'No statement category')+'</strong><small>'+g.ids.length+' selected transactions</small></span></label>').join('');
  syncSelectedGroupRule();
}
function openSelectedGroupRule(ids,grouping='merchant'){
  if(!requireConnection())return;
  const rows=[...new Set(ids)].map(id=>state.transactions.find(t=>t.id===id)).filter(Boolean),directions=new Set(rows.map(t=>t.direction)),source=grouping==='sourceCategory';
  if(!rows.length){toast('Check the groups or transactions you want in the rule.');return;}
  if(rows.length>5000){toast('Choose at most 5,000 transactions for this rule.');return;}
  if(!source&&(directions.size!==1||!['debit','credit'].includes(rows[0].direction))){toast('Select money-out or money-in transactions separately. Use the Money movement filter or pick individual rows.');return;}
  if(source&&!rows.some(t=>['debit','credit'].includes(t.direction))){toast('Confirm the money movement for these rows before making a category rule.');return;}
  ruleDesk.groupSelection={allIds:rows.map(t=>t.id),grouping};
  $('#selected-groups-direction-field').hidden=!source;$('#selected-groups-direction').disabled=!source;
  $('#selected-groups-direction').innerHTML=quickOptions([['debit','Money out · expense category rule'],['credit','Money in · credit decision rule']].filter(([key])=>directions.has(key)),directions.has('debit')?'debit':'credit');
  try{refreshSelectedRulePicker();}catch(error){toast(error.message);return;}
  showDialog('selected-groups-rule');
}
function syncSelectedGroupRule(){
  const selection=ruleDesk.groupSelection,source=selection.grouping==='sourceCategory',groups=selection.groups.filter(g=>selection.selected.has(g.pattern)),rule=selectedGroupRuleChoices().find(r=>r.id===$('#selected-groups-target').value),labels=combinedPatterns([{patterns:rule?selectedRuleLabels(rule):[]},{patterns:groups.map(g=>g.pattern)}]),max=(source?state.automation?.maxSourceCategories:state.automation?.maxPatterns)||200;
  $$('[data-selected-rule-group]',$('#selected-groups-picker')).forEach(el=>{el.checked=selection.selected.has(selection.groups[Number(el.dataset.selectedRuleGroup)].pattern);el.closest('label').classList.toggle('selected',el.checked);});
  $('#selected-groups-summary').textContent=groups.length+(source?' statement category groups':' merchant groups')+' chosen · '+labels.length+' total '+(source?'category labels':'phrases')+' in '+(rule?'the existing rule.':'one new rule.')+(labels.length>max?' Choose fewer groups; the limit is '+max+'.':'');
  $('#selected-groups-continue').disabled=!groups.length||labels.length>max;
}
function buildSelectedGroupRule(){
  const selection=ruleDesk.groupSelection,source=selection.grouping==='sourceCategory',groups=selection.groups.filter(g=>selection.selected.has(g.pattern)),rule=selectedGroupRuleChoices().find(r=>r.id===$('#selected-groups-target').value);
  if(!groups.length)return;
  const ids=[...new Set(groups.flatMap(g=>g.ids))],rows=ids.map(id=>state.transactions.find(t=>t.id===id)),accounts=[...new Set(rows.map(t=>t.accountId))],businesses=[...new Set(rows.map(t=>t.businessId||state.accounts.find(a=>a.id===t.accountId)?.business_id||''))],categories=[...new Set(rows.map(t=>t.category))],treatments=[...new Set(rows.map(t=>t.creditTreatment||creditSuggestion(t)?.treatment||''))],labels=combinedPatterns([{patterns:rule?selectedRuleLabels(rule):[]},{patterns:groups.map(g=>g.pattern)}]);
  if(labels.length>((source?state.automation?.maxSourceCategories:state.automation?.maxPatterns)||200))return;
  $('#selected-groups-rule').close();
  openAutomationRule(selection.type,rule?.id||'',{patterns:source?[]:labels,sourceCategories:source?labels:[],accountId:accounts.length===1?accounts[0]:null,businessId:businesses.length===1?businesses[0]:null,category:categories.length===1?categories[0]:'',treatment:treatments.length===1?treatments[0]:''});
  if(source){$('#auto-patterns').value='';$('#auto-source-category').value=labels.join('\n');}else $('#auto-patterns').value=labels.join('\n');
  $('#auto-kind').disabled=true;
  if(!rule&&selection.type==='credit'&&(treatments.length!==1||!treatments[0]))$('#auto-treatment').value='';
  ruleDesk.editor.groupSelection={ids,count:groups.length,grouping:selection.grouping};
  $('#automation-editor-title').textContent=rule?'Add '+groups.length+' groups to this rule.':source?'Map '+groups.length+' statement categories.':'Create one rule for '+groups.length+' groups.';
  $('#auto-combined-origin').hidden=false;$('#auto-combined-description').textContent=groups.length+(source?' chosen statement categories. Rules match these original labels across merchants. ':' chosen merchant groups. ')+(rule?'Existing conditions are retained. Confirm account scope and other limits.':'Choose the destination and account scope below.');
  invalidateAutoRule();syncAutoEditor();
}
function combinedSelected(){const c=ruleDesk.combine;if(!c.selections.has(c.key))c.selections.set(c.key,new Set());return c.selections.get(c.key);}
function combinedIdeaKey(p){return JSON.stringify(p.patterns);}
function combinedVisibleIdeas(){const words=ruleDesk.combine.query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);return combinedGroup().ideas.filter(p=>words.every(w=>p.patterns.join(' ').toLocaleLowerCase().includes(w)));}
function combinedPatterns(ideas){const unique=new Map();for(const p of ideas)for(const phrase of p.patterns){const key=phrase.normalize('NFKC').toLocaleLowerCase().replace(/[^\p{L}\p{N}_]+/gu,' ').trim();if(!unique.has(key))unique.set(key,phrase);}return [...unique.values()];}
function openCombinedIdeas(key=''){
  if(!requireConnection())return;
  const groups=automationProposalGroups();if(!groups.length){toast('No uncovered rule ideas are available yet.');return;}
  const selected=groups.find(g=>g.key===key)||groups.find(g=>g.category===ruleDesk.category)||groups[0];
  ruleDesk.combine={groups,key:selected.key,selections:new Map(),query:''};
  $('#combined-rule-group').innerHTML=quickOptions(groups.map(g=>[g.key,g.label+' · '+proposalGroupScope(g)+' · '+g.ideas.length+' stores']),selected.key);
  $('#combined-rule-search').value='';renderCombinedStores();showDialog('combined-rule-dialog');
}
function renderCombinedStores(){
  const group=combinedGroup(),ideas=combinedVisibleIdeas();
  $('#combined-rule-scope').textContent=group.label+' · '+proposalGroupScope(group)+' · '+(group.type==='expense'?'Money out':'Money in')+'. Every checked store will use this same destination and account scope.';
  $('#combined-rule-stores').innerHTML=ideas.length?ideas.map(p=>'<label class="combined-store-row"><input type="checkbox" data-combined-store="'+e(combinedIdeaKey(p))+'" aria-label="Include '+e(p.patterns.join(' OR '))+' in combined rule"><span><strong>'+e(p.patterns.join(' OR '))+'</strong><small>'+p.count+' reviewed transactions · '+e(group.label)+'</small></span></label>').join(''):'<p class="field-hint">No stores match this search. Your other selections are kept.</p>';
  syncCombinedSelection();
}
function syncCombinedSelection(){
  const group=combinedGroup(),selected=combinedSelected(),visible=combinedVisibleIdeas(),ideas=group.ideas.filter(p=>selected.has(combinedIdeaKey(p))),phrases=combinedPatterns(ideas),max=state.automation?.maxPatterns||200;
  $$('[data-combined-store]',$('#combined-rule-stores')).forEach(el=>{el.checked=selected.has(el.dataset.combinedStore);el.closest('label').classList.toggle('selected',el.checked);});
  const all=$('#combined-rule-all'),checked=visible.filter(p=>selected.has(combinedIdeaKey(p))).length;
  all.checked=visible.length>0&&checked===visible.length;all.indeterminate=checked>0&&checked<visible.length;all.disabled=!visible.length;
  $('#combined-rule-visible').textContent='Showing '+visible.length+' of '+group.ideas.length+' stores'+(selected.size>checked?' · '+(selected.size-checked)+' selected outside this search':'')+'.';
  $('#combined-rule-summary').textContent=ideas.length+' stores selected · '+ideas.reduce((n,p)=>n+p.count,0)+' reviewed transactions · '+phrases.length+' merchant phrases in one '+group.label+' rule.';
  $('#combined-rule-limit').hidden=phrases.length<=max;$('#combined-rule-limit').textContent='One rule supports '+max+' merchant phrases. Leave some stores out, then create another combined rule for those stores.';
  $('#combined-rule-build').disabled=!ideas.length||phrases.length>max;$('#combined-rule-build').textContent=ideas.length?'Continue with '+ideas.length+' selected stores':'Continue with selected stores';
  $('[data-combined-clear]').disabled=!ideas.length;
}
function buildCombinedRule(){
  const group=combinedGroup(),selected=combinedSelected(),ideas=group.ideas.filter(p=>selected.has(combinedIdeaKey(p))),patterns=combinedPatterns(ideas);
  if(!patterns.length||patterns.length>(state.automation?.maxPatterns||200))return;
  $('#combined-rule-dialog').close();
  openAutomationRule(group.type,'',{patterns,accountId:group.accountId,businessId:group.businessId,category:group.category,treatment:group.treatment});
  ruleDesk.editor.combined={count:ideas.length,label:group.label};
  $('#automation-editor-title').textContent='One '+group.label+' rule for '+ideas.length+' stores.';
  $('#auto-combined-origin').hidden=false;$('#auto-combined-description').textContent='Only your '+ideas.length+' checked stores were added. '+proposalGroupScope(group)+'. Preview and save to accept them together.';
}
function autoCategoryOptions(selected=''){
  const business=$('#auto-business').value;
  $('#auto-category').innerHTML=quickOptions([['','Choose category'],...[...new Set(state.categories.filter(c=>(!c.business_id||c.business_id===business)&&!/uncategorized/i.test(c.name)).map(c=>c.name))].sort().map(c=>[c,c])],selected);
}
function syncAutoEditor(){
  const credit=$('#auto-kind').value==='credit',refund=credit&&$('#auto-treatment').value==='refund',destination=!credit||refund,hasBusiness=destination&&!!$('#auto-business').value,trusted=$('#auto-mode').value==='review';
  $('#auto-credit-field').hidden=!credit;$('#auto-destination').hidden=!destination;$('#auto-category-field').hidden=refund&&!hasBusiness;
  $('#auto-treatment').required=credit;
  const personalConflict=hasBusiness&&isPersonalCategory($('#auto-category').value);
  $('#auto-consistency-warning').hidden=!personalConflict;
  $('#auto-include').disabled=personalConflict;
  if(personalConflict)$('#auto-include').checked=false;
  $('#auto-business').disabled=!destination;$('#auto-business').required=!credit;$('#auto-category').disabled=!hasBusiness;$('#auto-category').required=hasBusiness;
  $('#auto-trust-fields').hidden=!trusted;$('#auto-trust').required=trusted;$('#auto-include-field').hidden=!hasBusiness;
  if(!trusted||!hasBusiness)$('#auto-include').checked=false;
  $('#auto-mode-help').textContent=({suggest:'Matching imports receive suggestions for you to apply.',categorize:'Matching imports receive the category or credit decision and remain awaiting review, outside expense totals.',review:'Matching imports are automatically reviewed. Expense inclusion is a separate explicit choice below.'})[$('#auto-mode').value];
}
document.querySelector('#auto-destination').insertAdjacentHTML('afterend','<div id="auto-consistency-warning" class="callout" hidden><p><strong>This category is personal.</strong> Business rules need a business category. Pause an existing conflicting rule or choose a different category.</p></div>');

function openAutomationRule(type='expense',id='',seed={}){
  if(!requireConnection())return;
  const rule=automationRules().find(r=>r.type===type&&r.id===id),c=rule?.conditions||{};
  $('#auto-combined-origin').hidden=true;
  ruleDesk.editor={id:id||null,type,preview:null};$('#automation-form').reset();$('#auto-kind').value=type;$('#auto-kind').disabled=!!id;
  $('#automation-editor-title').textContent=id?'Edit your import rule.':'Create an import rule.';
  $('#auto-patterns').value=(c.patterns||seed.patterns||(rule?[rule.pattern]:[])).join('\n');$('#auto-source-category').value=(rule?autoSourceCategories(c):seed.sourceCategories||(seed.sourceCategory?[seed.sourceCategory]:[])).join('\n');
  $('#auto-source-categories').innerHTML=[...new Set(state.transactions.map(t=>t.sourceCategory).filter(Boolean))].sort().map(c=>'<option value="'+e(c)+'"></option>').join('');
  $('#auto-account').innerHTML=quickOptions([['','All source accounts'],...state.accounts.map(a=>[a.id,accountName(a)])],rule?.account_id||seed.accountId||'');
  $('#auto-min').value=c.minCents!=null?c.minCents/100:'';$('#auto-max').value=c.maxCents!=null?c.maxCents/100:'';
  $('#auto-treatment').value=rule?.treatment||seed.treatment||'payment';
  $('#auto-business').innerHTML=quickOptions([['','Outside business books / choose business'],...state.businesses.map(b=>[b.id,b.display_name])],rule?.business_id||seed.businessId||(!['all','personal'].includes(state.workspace)?state.workspace:''));
  autoCategoryOptions(rule?.category_name||seed.category||'');$('#auto-mode').value=rule?.automation_mode||'categorize';$('#auto-include').checked=!!rule?.include_expenses;$('#auto-trust').checked=rule?.automation_mode==='review';
  invalidateAutoRule();syncAutoEditor();showDialog('automation-editor');
}
function autoRulePayload(){return {id:ruleDesk.editor.id||undefined,type:$('#auto-kind').value,patterns:$('#auto-patterns').value.split('\n').map(p=>p.trim()).filter(Boolean),sourceCategories:$('#auto-source-category').value.split('\n').map(s=>s.trim()).filter(Boolean),accountId:$('#auto-account').value||null,minAmount:$('#auto-min').value,maxAmount:$('#auto-max').value,businessId:$('#auto-business').disabled?null:$('#auto-business').value||null,category:$('#auto-category').disabled?'':$('#auto-category').value,treatment:$('#auto-kind').value==='credit'?$('#auto-treatment').value:'',mode:$('#auto-mode').value,includeInTotals:$('#auto-include').checked,...(ruleDesk.editor.groupSelection?{selectedIds:ruleDesk.editor.groupSelection.ids}:{})};}
function invalidateAutoRule(){if(ruleDesk.editor)ruleDesk.editor.preview=null;$('#auto-rule-preview').hidden=true;$('#auto-rule-submit').textContent='Preview rule';$('.form-error',$('#automation-form')).hidden=true;}
function automationPreviewTable(rows){return '<div class="quick-preview-table"><table><thead><tr><th>Transaction / amount</th><th>Decision / explanation</th></tr></thead><tbody>'+rows.map(r=>'<tr><td>'+e(r.description)+'<small>'+e(r.date)+' · '+money(r.amountCents)+'</small></td><td>'+e(r.new?.category_name||r.destination||r.sourceCategory||'No original category')+'<small>'+e(r.reason)+'</small>'+(r.new?'<small>'+e(r.new.status==='approved'?'Reviewed':'Awaiting review')+' · '+(r.new.include_in_totals?'Included in totals':'Outside totals')+'</small>':'<small>'+(r.eligible?'Eligible for automation':'Historical / requires separate review')+'</small>')+'</td></tr>').join('')+'</tbody></table></div>';}
function automationCountsMarkup(p){const labels={categorized:'Auto-categorized · review later',reviewed:'Automatically reviewed',suggested:'Rule suggestions',conflicts:'Conflicting rules',unmatched:'No matching rule',attention:'Needs separate attention'};return '<div class="automation-results">'+Object.entries(labels).map(([k,label])=>'<div><strong>'+p.counts[k]+'</strong><span>'+label+'</span></div>').join('')+'</div>';}
async function previewExistingAutomation(){
  if(ruleDesk.checking||!requireConnection())return;
  const buttons=$$('[data-auto-run]');
  ruleDesk.checking=true;ruleDesk.run=null;
  buttons.forEach(button=>{button.disabled=true;button.textContent='Checking rules…';button.setAttribute('aria-busy','true');});
  try{
    ruleDesk.run=await post('/api/automation/preview',{});
    const rows=ruleDesk.run.rows;
    $('#automation-run-preview').innerHTML=automationCountsMarkup(ruleDesk.run)+(rows.length?'<p><strong>'+rows.length+' proposed transaction changes.</strong> Nothing has been changed yet.</p>'+automationPreviewTable(rows)+'<p class="field-hint">Apply this preview to save these changes. Undo is available in Data & storage.</p>':'<p role="status"><strong>No automatic changes to apply.</strong> Suggest-only matches and conflicting rules still need your review.</p>');
    $('#automation-run-submit').disabled=!rows.length;
    $('.form-error',$('#automation-run')).hidden=true;
    showDialog('automation-run');
  }catch(error){toast(error.message);}
  finally{ruleDesk.checking=false;buttons.forEach(button=>{button.disabled=false;button.textContent='Run rule check';button.removeAttribute('aria-busy');});}
}
function showAutomationSummary(documentId,plan){
  const doc=state.documents.find(d=>d.id===documentId);plan=plan||doc?.metadata?.automation;if(!plan)return;
  ruleDesk.summary={documentId,plan};$('#automation-summary-title').textContent=doc?.filename||'Your import is organized.';
  $('#automation-summary-body').innerHTML=automationCountsMarkup(plan)+'<div class="automation-result-actions">'+[['categorized','Review categorized rows'],['reviewed','See automatically reviewed'],['suggested','Review suggestions'],['conflicts','Resolve rule conflicts'],['unmatched','Categorize unmatched rows'],['attention','Review attention rows']].filter(([key])=>plan.groups[key]?.length).map(([key,label])=>'<button class="button button-secondary" data-summary-group="'+key+'">'+label+' ('+plan.groups[key].length+')</button>').join('')+'</div>';
  const actionStatus=state.automation?.actionStatuses?.[plan.actionId];$('[data-summary-undo]').hidden=!plan.actionId;$('[data-summary-undo]').disabled=!!actionStatus&&actionStatus!=='active';$('[data-summary-undo]').textContent=actionStatus==='undone'?'Automatic decisions undone':actionStatus==='partially_undone'?'Partially undone · check Data & storage':'Undo automatic decisions';$('.form-error',$('#automation-summary')).hidden=true;showDialog('automation-summary');
}
function openAutomationResultGroup(key){
  const summary=ruleDesk.summary,ids=summary.plan.groups[key]||[];$('#automation-summary').close();state.workspace='all';$('#workspace-select').value='all';state.year='all';state.document=summary.documentId;state.query='';state.account='';state.tab='all';state.selected.clear();
  Object.assign(triage,{sourceCategory:'',category:'',classification:'',direction:'',from:'',to:'',min:'',max:'',focus:'all',merchant:'',sourceGroup:null,view:'rows',resultIds:new Set(ids)});navigate('transactions');
}
document.addEventListener('click',async event=>{
  const el=event.target;
  if(el.closest('[data-auto-new]'))openAutomationRule();
  if(el.closest('[data-auto-ideas]')){const ideas=$('#automation-rule-ideas');ideas.scrollIntoView({behavior:'smooth',block:'start'});ideas.focus({preventScroll:true});}
  if(el.closest('[data-auto-combine]'))openCombinedIdeas();
  const combinedGroupButton=el.closest('[data-auto-combine-group]');if(combinedGroupButton)openCombinedIdeas(combinedGroupButton.dataset.autoCombineGroup);
  if(el.closest('[data-combined-clear]')){combinedSelected().clear();syncCombinedSelection();}
  if(el.closest('[data-combined-back]')){$('#automation-editor').close();if(ruleDesk.editor.groupSelection){syncSelectedGroupRule();showDialog('selected-groups-rule');}else{renderCombinedStores();showDialog('combined-rule-dialog');}}
  const selectedRule=el.closest('[data-selected-groups-rule]');if(selectedRule)openSelectedGroupRule(selectedRule.dataset.selectedGroupsRule==='credit'?[...creditView.selected]:[...state.selected],selectedRule.dataset.ruleGrouping||'merchant');
  const sourceRule=el.closest('[data-source-category-rule]');if(sourceRule)openSelectedGroupRule(triage.groups[Number(sourceRule.dataset.sourceCategoryRule)][1].map(t=>t.id),'sourceCategory');
  if(el.closest('[data-selected-groups-all]')){ruleDesk.groupSelection.selected=new Set(ruleDesk.groupSelection.groups.filter(g=>g.pattern).map(g=>g.pattern));syncSelectedGroupRule();}
  if(el.closest('[data-selected-groups-none]')){ruleDesk.groupSelection.selected.clear();syncSelectedGroupRule();}
  const edit=el.closest('[data-auto-edit]');if(edit)openAutomationRule(edit.dataset.ruleType,edit.dataset.autoEdit);
  const category=el.closest('[data-auto-category]');if(category){const group=automationProposalGroups().find(g=>g.type==='expense'&&g.category===category.dataset.autoCategory);if(group)openCombinedIdeas(group.key);else openAutomationRule('expense','',{category:category.dataset.autoCategory});}
  const proposal=el.closest('[data-auto-proposal]');if(proposal){const p=JSON.parse(proposal.dataset.autoProposal);openAutomationRule(p.type,'',p);}
  const toggle=el.closest('[data-auto-toggle]');if(toggle){toggle.disabled=true;try{const r=automationRules().find(r=>r.id===toggle.dataset.autoToggle&&r.type===toggle.dataset.ruleType);await post('/api/automation/rules',{id:r.id,type:r.type,active:!r.active});await loadData({quiet:true});}catch(error){toast(error.message);toggle.disabled=false;}}
  if(el.closest('[data-auto-run]'))previewExistingAutomation();
  const summary=el.closest('[data-import-results]');if(summary)showAutomationSummary(summary.dataset.importResults);
  const group=el.closest('[data-summary-group]');if(group)openAutomationResultGroup(group.dataset.summaryGroup);
  if(el.closest('[data-summary-undo]')){const button=el.closest('[data-summary-undo]');button.disabled=true;try{const result=await post('/api/review/undo',{actionId:ruleDesk.summary.plan.actionId});await loadData({quiet:true});button.textContent=result.conflicts.length?'Undone where unchanged · '+result.conflicts.length+' conflicts':'Automatic decisions undone';toast(result.restored.length+' automatic decisions undone. Original imports remain available.');}catch(error){showError($('#automation-summary'),error);}}
  if(el.closest('[data-clear-import-result]')){triage.resultIds=null;state.document='';render();}
});
document.addEventListener('change',event=>{
  const el=event.target;
  if(el.matches('[data-combined-store]')){const selected=combinedSelected();el.checked?selected.add(el.dataset.combinedStore):selected.delete(el.dataset.combinedStore);syncCombinedSelection();}
  if(el.id==='combined-rule-all'){const selected=combinedSelected();combinedVisibleIdeas().forEach(p=>el.checked?selected.add(combinedIdeaKey(p)):selected.delete(combinedIdeaKey(p)));syncCombinedSelection();}
  if(el.id==='combined-rule-group'){ruleDesk.combine.key=el.value;ruleDesk.combine.query='';$('#combined-rule-search').value='';renderCombinedStores();}
  if(el.matches('[data-selected-rule-group]')){const selection=ruleDesk.groupSelection,pattern=selection.groups[Number(el.dataset.selectedRuleGroup)].pattern;el.checked?selection.selected.add(pattern):selection.selected.delete(pattern);syncSelectedGroupRule();}
  if(el.id==='selected-groups-target')syncSelectedGroupRule();
  if(el.id==='selected-groups-direction')refreshSelectedRulePicker();
  if(el.id==='automation-category'){ruleDesk.category=el.value;render();}
  if(el.id==='automation-type'){ruleDesk.type=el.value;render();}
  if(el.closest('#automation-form')){if(el.id==='auto-business')autoCategoryOptions($('#auto-category').value);invalidateAutoRule();syncAutoEditor();}
});
document.addEventListener('input',event=>{if(event.target.id==='combined-rule-search'){ruleDesk.combine.query=event.target.value;renderCombinedStores();}if(event.target.id==='automation-search'){ruleDesk.query=event.target.value;const start=event.target.selectionStart;render();$('#automation-search').focus();$('#automation-search').setSelectionRange(start,start);}if(event.target.closest('#automation-form'))invalidateAutoRule();});
document.querySelector('#combined-rule-form').addEventListener('submit',event=>{event.preventDefault();buildCombinedRule();});
document.querySelector('#selected-groups-rule-form').addEventListener('submit',event=>{event.preventDefault();buildSelectedGroupRule();});
document.querySelector('#automation-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,body=autoRulePayload(),fingerprint=JSON.stringify(body),hadPreview=ruleDesk.editor.preview===fingerprint;
  if(body.businessId&&isPersonalCategory(body.category)){showError(form,new Error('Personal / non-business cannot be assigned by a business rule. Choose a business category.'));return;}
  busy(form,true);
  try{if(hadPreview){const combined=ruleDesk.editor.combined,chosen=ruleDesk.editor.groupSelection;await post('/api/automation/rules',body);if(chosen)ruleDesk.groupSelection=null;if(combined)ruleDesk.combine=null;$('#automation-editor').close();await loadData({quiet:true});renderRuleList();toast((chosen?'Rule saved with '+chosen.count+' selected '+(chosen.grouping==='sourceCategory'?'statement category':'merchant')+' groups. ':combined?'Combined rule saved for '+combined.count+' stores. ':'Rule saved. ')+(body.mode==='suggest'?'Future imports receive suggestions.':'Future matching imports use this automation.'));}else{const p=await post('/api/automation/rules/preview',body);ruleDesk.editor.preview=fingerprint;$('#auto-rule-preview').innerHTML='<p><strong>'+p.matched+' historical matches · '+p.eligible+' eligible unreviewed candidates.</strong></p><p>Saving this rule changes future imports. Use “Run rule check” to preview changes to existing rows. Reviewed rows are shown for comparison and preserved.</p>'+automationPreviewTable(p.rows)+'<p class="field-hint">Showing up to 50 matches. Other rules and duplicate / transaction validation can change the final outcome.</p>';$('#auto-rule-preview').hidden=false;$('#auto-rule-submit').textContent='Save rule';}}
  catch(error){showError(form,error);}finally{busy(form,false);}
});
document.querySelector('#automation-run-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget;busy(form,true);try{const result=await post('/api/automation/apply',{revision:ruleDesk.run.revision});$('#automation-run').close();await loadData({quiet:true});toast(result.rows.length+' transactions updated. Undo is available in Data & storage.');}catch(error){showError(form,error);}finally{busy(form,false);}});
