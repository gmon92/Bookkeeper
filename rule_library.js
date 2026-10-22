'use strict';

const ruleLibrary={library:null,workspaceId:null,preview:null,busy:false,generation:0};
function ruleLibraryPanel(){
  return '<section class="panel rule-library-panel"><div><h2>Rules & categories file</h2><p>Export your setup as JSON, or import it into this profile without copying transactions. Includes every business and account scope, regardless of page filters.</p></div><div class="rule-library-actions"><button class="button button-secondary" data-library-export>Export rules & categories</button><button class="button button-secondary" data-library-import>Import rules & categories</button></div></section>';
}

document.body.insertAdjacentHTML('beforeend',`<dialog id="rule-library-dialog" class="modal quick-modal"><form id="rule-library-form"><div class="modal-top"><span class="eyebrow">REUSABLE SETUP</span><button type="button" class="icon-button" data-close="rule-library-dialog" aria-label="Close rules import">×</button></div><h2>Import rules & categories.</h2><p class="modal-description">Add a saved setup to this profile. Existing rules and category settings are kept. Transactions stay unchanged.</p><label class="field">Rules & categories JSON file<input id="rule-library-file" type="file" accept=".json,application/json"><span class="field-hint">Local Bookkeeper export · up to 5 MB</span></label><div id="rule-library-mappings" hidden><p id="rule-library-file-summary" class="field-hint"></p><h3>Match businesses</h3><p class="field-hint">Choose where business categories and rules belong. Shared categories remain shared. Add missing businesses before importing.</p><div id="rule-library-businesses"></div><h3>Match source accounts</h3><p class="field-hint">Choose an existing account for each scoped rule. Skipped accounts leave their rules out; they do not become rules for all accounts. Add missing accounts before importing.</p><div id="rule-library-accounts"></div><label class="quick-check"><input id="rule-library-automation" type="checkbox"><span><strong>Keep the file’s automation and expense-inclusion settings</strong><small>May enable trusted automatic review or inclusion on future imports. Leave unchecked to import rules as Suggest only. Paused rules stay paused.</small></span></label></div><div id="rule-library-preview" class="quick-preview" hidden></div><p class="form-error" role="alert" hidden></p><div class="modal-footer"><button type="button" class="button button-secondary" data-close="rule-library-dialog">Cancel</button><button type="submit" class="button button-primary" id="rule-library-submit" disabled>Preview import</button></div></form></dialog>`);

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
  return {library:ruleLibrary.library,businessMap:Object.fromEntries($$('[data-library-business]').map(el=>[el.dataset.libraryBusiness,el.value||null])),accountMap:Object.fromEntries($$('[data-library-account]').map(el=>[el.dataset.libraryAccount,el.value||null])),preserveAutomation:$('#rule-library-automation').checked};
}
function renderLibraryPreview(preview){
  const counts=preview.counts;
  const heading='<p><strong>'+counts.categoryAdd+' categories and '+counts.ruleAdd+' rules will be added.</strong></p><p>'+counts.categoryKeep+' categories and '+counts.ruleKeep+' identical rules kept · '+counts.categorySkip+' categories and '+counts.ruleSkip+' rules skipped.</p><p>'+counts.trustedRules+' enabled trusted rules · '+counts.includeInTotalsRules+' enabled rules that can include expenses/refunds in totals. Nothing has been imported yet.</p>';
  const table='<div class="rule-library-items quick-preview-table"><table><thead><tr><th>Item</th><th>Import decision</th></tr></thead><tbody>'+preview.items.map(item=>'<tr><td>'+e(item.label)+'<small>'+e(item.kind==='category'?'Category · '+(item.active?'Active':'Inactive'):'Rule · '+(item.mode==='review'?'Auto-review':item.mode==='categorize'?'Auto-categorize':'Suggest only')+' · '+(item.active?'Enabled':'Paused'))+'</small><small>'+e(item.businessId?businessName(item.businessId):item.sourceBusiness?'Unmapped business: '+item.sourceBusiness:'Shared / outside business books')+(item.kind==='rule'?' · '+e(item.accountId?accountName(state.accounts.find(account=>account.id===item.accountId)):item.sourceAccount?'Unmapped account: '+item.sourceAccount:'All accounts')+' · '+e(item.category||creditLabels[item.treatment]||''):'')+'</small>'+(item.includeInTotals?'<small>Includes eligible expenses/refunds in totals</small>':'')+'</td><td><strong>'+e({add:'Add',keep:'Keep existing',skip:'Skip'}[item.status])+'</strong><small>'+e(item.reason)+'</small></td></tr>').join('')+'</tbody></table></div>';
  $('#rule-library-preview').innerHTML=heading+table;
  $('#rule-library-preview').hidden=false;
  $('#rule-library-submit').textContent='Import this preview';
  $('#rule-library-submit').disabled=!(counts.categoryAdd+counts.ruleAdd);
}
document.addEventListener('click',async event=>{
  if(event.target.closest('[data-library-import]')){if(!requireConnection())return;resetRuleLibrary();ruleLibrary.workspaceId=state.health.workspaceId;showDialog('rule-library-dialog');}
  const exportButton=event.target.closest('[data-library-export]');
  if(exportButton){
    if(!requireConnection())return;
    exportButton.disabled=true;
    try{
      const library=await api('/api/rule-library/export'),url=URL.createObjectURL(new Blob([JSON.stringify(library)],{type:'application/json'})),link=document.createElement('a');
      link.href=url;link.download='bookkeeper-rules-and-categories-'+new Date().toISOString().slice(0,10)+'.json';
      document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(error){toast(error.message);}finally{exportButton.disabled=false;}
  }
});
document.addEventListener('change',async event=>{
  const target=event.target;
  if(target.matches('[data-library-business],[data-library-account],#rule-library-automation'))invalidateRuleLibrary();
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
  const body=libraryImportBody(),preview=ruleLibrary.preview;
  ruleLibrary.busy=true;
  $$('input,select,button',form).forEach(el=>el.disabled=true);form.setAttribute('aria-busy','true');
  try{
    const result=await post(preview?'/api/rule-library/apply':'/api/rule-library/preview',preview?{...body,revision:preview.revision}:body);
    if(generation!==ruleLibrary.generation||workspaceId!==state.health?.workspaceId)return;
    if(preview){$('#rule-library-dialog').close();await loadData({quiet:true});toast(result.counts.categoryAdd+' categories and '+result.counts.ruleAdd+' rules imported. Existing transactions were preserved.');resetRuleLibrary();}
    else{ruleLibrary.preview=result;renderLibraryPreview(result);}
  }catch(error){if(generation===ruleLibrary.generation){invalidateRuleLibrary();showError(form,error);}}
  finally{
    if(generation===ruleLibrary.generation){ruleLibrary.busy=false;$$('input,select,button',form).forEach(el=>el.disabled=false);form.setAttribute('aria-busy','false');$('#rule-library-submit').disabled=!ruleLibrary.library||!!ruleLibrary.preview&&!(ruleLibrary.preview.counts.categoryAdd+ruleLibrary.preview.counts.ruleAdd);}
  }
});

document.querySelector('#rule-library-dialog').addEventListener('cancel',event=>{if(ruleLibrary.busy)event.preventDefault();});
