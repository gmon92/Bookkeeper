'use strict';

const ruleLibrary={library:null,workspaceId:null,preview:null,busy:false,generation:0};
function ruleLibraryPanel(downloadOnly=false){
  return '<section class="panel rule-library-panel"><div><h2>'+(downloadOnly?'Rules & categories only':'Rules & categories file')+'</h2><p>Download a readable JSON file for the whole active profile, across all businesses and years. Edit it, then upload it in Rules & automation or Data & storage. Each rule keeps its account/business scope.</p></div><div class="rule-library-actions"><button class="button button-secondary" data-library-export>'+(downloadOnly?'Download rules file':'Export rules & categories')+'</button>'+(!downloadOnly?'<button class="button button-secondary" data-library-import>Upload edited rules file</button>':'')+'</div></section>';
}

document.body.insertAdjacentHTML('beforeend',`<dialog id="rule-library-dialog" class="modal quick-modal"><form id="rule-library-form"><div class="modal-top"><span class="eyebrow">REUSABLE SETUP</span><button type="button" class="icon-button" data-close="rule-library-dialog" aria-label="Close rules import">×</button></div><h2>Import rules & categories.</h2><p class="modal-description">Upload a setup or an edited export. The preview covers the whole active profile, regardless of page filters, while keeping each rule’s account/business scope. Existing category definitions stay in place. Transactions change only through the separate rule-check preview.</p><label class="field">Rules & categories JSON file<input id="rule-library-file" type="file" accept=".json,application/json"><span class="field-hint">Local Bookkeeper export · up to 5 MB</span></label><div id="rule-library-mappings" hidden><p id="rule-library-file-summary" class="field-hint"></p><label class="field">Existing rules<select id="rule-library-update"><option value="update">Update rules with matching keys and add new rules</option><option value="keep">Add only · keep existing rules unchanged</option></select><span class="field-hint">Keep rule keys when editing an export. Current and proposed settings are shown before updates. Entries omitted from the file are kept; set active to false to pause a rule.</span></label><h3>Match businesses</h3><p class="field-hint">Choose where business categories and rules belong. Shared categories remain shared. Add missing businesses before importing.</p><div id="rule-library-businesses"></div><h3>Match source accounts</h3><p class="field-hint">Choose an existing account for each scoped rule. Skipped accounts leave their rules out; they do not become rules for all accounts. Add missing accounts before importing.</p><div id="rule-library-accounts"></div><label class="quick-check"><input id="rule-library-automation" type="checkbox"><span><strong>Keep the file’s automation and expense-inclusion settings</strong><small>May enable trusted automatic review or inclusion on future imports. Leave unchecked to keep existing rules’ automation settings and start new rules as Suggest only. The file’s enabled/paused status is applied.</small></span></label><label class="quick-check"><input id="rule-library-check" type="checkbox" checked><span><strong>Open a rule check across the whole profile after import</strong><small>Preview existing unreviewed transactions across all businesses and years. Reviewed transactions are preserved; applying transaction changes is a separate step.</small></span></label></div><div id="rule-library-preview" class="quick-preview" hidden></div><p class="form-error" role="alert" hidden></p><div class="modal-footer"><button type="button" class="button button-secondary" data-close="rule-library-dialog">Cancel</button><button type="submit" class="button button-primary" id="rule-library-submit" disabled>Preview import</button></div></form></dialog>`);

