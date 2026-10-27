'use strict';

let statementBatch=null;
function batchWorkspaceMatches(){return statementBatch?.workspaceId===state.health?.workspaceId;}
function pendingStatementEntries(){return statementBatch?.entries.filter(item=>!item.result)||[];}
function batchReady(){
  const batch=statementBatch,pending=pendingStatementEntries();
  return !!batch&&pending.length>0&&batch.confirmed&&!!batch.settings.accountId&&pending.every(item=>item.preview&&!item.error);
}
async function discardStatementPreviews(tokens){if(tokens.length)await post('/api/imports/discard',{tokens});}
function openStatementImportMode(){if(requireConnection())showDialog('import-mode-dialog');}
async function readStatements(files,{batch:forceBatch=false}={}){
  const selected=Array.from(files||[]);
  if(!selected.length||!requireConnection()||state.loadingFile)return;
  if(statementBatch)return toast('Finish or cancel the current statement batch first.');
  if(selected.length===1&&!forceBatch)return readStatement(selected[0]);
  if(selected.length>25)return toast('Choose up to 25 statements at a time.');
  if(selected.reduce((sum,file)=>sum+file.size,0)>100*1024*1024)return toast('Choose a statement batch totaling 100 MB or less.');
  statementBatch={workspaceId:state.health.workspaceId,entries:[],index:0,committing:false,confirmed:false,
    settings:{accountId:'',rememberLayout:false,allowDuplicate:false,sourceGroups:!!state.health.profile?.settings?.groupImportsBySourceCategory}};
  const batch=statementBatch;state.loadingFile=true;
  try{
    for(const file of selected){
      const item={file,preview:null,error:'',result:null};batch.entries.push(item);
      toast('Reading statement '+batch.entries.length+' of '+selected.length+'…');
      try{
        if(!/\.(csv|xlsx|pdf)$/i.test(file.name))throw new Error('Choose a CSV, XLSX or supported Chase checking PDF statement.');
        if(file.size>20*1024*1024)throw new Error('Each statement must be 20 MB or smaller.');
        if(!batchWorkspaceMatches())throw new Error('The active profile changed. Cancel this batch and select the files again.');
        item.preview=await post('/api/imports/preview',{filename:file.name,contentBase64:await fileBase64(file)});
        if(!batchWorkspaceMatches())throw new Error('The active profile changed. Cancel this batch and select the files again.');
        if(batch.entries.some(other=>other!==item&&other.preview?.fileHash===item.preview.fileHash)){
          item.preview.alreadyImported=true;item.preview.duplicateInBatch=true;
        }
      }catch(error){item.error=error.message;}
    }
    populateStatementBatchSettings();displayStatementEntry(0);
  }finally{state.loadingFile=false;}
}
function populateStatementBatchSettings(){
  const settings=statementBatch.settings;
  $('#batch-import-account').innerHTML=accountOptions(settings.accountId);
  $('#batch-remember-layout').checked=settings.rememberLayout;
  $('#batch-allow-duplicates').checked=settings.allowDuplicate;
  $('#batch-source-groups').checked=settings.sourceGroups;
  $('#batch-import-confirm').checked=statementBatch.confirmed;
}
function displayStatementEntry(index){
  if(!statementBatch||statementBatch.committing)return;
  statementBatch.index=index;
  const item=statementBatch.entries[index];state.preview=item.preview;
  $('#import-details').hidden=!item.preview||!!item.result;
  if(item.preview)openImportPreview();
  else{$('#import-description').textContent=item.file.name;showDialog('import-dialog');}
  $('#import-description').textContent=item.file.name+' · Review this statement’s extraction. The shared account and settings apply to every file in the batch.';
  // The batch panel owns the single account/settings choice. Per-file controls
  // remain available to the independent single-file workflow only.
  $('#import-account-row').hidden=true;$('#mapping-confirmation').hidden=true;$('#duplicate-confirmation').hidden=true;
  $('#import-account').value=statementBatch.settings.accountId;
  if(item.preview)updateLayoutMemory();
  $('#remember-import-layout')?.closest('label')?.setAttribute('hidden','');
  $('#import-source-batch')?.closest('section')?.setAttribute('hidden','');
  renderStatementBatch();
  if(item.error)showError($('#import-form'),new Error(item.error));
}
function renderStatementBatch(){
  const batch=statementBatch;$('#import-batch').hidden=!batch;if(!batch)return;
  const item=batch.entries[batch.index],pending=pendingStatementEntries();
  $('#import-batch-file').innerHTML=quickOptions(batch.entries.map((entry,index)=>[String(index),
    (index+1)+'. '+entry.file.name+' · '+(entry.result?'Imported':entry.error?'Needs attention':'Ready to preview')]),String(batch.index));
  $('#import-batch-status').textContent=batch.entries.filter(entry=>entry.result).length+' imported · '+pending.length+' remaining. Every file uses the account and settings below. Use the statement picker to inspect each preview.';
  $('#import-batch-summary').innerHTML='<ul>'+pending.map(entry=>'<li>'+e(entry.file.name)+' · '+(entry.preview?entry.preview.rowCount+' transactions':e(entry.error))+'</li>').join('')+'</ul>';
  $('#batch-duplicates-field').hidden=!pending.some(entry=>entry.preview?.alreadyImported);
  for(const selector of ['#import-batch-skip','#import-batch-reload'])$(selector).disabled=batch.committing||!!item.result;
  for(const selector of ['#import-batch-file','#batch-import-confirm'])$(selector).disabled=batch.committing;
  for(const selector of ['#batch-import-account','#batch-remember-layout','#batch-allow-duplicates','#batch-source-groups'])$(selector).disabled=batch.committing||batch.entries.some(entry=>entry.result);
  const duplicateBlocked=pending.some(entry=>entry.preview?.alreadyImported)&&!batch.settings.allowDuplicate;
  const submit=$('#import-submit');submit.formNoValidate=true;
  submit.disabled=batch.committing||!batchReady()||duplicateBlocked;
  submit.textContent=batch.committing?'Importing statements…':'Import '+pending.length+' statement'+(pending.length===1?'':'s')+' to this account';
}
async function submitStatementBatch(form){
  const batch=statementBatch;if(!batch||batch.committing)return;
  if(!batchWorkspaceMatches())throw new Error('The active profile changed. Cancel this batch and select the files again.');
  if(!batchReady())throw new Error('Choose the shared account, check the statement previews, and confirm the batch settings.');
  const pending=pendingStatementEntries();
  if(pending.some(item=>item.preview.alreadyImported)&&!batch.settings.allowDuplicate)throw new Error('Remove duplicate files or explicitly confirm re-importing them.');
  const {sourceGroups,...settings}=batch.settings;
  batch.committing=true;renderStatementBatch();$('#import-batch').setAttribute('aria-busy','true');
  try{
    const result=await post('/api/imports/commit-batch',{items:pending.map(item=>({token:item.preview.token,...settings,confirmMapping:true,confirmExtraction:true}))});
    result.imported.forEach((saved,index)=>{pending[index].result=saved;pending[index].error='';});
    if(result.failedIndex!==null){
      const failed=pending[result.failedIndex];failed.error=result.error;batch.confirmed=false;$('#batch-import-confirm').checked=false;
      batch.committing=false;displayStatementEntry(batch.entries.indexOf(failed));
      throw new Error(result.imported.length+' statements saved in this attempt. '+result.error+' Saved statements will not be imported again when you retry.');
    }
    await finishStatementBatch(batch);
  }finally{batch.committing=false;$('#import-batch').setAttribute('aria-busy','false');if(statementBatch)renderStatementBatch();}
}
async function finishStatementBatch(batch){
  const entries=batch.entries.slice(),count=entries.reduce((sum,item)=>sum+(item.result?.rowCount||0),0);
  statementBatch=null;state.preview=null;$('#import-dialog').close();resetStatementImportControls();
  await loadData({quiet:true});
  await saveProfilePreferences({groupImportsBySourceCategory:batch.settings.sourceGroups});
  state.workspace='all';state.year='all';state.document='';state.account='';state.query='';state.selected.clear();
  Object.assign(triage,{sourceCategory:'',category:'',classification:'',direction:'',from:'',to:'',min:'',max:'',focus:'all',merchant:'',sourceGroup:null,
    view:batch.settings.sourceGroups?'groups':'rows',grouping:batch.settings.sourceGroups?'sourceCategory':'merchant',resultIds:null});
  $('#workspace-select').value='all';navigate('imports');
  toast(entries.length+' statements imported · '+count+' transactions to '+accountName(state.accounts.find(account=>account.id===batch.settings.accountId))+'. Open each statement to review its rows or automation results.');
}
function resetStatementImportControls(){
  $('#import-batch').hidden=true;$('#import-details').hidden=false;$('#import-account-row').hidden=false;
  $('#import-submit').textContent='Import for review';$('#import-submit').disabled=false;$('#import-submit').formNoValidate=false;
}
async function reloadStatementEntry(){
  const batch=statementBatch,item=batch?.entries[batch.index];if(!item||item.result||batch.committing||state.loadingFile)return;
  if(!batchWorkspaceMatches())return showError($('#import-form'),new Error('The active profile changed. Cancel this batch and select the files again.'));
  state.loadingFile=true;batch.confirmed=false;$('#batch-import-confirm').checked=false;
  try{
    await discardStatementPreviews(item.preview?[item.preview.token]:[]);item.preview=null;item.error='';
    item.preview=await post('/api/imports/preview',{filename:item.file.name,contentBase64:await fileBase64(item.file)});
    if(batch.entries.some(other=>other!==item&&other.preview?.fileHash===item.preview.fileHash)){
      item.preview.alreadyImported=true;item.preview.duplicateInBatch=true;
    }
  }catch(error){item.error=error.message;}
  finally{state.loadingFile=false;displayStatementEntry(batch.index);}
}
document.addEventListener('change',event=>{
  const batch=statementBatch;if(!batch||batch.committing)return;
  if(event.target.id==='import-batch-file'){displayStatementEntry(Number(event.target.value));return;}
  if(['batch-import-account','batch-remember-layout','batch-allow-duplicates','batch-source-groups','batch-import-confirm'].includes(event.target.id)){
    if(event.target.id!=='batch-import-confirm'&&batch.entries.some(item=>item.result))return;
    if(event.target.id!=='batch-import-confirm')$('#batch-import-confirm').checked=false;
    batch.settings={accountId:$('#batch-import-account').value,rememberLayout:$('#batch-remember-layout').checked,
      allowDuplicate:$('#batch-allow-duplicates').checked,sourceGroups:$('#batch-source-groups').checked};
    batch.confirmed=$('#batch-import-confirm').checked;
    $('#import-account').value=batch.settings.accountId;
    if(state.preview)updateLayoutMemory();
    for(const item of batch.entries)if(item.preview&&!item.result)item.error='';
    renderStatementBatch();
  }
});
document.addEventListener('click',async event=>{
  const batch=statementBatch;if(!batch||batch.committing)return;
  try{
    if(event.target.closest('#import-batch-reload'))await reloadStatementEntry();
    if(event.target.closest('#import-batch-skip')){
      const item=batch.entries[batch.index];if(item.result)return;
      if(batchWorkspaceMatches())await discardStatementPreviews(item.preview?[item.preview.token]:[]);
      batch.entries.splice(batch.index,1);batch.confirmed=false;$('#batch-import-confirm').checked=false;
      if(!batch.entries.length){statementBatch=null;state.preview=null;$('#import-dialog').close();resetStatementImportControls();}
      else if(batch.entries.every(entry=>entry.result))await finishStatementBatch(batch);
      else displayStatementEntry(Math.min(batch.index,batch.entries.length-1));
    }
  }catch(error){showError($('#import-form'),error);}
});
document.querySelector('#import-dialog').addEventListener('cancel',event=>{if(statementBatch?.committing)event.preventDefault();});
document.querySelector('#import-dialog').addEventListener('close',()=>{
  const batch=statementBatch,tokens=batch?batch.entries.filter(item=>!item.result&&item.preview).map(item=>item.preview.token):state.preview?[state.preview.token]:[];
  const canDiscard=!batch||batchWorkspaceMatches();statementBatch=null;state.preview=null;resetStatementImportControls();
  if(canDiscard)discardStatementPreviews(tokens).catch(error=>toast(error.message));
});
