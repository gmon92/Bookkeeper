'use strict';

function extractionMarkup(extraction){
  if(!extraction)return '<p>Detailed extraction evidence was not saved for this older import.</p>';
  const labels={date:'Transaction date',postedDate:'Posted date',description:'Transaction / merchant',amount:'Amount',debit:'Money out',credit:'Money in',type:'Transaction type',sourceCategory:'Statement category'};
  const pdf=extraction.format==='pdf'||!!extraction.pageCount;
  const location=pdf?'PDF · '+extraction.pageCount+' pages':e(extraction.sheet||'CSV table')+' · header row '+extraction.headerRow;
  const selection=pdf?e(extraction.pdfTextPolicy):extraction.metadataRowsSkipped+' rows before the header and '+extraction.blankRowsSkipped+' blank rows skipped.'+(extraction.otherSheets.length?' Other sheets not imported as transactions: '+e(extraction.otherSheets.join(', '))+'.':'');
  return '<div class="extraction-facts"><span><strong>'+e(extraction.provider)+'</strong> · '+e(extraction.parserVersion)+'</span><span>'+location+' · '+extraction.rowCount+' rows</span></div><table class="mapping-table"><thead><tr><th>App field</th><th>Source column</th></tr></thead><tbody>'+Object.entries(extraction.columns).map(([key,column])=>'<tr><td>'+e(labels[key]||key)+'</td><td>Column '+(column.index+1)+' · <strong>'+e(column.header)+'</strong><small>'+e(column.purpose||'Read by the import adapter.')+'</small></td></tr>').join('')+'</tbody></table><ul class="extraction-reasons"><li>'+e(extraction.rowSelection)+'</li><li>'+selection+'</li><li>'+e(extraction.amountPolicy)+'</li><li>'+e(extraction.datePolicy)+'</li><li>'+e(extraction.categoryPolicy)+'</li></ul>';
}
function importExplanationMarkup(preview){
  const groupImports=!!state.health?.profile?.settings?.groupImportsBySourceCategory;
  const groups=preview.sourceCategoryGroups||[],hasCategory=!!preview.extraction?.columns?.sourceCategory;
  return '<details class="import-explanation" open><summary>How this statement was read</summary>'+extractionMarkup(preview.extraction)+'<div id="layout-memory" class="layout-memory"></div></details><p class="field-hint">Import also retains the original statement, preserves its cells or extracted PDF page text, and saves a separate transaction snapshot inside SQLite for later comparison.</p>'+(hasCategory?'<section class="import-category-groups"><strong>Batch using the statement’s category column</strong><p>Detected '+e(preview.extraction.columns.sourceCategory.header)+' · '+groups.length+' groups. Each group collects every transaction with the same original category description.</p><div class="source-category-example">'+groups.slice(0,8).map(g=>'<span>'+e(g.category||'No statement category')+' · '+g.count+'</span>').join('')+'</div><label class="quick-check"><input type="checkbox" id="import-source-batch"'+(groupImports?' checked':'')+'><span>After importing, automatically open statement category groups.<small>Remember this choice for future imports. Choose a business and category once per batch. Review and totals remain explicit choices.</small></span></label></section>':'<p class="field-hint">No category column detected. Merchant groups remain available after import.</p>')+'<label class="quick-check"><input type="checkbox" id="remember-import-layout"><span>Remember this confirmed layout for the selected source account.<small>Remembering a layout never approves transactions or includes expenses.</small></span></label>';
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