function resetRuleLibrary(){
  ruleLibrary.generation++;
  Object.assign(ruleLibrary,{library:null,workspaceId:null,preview:null,busy:false});
  $('#rule-library-form').reset();
  $$('input,select,button',$('#rule-library-form')).forEach(el=>el.disabled=false);
  $('#rule-library-submit').disabled=true;
  $('#rule-library-submit').textContent='Preview import';
  $('#rule-library-preview').hidden=true;$('#rule-library-mappings').hidden=true;
  $('.form-error',$('#rule-library-form')).hidden=true;
  $('#rule-library-form').removeAttribute('aria-busy');
  if($('#rule-library-dialog').open)$('#rule-library-dialog').close();
}
function invalidateRuleLibrary(){
  ruleLibrary.preview=null;
  $('#rule-library-preview').hidden=true;
  $('#rule-library-submit').textContent='Preview import';
  $('#rule-library-submit').disabled=!ruleLibrary.library;
  $('.form-error',$('#rule-library-form')).hidden=true;
}
function libraryMappingOptions(source,collection,allowNames){
  const normalized=value=>String(value||'').normalize('NFKC').trim().toLowerCase();
  let match=collection.find(item=>item.id===source.key);
  if(!match&&allowNames){const candidates=collection.filter(item=>[item.display_name,item.legal_name].some(name=>[source.name,source.legalName].some(other=>other&&normalized(name)===normalized(other))));if(candidates.length===1)match=candidates[0];}
  return quickOptions([['','Skip this '+(allowNames?'business':'account')],...collection.map(item=>[item.id,allowNames?item.display_name:accountName(item)])],match?.id||'');
}
function renderLibraryMappings(){
  const library=ruleLibrary.library;
  $('#rule-library-file-summary').textContent=library.categories.length+' categories · '+library.rules.length+' rules in this file. Preview the mapped import before saving.';
  $('#rule-library-businesses').innerHTML=library.businesses.length?library.businesses.map(source=>'<label class="field">'+e(source.name)+' → destination business<select data-library-business="'+e(source.key)+'">'+libraryMappingOptions(source,state.businesses,true)+'</select></label>').join(''):'<p class="field-hint">No business-specific categories or rules.</p>';
  $('#rule-library-accounts').innerHTML=library.accounts.length?library.accounts.map(source=>'<label class="field">'+e(source.name)+(source.institution?' · '+e(source.institution):'')+' → destination account<select data-library-account="'+e(source.key)+'">'+libraryMappingOptions(source,state.accounts,false)+'</select></label>').join(''):'<p class="field-hint">No source-account mappings needed.</p>';
  $('#rule-library-mappings').hidden=false;
}
function libraryImportBody(){
  return {library:ruleLibrary.library,businessMap:Object.fromEntries($$('[data-library-business]').map(el=>[el.dataset.libraryBusiness,el.value||null])),accountMap:Object.fromEntries($$('[data-library-account]').map(el=>[el.dataset.libraryAccount,el.value||null])),preserveAutomation:$('#rule-library-automation').checked,updateRules:$('#rule-library-update').value==='update'};
}
function libraryRuleDetails(item){
  const lines=[];
  if(item.patterns?.length)lines.push('Merchant contains: '+item.patterns.join(' OR '));
  if(item.sourceCategories?.length)lines.push('Original category: '+item.sourceCategories.join(' OR '));
  if(item.minCents!=null)lines.push('Minimum '+money(item.minCents));
  if(item.maxCents!=null)lines.push('Maximum '+money(item.maxCents));
  lines.push((item.businessName||(item.businessId?businessName(item.businessId):item.sourceBusiness?'Unmapped business: '+item.sourceBusiness:'Shared / outside business books'))+' · '+(item.accountName||(item.accountId?accountName(state.accounts.find(account=>account.id===item.accountId)):item.sourceAccount?'Unmapped account: '+item.sourceAccount:'All source accounts')));
  lines.push((item.treatment?'Money in · ':'Money out · ')+(item.category||creditLabels[item.treatment]||''));
  lines.push((automationModes[item.mode]||item.mode)+' · '+(item.active?'Enabled':'Paused')+' · '+(item.includeInTotals?'Includes eligible expenses/refunds in totals':'Outside totals'));
  return lines.map(line=>'<small>'+e(line)+'</small>').join('');
}
function renderLibraryPreview(preview){
  const counts=preview.counts;
  const heading='<p><strong>'+counts.categoryAdd+' categories and '+counts.ruleAdd+' rules added · '+counts.ruleUpdate+' existing rules updated.</strong></p><p>'+counts.categoryKeep+' categories and '+counts.ruleKeep+' unchanged rules kept · '+counts.categorySkip+' categories and '+counts.ruleSkip+' rules skipped.</p><p>'+counts.trustedRules+' enabled trusted rules · '+counts.includeInTotalsRules+' enabled rules that can include expenses/refunds in totals among the additions/updates. This preview covers the whole profile; nothing has been saved yet.</p>';
  const table='<div class="rule-library-items quick-preview-table"><table><thead><tr><th>Item / proposed settings</th><th>Import decision</th></tr></thead><tbody>'+preview.items.map(item=>'<tr><td>'+e(item.label)+(item.kind==='rule'?(item.previous?'<div class="rule-library-before"><strong>Current rule</strong>'+libraryRuleDetails(item.previous)+'</div><strong>Proposed rule</strong>':'')+libraryRuleDetails(item):'<small>Category · '+(item.active?'Active':'Inactive')+' · '+e(item.businessId?businessName(item.businessId):item.sourceBusiness?'Unmapped business: '+item.sourceBusiness:'Shared category')+'</small>')+'</td><td><strong>'+e({add:'Add',update:'Update existing',keep:'Keep existing',skip:'Skip'}[item.status])+'</strong><small>'+e(item.reason)+'</small></td></tr>').join('')+'</tbody></table></div>';
  $('#rule-library-preview').innerHTML=heading+table;
  $('#rule-library-preview').hidden=false;
  $('#rule-library-submit').textContent='Apply to whole profile';
  $('#rule-library-submit').disabled=!(counts.categoryAdd+counts.ruleAdd+counts.ruleUpdate);
}
document.addEventListener('click',async event=>{
  if(event.target.closest('[data-library-import]')){if(!requireConnection())return;resetRuleLibrary();ruleLibrary.workspaceId=state.health.workspaceId;showDialog('rule-library-dialog');}
  const exportButton=event.target.closest('[data-library-export]');
  if(exportButton){
    if(!requireConnection())return;
    exportButton.disabled=true;
    try{
      const library=await api('/api/rule-library/export'),url=URL.createObjectURL(new Blob([JSON.stringify(library,null,2)],{type:'application/json'})),link=document.createElement('a');
      link.href=url;link.download='bookkeeper-rules-and-categories-'+new Date().toISOString().slice(0,10)+'.json';
      document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(error){toast(error.message);}finally{exportButton.disabled=false;}
  }
});
document.addEventListener('change',async event=>{
  const target=event.target;
  if(target.matches('[data-library-business],[data-library-account],#rule-library-automation,#rule-library-update'))invalidateRuleLibrary();
  if(target.id!=='rule-library-file')return;
  invalidateRuleLibrary();ruleLibrary.library=null;
  $('#rule-library-submit').disabled=true;$('#rule-library-mappings').hidden=true;
  const file=target.files?.[0],generation=++ruleLibrary.generation,workspaceId=ruleLibrary.workspaceId;
  if(!file)return;
  try{
    if(file.size>5*1024*1024)throw new Error('Choose a rules-and-categories file of at most 5 MB.');
    let library;
    try{library=JSON.parse(await file.text());}catch{throw new Error('This file is not valid JSON. Choose a Local Bookkeeper rules-and-categories export.');}
    if(generation!==ruleLibrary.generation||workspaceId!==state.health?.workspaceId||!$('#rule-library-dialog').open)return;
    await post('/api/rule-library/inspect',{library});
    if(generation!==ruleLibrary.generation||workspaceId!==state.health?.workspaceId||!$('#rule-library-dialog').open)return;
    ruleLibrary.library=library;renderLibraryMappings();invalidateRuleLibrary();
  }catch(error){if(generation===ruleLibrary.generation)showError($('#rule-library-form'),error);}
});
document.querySelector('#rule-library-form').addEventListener('submit',async event=>{
  event.preventDefault();
  if(ruleLibrary.busy||!ruleLibrary.library)return;
  const form=event.currentTarget,workspaceId=ruleLibrary.workspaceId,generation=ruleLibrary.generation;
  if(workspaceId!==state.health?.workspaceId){showError(form,new Error('The active profile changed. Reopen the import.'));return;}
  const body=libraryImportBody(),preview=ruleLibrary.preview,checkTransactions=$('#rule-library-check').checked;
  ruleLibrary.busy=true;
  $$('input,select,button',form).forEach(el=>el.disabled=true);form.setAttribute('aria-busy','true');
  try{
    const result=await post(preview?'/api/rule-library/apply':'/api/rule-library/preview',preview?{...body,revision:preview.revision}:body);
    if(generation!==ruleLibrary.generation||workspaceId!==state.health?.workspaceId)return;
    if(preview){$('#rule-library-dialog').close();await loadData({quiet:true});toast(result.counts.categoryAdd+' categories and '+result.counts.ruleAdd+' rules added; '+result.counts.ruleUpdate+' rules updated across the profile.');resetRuleLibrary();if(checkTransactions&&workspaceId===state.health?.workspaceId)await previewExistingAutomation();}
    else{ruleLibrary.preview=result;renderLibraryPreview(result);}
  }catch(error){if(generation===ruleLibrary.generation){invalidateRuleLibrary();showError(form,error);}}
  finally{
    if(generation===ruleLibrary.generation){ruleLibrary.busy=false;$$('input,select,button',form).forEach(el=>el.disabled=false);form.setAttribute('aria-busy','false');$('#rule-library-submit').disabled=!ruleLibrary.library||!!ruleLibrary.preview&&!(ruleLibrary.preview.counts.categoryAdd+ruleLibrary.preview.counts.ruleAdd+ruleLibrary.preview.counts.ruleUpdate);}
  }
});

document.querySelector('#rule-library-dialog').addEventListener('cancel',event=>{if(ruleLibrary.busy)event.preventDefault();});
