'use strict';

const batchReturns=[];
const batchParts={category:{dialog:'categorize-dialog',form:'categorize-form',scope:'categorize-scope-rows',summary:'categorize-scope-summary',submit:'categorize-submit',label:'category batch'},credit:{dialog:'credit-dialog',form:'credit-form',scope:'credit-scope',summary:'credit-scope-summary',submit:'credit-submit',label:'credit batch'}};
function batchFor(kind){return kind==='category'?triage.bulk:creditView.bulk;}
function initializeBatchSelection(batch,ids){batch.candidateIds=[...ids];batch.ids=[...ids];batch.issues=[];batch.busy=false;batch.sort=triage.sort||'date-desc';batch.workspaceId=state.health?.workspaceId;}
function batchCandidateRows(kind){return (batchFor(kind)?.candidateIds||[]).map(id=>state.transactions.find(t=>t.id===id)).filter(Boolean);}
function renderBatchScope(kind){
  const batch=batchFor(kind),parts=batchParts[kind];if(!batch)return;
  $('#'+parts.scope).innerHTML='<p class="batch-selection-help">Check the rows receiving this decision. Leaving a row out here only removes it from this batch.</p>'+transactionSortControl(batch.sort,'batch-'+kind)+'<table><thead><tr><th class="batch-checkbox-col"><input type="checkbox" data-batch-select-all="'+kind+'" aria-label="Include all rows in this '+parts.label+'"></th><th>Transaction / source account</th><th>Date / amount</th><th>Current category / books</th><th>Review</th></tr></thead><tbody>'+sortTransactionRows(batchCandidateRows(kind),batch.sort).map(t=>'<tr data-batch-scope-row="'+e(t.id)+'"><td><input type="checkbox" data-batch-row-select="'+kind+'" data-row-id="'+e(t.id)+'" aria-label="Include '+e(t.description)+' in this '+parts.label+'"></td><td>'+e(t.description)+'<small>'+e(t.account)+'</small><small class="batch-row-issue" hidden></small></td><td>'+e(formatDate(t.date))+'<small>'+signedMoney(t)+'</small></td><td>'+e(t.category)+'<small>'+e(t.classification==='business'?businessName(t.businessId):t.classification)+'</small></td><td><button type="button" class="text-button" data-batch-fix="'+kind+'" data-row-id="'+e(t.id)+'">Review transaction</button></td></tr>').join('')+'</tbody></table>';
  syncBatchScope(kind);
}
function syncBatchScope(kind){
  const batch=batchFor(kind),parts=batchParts[kind];if(!batch)return;
  const selected=new Set(batch.ids),rows=batchCandidateRows(kind),issues=new Map((batch.issues||[]).map(r=>[r.id,r.reason]));
  const total=rows.filter(t=>selected.has(t.id)).reduce((n,t)=>n+t.amountCents,0),omitted=rows.length-batch.ids.length;
  $('#'+parts.summary).textContent='See all '+rows.length+' transactions · '+batch.ids.length+' selected'+(omitted?' · '+omitted+' left out':'');
  const root=$('#'+parts.scope);
  $$('[data-batch-row-select]',root).forEach(el=>{el.checked=selected.has(el.dataset.rowId);});
  const all=$('[data-batch-select-all]',root);if(all){all.checked=rows.length>0&&selected.size===rows.length;all.indeterminate=selected.size>0&&selected.size<rows.length;}
  $$('[data-batch-scope-row]',root).forEach(el=>{const id=el.dataset.batchScopeRow;el.classList.toggle('batch-row-omitted',!selected.has(id));el.classList.toggle('batch-row-flagged',selected.has(id)&&issues.has(id));const issue=$('.batch-row-issue',el);issue.hidden=!issues.has(id);issue.textContent=issues.has(id)?(selected.has(id)?'Last preview: ':'Left out · ')+issues.get(id):'';});
  if(kind==='category'){
    $('#categorize-title').textContent='Categorize '+batch.ids.length+' of '+rows.length+' transactions.';
    $('#categorize-description').textContent=(batch.scope?batch.scope.label+' · ':'')+batch.ids.length+' selected · '+money(total)+' in activity. '+(omitted?omitted+' left out of this batch. ':'')+(batch.mode==='suggestions'?'Preview the suggestions for the checked rows.':'Your category and business decision will apply to the checked rows.');
    $('#bulk-business').required=batch.mode!=='suggestions'&&rows.some(t=>selected.has(t.id)&&(t.classification!=='business'||!t.businessId));
  }else{
    $('#credit-title').textContent='One decision for '+batch.ids.length+' of '+rows.length+' credits.';
    $('#credit-description').textContent=batch.ids.length+' selected · '+money(total)+' in money-in activity. '+(omitted?omitted+' left out of this batch. ':'')+'Preview the reporting effect before applying.';
  }
  $('#'+parts.submit).disabled=!!batch.busy||!batch.ids.length||!!batch.blocked;
  if(kind==='category')syncBulkConsistency();
}
function changeBatchSelection(kind,ids){
  const batch=batchFor(kind);if(!batch||batch.busy)return;
  const wanted=new Set(ids);batch.ids=batch.candidateIds.filter(id=>wanted.has(id)&&(kind!=='credit'||state.transactions.find(t=>t.id===id)?.direction==='credit'));
  if(kind==='category')invalidateBulk(true);
  else{
    invalidateCredit();batch.linkRequest++;batch.linkLoading=false;batch.candidates=[];
    $('#credit-related').innerHTML='<option value="">No linked transaction</option>';$('#credit-related-search').value='';
    syncCreditDecision();
    const row=batch.ids.length===1?state.transactions.find(t=>t.id===batch.ids[0]):null;
    $('#credit-unlink').hidden=!row?.relatedTransactionId;
    if(row)loadCreditCandidates(row.creditTreatment===$('#credit-treatment').value?row.relatedTransactionId:null);
  }
  syncBatchScope(kind);
}
function setBatchBusy(kind,value){
  const batch=batchFor(kind);if(!batch)return;const form=$('#'+batchParts[kind].form);batch.busy=value;
  if(value){batch.disabledControls=$$('button,input,select,textarea',form).map(el=>[el,el.disabled]);batch.disabledControls.forEach(([el])=>{el.disabled=true;});}
  else{(batch.disabledControls||[]).forEach(([el,disabled])=>{el.disabled=disabled;});batch.disabledControls=[];syncBatchScope(kind);resumeBatchReview();}
  form.setAttribute('aria-busy',String(value));
}
function attachBatchReturn(entry){
  const dialog=$('#'+entry.child),target=$('.drawer-content',dialog)||$('form',dialog);
  $('.batch-return-banner',dialog)?.remove();
  target.insertAdjacentHTML('afterbegin','<div class="batch-return-banner"><button type="button" class="text-button" data-return-to-batch>Back to '+batchParts[entry.kind].label+'</button><span>Your batch selection, business and category choices are saved. Save this review or go back to continue the batch.</span></div>');
}
function reviewBatchRow(kind,id,credit=false){
  const batch=batchFor(kind);if(!batch||batch.busy)return;
  if(credit)changeBatchSelection(kind,batch.ids.filter(value=>value!==id));
  const row=state.transactions.find(t=>t.id===id),creditId=row?.direction==='credit'?id:row?.relatedTransactionId;
  const entry={kind,batch,rowId:id,child:credit?'credit-dialog':'transaction-dialog',workspaceId:state.health?.workspaceId};
  batchReturns.push(entry);$('#'+batchParts[kind].dialog).close();
  if(credit)openCreditDecision([creditId]);else openEditor(id);
  attachBatchReturn(entry);
}
function routeEditorCreditFromBatch(id){
  const entry=batchReturns.at(-1);if(!entry||entry.child!=='transaction-dialog')return false;
  if(entry.kind==='credit'){$('#transaction-dialog').close();return true;}
  changeBatchSelection(entry.kind,entry.batch.ids.filter(value=>value!==entry.rowId));
  $('.batch-return-banner',$('#transaction-dialog'))?.remove();entry.child='credit-dialog';$('#transaction-dialog').close();openCreditDecision([id]);attachBatchReturn(entry);return true;
}
async function resumeBatchReview(){
  const entry=batchReturns.at(-1);if(!entry||entry.resuming||$('#'+entry.child).open)return;
  if(entry.child==='credit-dialog'&&creditView.bulk?.busy)return;
  entry.resuming=true;
  try{
    await loadData({quiet:true});
    if(batchReturns.at(-1)!==entry)return;
    if(batchFor(entry.kind)!==entry.batch){batchReturns.pop();$('.batch-return-banner',$('#'+entry.child))?.remove();return;}
    batchReturns.pop();$('.batch-return-banner',$('#'+entry.child))?.remove();
    if(state.health?.workspaceId!==entry.workspaceId){toast('The books changed. Start a new batch in the active books.');return;}
    if(!state.connected){toast('Reconnect to the local server before continuing this batch.');return;}
    if(entry.kind==='category')invalidateBulk();
    else{entry.batch.ids=entry.batch.ids.filter(id=>state.transactions.find(t=>t.id===id)?.direction==='credit');invalidateCredit();syncCreditDecision();}
    renderBatchScope(entry.kind);showDialog(batchParts[entry.kind].dialog);
    const target=$('[data-batch-row-select][data-row-id="'+CSS.escape(entry.rowId)+'"]',$('#'+batchParts[entry.kind].scope));target?.focus();
  }finally{entry.resuming=false;}
}
document.addEventListener('change',event=>{
  const el=event.target;
  if(el.matches('[data-batch-row-select]')){const kind=el.dataset.batchRowSelect,batch=batchFor(kind);changeBatchSelection(kind,el.checked?[...batch.ids,el.dataset.rowId]:batch.ids.filter(id=>id!==el.dataset.rowId));}
  if(el.matches('[data-batch-select-all]')){const kind=el.dataset.batchSelectAll;changeBatchSelection(kind,el.checked?batchFor(kind).candidateIds:[]);}
});
document.addEventListener('click',event=>{
  const fix=event.target.closest('[data-batch-fix]');if(fix){reviewBatchRow(fix.dataset.batchFix,fix.dataset.rowId);return;}
  const omit=event.target.closest('[data-batch-omit]');if(omit){const kind=omit.dataset.batchOmit;changeBatchSelection(kind,batchFor(kind).ids.filter(id=>id!==omit.dataset.rowId));return;}
  const flagged=event.target.closest('[data-batch-omit-attention]');if(flagged){const kind=flagged.dataset.batchOmitAttention,batch=batchFor(kind),bad=new Set(batch.issues.map(r=>r.id));changeBatchSelection(kind,batch.ids.filter(id=>!bad.has(id)));return;}
  const credit=event.target.closest('[data-batch-review-credit]');if(credit){reviewBatchRow('category',credit.dataset.rowId,true);return;}
  const back=event.target.closest('[data-return-to-batch]');if(back)back.closest('dialog').close();
});
document.addEventListener('close',resumeBatchReview,true);
document.addEventListener('cancel',event=>{const kind=Object.keys(batchParts).find(key=>batchParts[key].dialog===event.target.id);if(kind&&batchFor(kind)?.busy)event.preventDefault();},true);
