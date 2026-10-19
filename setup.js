'use strict';

const booksSetup = {info:null,mode:'create',directory:null,source:null,business:'',saving:false};

function setupGate(active){$('#sidebar').inert=active;document.body.classList.toggle('books-setup-active',active);}
function renderBooksSetup(){
  const info=booksSetup.info||state.health?.setup||{defaultDirectory:'',existingDirectories:[]};booksSetup.info=info;
  const mode=booksSetup.mode,configured=!!info.configured,candidates=info.existingDirectories||[];
  if(booksSetup.directory===null)booksSetup.directory=mode==='open'?(info.directory||candidates[0]||''):info.defaultDirectory;
  if(booksSetup.source===null)booksSetup.source=info.directory||candidates[0]||'';
  setupGate(true);$('#breadcrumb').textContent='Choose your books';$('#connection-banner').hidden=true;
  $('#connection-status').className='connection-status connected';$('#connection-status').textContent=configured?'Choose books':'Local setup';
  $('#page').innerHTML='<section class="books-setup"><span class="eyebrow">YOUR BOOKS. YOUR LOCATION.</span><h1>Give your books a home.</h1><p class="setup-lead">Choose a local folder for your database and original statements. The books stay separate from the app, ready to reopen after an update or reinstall.</p>'+(info.error?'<div class="callout"><p>'+e(info.error)+'</p></div>':'')+''+(candidates.length&&!configured?'<p class="setup-existing-note">Existing books were found. Choose Open or Copy to continue with those records.</p>':'')+'<div class="setup-modes" role="group" aria-label="Database setup">'+[['create','Create new books','Start with your first business.'],['open','Open existing books','Keep using a books folder you already have.'],['copy','Copy existing books','Keep the original and use a copy in a new folder.']].map(([key,title,description])=>'<button type="button" data-books-mode="'+key+'" aria-pressed="'+(mode===key)+'" class="'+(mode===key?'active':'')+'"><strong>'+title+'</strong><span>'+description+'</span></button>').join('')+'</div><form id="books-setup-form">'+(mode==='copy'?'<label class="field">Existing books folder<div class="setup-path"><input id="books-source" required value="'+e(booksSetup.source)+'" placeholder="Folder containing bookkeeper.sqlite3"><button type="button" class="button button-secondary" data-books-browse="source">Browse…</button></div></label>':'')+'<label class="field">'+(mode==='open'?'Existing books folder':mode==='copy'?'New destination folder':'New books folder')+'<div class="setup-path"><input id="books-directory" required value="'+e(booksSetup.directory)+'" placeholder="Choose an absolute folder path"><button type="button" class="button button-secondary" data-books-browse="directory">Browse…</button></div><span class="field-hint">'+(mode==='open'?'Select the folder containing bookkeeper.sqlite3 and its documents folder.':mode==='copy'?'Use a new or empty folder. Your original books will remain in place.':'A bookkeeper.sqlite3 database and documents folder will be created here. Existing databases will never be overwritten.')+'</span></label>'+(mode==='create'?'<label class="field">First business name<input id="books-business" required maxlength="200" value="'+e(booksSetup.business)+'" placeholder="e.g. Maple Street Services LLC"><span class="field-hint">You can add more businesses after setup.</span></label>':'')+(candidates.length?'<details class="setup-existing"><summary>Existing books found on this computer</summary>'+candidates.map(path=>'<button type="button" class="text-button" data-books-existing="'+e(path)+'">'+e(path)+'</button>').join('')+'</details>':'')+'<div class="setup-explainer"><strong>The app and the books travel separately.</strong><p>This folder contains your financial data and retained statements. Keep the whole folder together when moving or backing up. The app remembers its location for this user on this computer.</p></div><p class="form-error" role="alert" hidden></p><div class="modal-footer">'+(configured?'<button type="button" class="button button-secondary" data-books-cancel>Keep current books</button>':'')+'<button type="submit" class="button button-primary">'+(mode==='open'?'Open these books':mode==='copy'?'Copy and open books':'Create books')+' '+icon('arrow-right')+'</button></div></form></section>';
}
function captureSetup(){booksSetup.directory=$('#books-directory')?.value??booksSetup.directory;booksSetup.source=$('#books-source')?.value??booksSetup.source;booksSetup.business=$('#books-business')?.value??booksSetup.business;}
document.addEventListener('input',event=>{if(event.target.closest('#books-setup-form'))captureSetup();});
document.addEventListener('click',async event=>{
  const mode=event.target.closest('[data-books-mode]');if(mode&&!booksSetup.saving){captureSetup();booksSetup.mode=mode.dataset.booksMode;booksSetup.directory=null;renderBooksSetup();}
  const existing=event.target.closest('[data-books-existing]');if(existing&&!booksSetup.saving){captureSetup();if(booksSetup.mode==='copy')booksSetup.source=existing.dataset.booksExisting;else{booksSetup.mode='open';booksSetup.directory=existing.dataset.booksExisting;}renderBooksSetup();}
  const browse=event.target.closest('[data-books-browse]');if(browse&&!booksSetup.saving){
    captureSetup();browse.disabled=true;
    try{const result=await api('/api/setup/browse',{method:'POST',body:JSON.stringify({initial:booksSetup[browse.dataset.booksBrowse]||''}),signal:AbortSignal.timeout(190000)});if(result.directory){booksSetup[browse.dataset.booksBrowse]=result.directory;renderBooksSetup();}}
    catch(error){showError($('#books-setup-form'),error);}finally{browse.disabled=false;}
  }
  if(event.target.closest('[data-books-cancel]')&&!booksSetup.saving){state.setupEditing=false;setupGate(false);connectionUI();render();}
  if(event.target.closest('[data-action="choose-database"]')){
    try{booksSetup.info=await api('/api/setup');booksSetup.mode='open';booksSetup.directory=null;booksSetup.source=null;state.setupEditing=true;render();}catch(error){toast(error.message);}
  }
  const revoke=event.target.closest('[data-layout-revoke]');if(revoke){revoke.disabled=true;try{await post('/api/import-profiles/revoke',{id:revoke.dataset.layoutRevoke});await loadData({quiet:true});toast('Saved layout revoked. Future imports still require confirmation.');}catch(error){toast(error.message);revoke.disabled=false;}}
});
document.addEventListener('submit',async event=>{
  if(event.target.id!=='books-setup-form')return;
  event.preventDefault();captureSetup();const form=event.target;booksSetup.saving=true;
  $$('button,input',form).forEach(el=>el.disabled=true);
  try{
    await api('/api/setup',{method:'POST',body:JSON.stringify({mode:booksSetup.mode,directory:booksSetup.directory,sourceDirectory:booksSetup.source,businessName:booksSetup.business}),signal:AbortSignal.timeout(180000)});
    state.setupRequired=false;state.setupEditing=false;state.workspace='all';state.year='all';state.query='';state.account='';state.document='';state.preview=null;state.selected.clear();
    Object.assign(triage,{sourceCategory:'',category:'',classification:'',direction:'',from:'',to:'',min:'',max:'',focus:'all',merchant:'',sourceGroup:null,grouping:'merchant'});
    booksSetup.info=null;booksSetup.directory=null;setupGate(false);await loadData({quiet:true});navigate('overview');toast('Your books are open. Their location is saved on this computer.');
  }catch(error){showError(form,error);$$('button,input',form).forEach(el=>el.disabled=false);}
  finally{booksSetup.saving=false;}
});

function extractionMarkup(extraction){
  if(!extraction)return '<p>Detailed extraction evidence was not saved for this older import.</p>';
  const labels={date:'Transaction date',postedDate:'Posted date',description:'Transaction / merchant',amount:'Amount',debit:'Money out',credit:'Money in',type:'Transaction type',sourceCategory:'Statement category'};
  return '<div class="extraction-facts"><span><strong>'+e(extraction.provider)+'</strong> · '+e(extraction.parserVersion)+'</span><span>'+e(extraction.sheet||'CSV table')+' · header row '+extraction.headerRow+' · '+extraction.rowCount+' rows</span></div><table class="mapping-table"><thead><tr><th>App field</th><th>Source column</th></tr></thead><tbody>'+Object.entries(extraction.columns).map(([key,column])=>'<tr><td>'+e(labels[key]||key)+'</td><td>Column '+(column.index+1)+' · <strong>'+e(column.header)+'</strong><small>'+e(column.purpose||'Read by the import adapter.')+'</small></td></tr>').join('')+'</tbody></table><ul class="extraction-reasons"><li>'+e(extraction.rowSelection)+'</li><li>'+extraction.metadataRowsSkipped+' rows before the header and '+extraction.blankRowsSkipped+' blank rows skipped.'+(extraction.otherSheets.length?' Other sheets not imported as transactions: '+e(extraction.otherSheets.join(', '))+'.':'')+'</li><li>'+e(extraction.amountPolicy)+'</li><li>'+e(extraction.datePolicy)+'</li><li>'+e(extraction.categoryPolicy)+'</li></ul>';
}
function importExplanationMarkup(preview){
  let groupImports=false;try{groupImports=localStorage.getItem('bookkeeper.groupImportsBySourceCategory')==='true';}catch{}
  const groups=preview.sourceCategoryGroups||[],hasCategory=!!preview.extraction?.columns?.sourceCategory;
  return '<details class="import-explanation" open><summary>How this statement was read</summary>'+extractionMarkup(preview.extraction)+'<div id="layout-memory" class="layout-memory"></div></details><p class="field-hint">Import also saves original cell data and a separate transaction snapshot inside SQLite for later comparison.</p>'+(hasCategory?'<section class="import-category-groups"><strong>Batch using the statement’s category column</strong><p>Detected '+e(preview.extraction.columns.sourceCategory.header)+' · '+groups.length+' groups. Each group collects every transaction with the same original category description.</p><div class="source-category-example">'+groups.slice(0,8).map(g=>'<span>'+e(g.category||'No statement category')+' · '+g.count+'</span>').join('')+'</div><label class="quick-check"><input type="checkbox" id="import-source-batch"'+(groupImports?' checked':'')+'><span>After importing, automatically open statement category groups.<small>Remember this choice for future imports. Choose a business and category once per batch. Review and totals remain explicit choices.</small></span></label></section>':'<p class="field-hint">No category column detected. Merchant groups remain available after import.</p>')+'<label class="quick-check"><input type="checkbox" id="remember-import-layout"><span>Remember this confirmed layout for the selected source account.<small>Remembering a layout never approves transactions or includes expenses.</small></span></label>';
}
function updateLayoutMemory(){
  const p=state.preview,target=$('#layout-memory');if(!p||!target)return;
  const saved=(p.rememberedLayouts||[]).find(r=>r.account_id===$('#import-account').value);
  target.textContent=saved?'This exact layout was previously confirmed for this account on '+formatDate(saved.confirmed_at)+'. Confirm today’s extracted rows and amounts before saving.':'This layout has not been remembered for the selected account. Confirm the extraction below.';
}
document.addEventListener('change',event=>{if(event.target.id==='import-account')updateLayoutMemory();});
function importRowReason(row){
  const evidence=row.evidence;
  return evidence?'<details class="row-reason"><summary>Why these values?</summary><p>'+e(evidence.dateReason)+'</p><p>'+e(evidence.amountReason)+'</p><p>'+e(evidence.directionReason)+'</p><p>'+e(evidence.kindReason)+'</p><p>'+e(evidence.categoryReason)+'</p></details>':'';
}
async function loadTransactionExplanation(id){
  const target=$('#transaction-explanation');if(!target)return;target.textContent='Loading the source and decision evidence…';
  try{
    const info=await api('/api/transactions/'+encodeURIComponent(id)+'/explanation');if($('#transaction-form').elements.id.value!==id)return;
    const current=info.current,original=info.importEvidence;
    target.innerHTML=sourceComparisonMarkup(info.original,current)+'<div class="decision-card"><strong>Current category: '+e(current.category)+'</strong><p>'+e(info.categoryReason)+'</p>'+(info.categoryDecidedAt?'<small>'+e(formatDate(info.categoryDecidedAt))+'</small>':'')+'</div>'+(info.suggestion?'<div class="decision-card"><strong>'+(info.suggestion.conflict?'Conflicting suggestions':'Suggested: '+e(info.suggestion.category))+'</strong><p>'+e(info.suggestion.reason)+'</p></div>':'')+'<div class="decision-card"><strong>Current amount: '+money(current.amountCents)+' · '+e(current.direction)+'</strong><p>Kind: '+e(current.kind)+' · '+(current.includeInTotals?'Included in business totals by an explicit review decision.':'Outside business expense totals.')+'</p></div>'+(original?'<h4>Original import interpretation</h4>'+['dateReason','amountReason','directionReason','kindReason','categoryReason'].map(key=>'<p>'+e(original[key])+'</p>').join(''):'<p>This older row has no detailed import interpretation. Its original values are retained below.</p>')+'<details><summary>Source columns and original values</summary><div class="source-values"><table class="mapping-table"><tbody>'+info.sourceColumns.map(c=>'<tr><th>'+e(c.header)+'</th><td>'+e(c.value)+'</td></tr>').join('')+'</tbody></table></div></details><details><summary>Document column mapping</summary>'+extractionMarkup(info.extraction)+'</details>';
  }catch(error){target.textContent=error.message;}
}
function renderConfirmedLayouts(){
  const layouts=state.importProfiles||[];
  return '<h2>Confirmed import layouts</h2><p>Layouts remember the columns and interpretation you confirmed for a source account. Each import still shows its evidence and requires confirmation.</p>'+(layouts.length?layouts.map(p=>'<div class="confirmed-layout"><div><strong>'+e(p.provider)+' · '+e(p.format.toUpperCase())+'</strong><small>'+e(p.nickname)+(p.last_four?' ···· '+e(p.last_four):'')+' · '+e(formatDate(p.confirmed_at))+'</small></div><button class="text-button" data-layout-revoke="'+e(p.id)+'">Revoke</button></div>').join(''):'<p>No layouts remembered yet.</p>');
}
