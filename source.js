'use strict';

const sourceViewer={id:'',sheet:null,offset:0,request:0};
document.body.insertAdjacentHTML('beforeend',`<dialog id="source-dialog" class="modal source-modal"><div class="source-modal-content"><div class="modal-top"><span class="eyebrow">ORIGINAL DATA IN SQLITE</span><button type="button" class="icon-button" data-close="source-dialog" aria-label="Close original data">×</button></div><h2 id="source-title">Original statement data</h2><p class="modal-description">These read-only records are stored separately from your editable transactions in the books database.</p><div id="source-archive-content"></div><p class="form-error" role="alert" hidden></p></div></dialog>`);

function sourceComparisonMarkup(original,current){
  if(!original)return '<p>No separate source snapshot is available for this transaction.</p>';
  const baseline=original.normalized;
  const fields=[['date','Date'],['postedDate','Posted date'],['description','Description'],['merchant','Merchant'],['amountCents','Amount'],['direction','Movement'],['kind','Kind'],['category','Your category'],['classification','Assignment']];
  const display=(key,value)=>key==='amountCents'?money(value):value||'—';
  return '<section class="original-comparison"><h4>Original import compared with current transaction</h4><p>Statement category: <strong>'+e(original.sourceCategory||'None supplied')+'</strong></p>'+(original.sourceCategory?'<button type="button" class="text-button" data-statement-batch="'+e(original.sourceCategory)+'">Group transactions with this statement category</button>':'')+(baseline?'<div class="source-values"><table class="mapping-table"><thead><tr><th>Field</th><th>At import</th><th>Current</th></tr></thead><tbody>'+fields.map(([key,label])=>'<tr class="'+(baseline[key]!==current[key]?'source-changed':'')+'"><th>'+label+'</th><td>'+e(display(key,baseline[key]))+'</td><td>'+e(display(key,current[key]))+(baseline[key]!==current[key]?'<small>Changed since import</small>':'')+'</td></tr>').join('')+'</tbody></table></div>':'<p>This older import has its retained original cells archived. A normalized snapshot from its original import time was not recorded; the source values below remain available for comparison.</p>')+'</section>';
}
function sourceColumnName(index){let name='';for(let n=index+1;n;n=Math.floor((n-1)/26))name=String.fromCharCode(65+(n-1)%26)+name;return name;}
async function showSourceArchive(id,sheet=null,offset=0){
  Object.assign(sourceViewer,{id,sheet,offset});const request=++sourceViewer.request;
  $('#source-title').textContent=state.documents.find(d=>d.id===id)?.filename||'Original statement data';
  $('#source-archive-content').textContent='Loading original data from SQLite…';showDialog('source-dialog');
  try{
    const params=new URLSearchParams({offset:String(offset)});if(sheet!==null)params.set('sheet',sheet);
    const archive=await api('/api/documents/'+encodeURIComponent(id)+'/source?'+params);if(sourceViewer.request!==request)return;
    sourceViewer.sheet=archive.sheet;
    const width=Math.max(0,...archive.rows.map(r=>r.cells.length));
    $('#source-archive-content').innerHTML='<p class="source-coverage">'+(archive.coverage==='all_cells'?'Archived cell data from every worksheet or CSV record, including headers and summary rows. Blank Excel cells are implicit in their row and column positions.':'Older import: only retained transaction rows are available. Other source rows could not be recovered from a matching original file.')+'</p><label class="field">Worksheet<select id="source-sheet">'+archive.sheets.map(s=>'<option value="'+e(s.name)+'"'+(s.name===archive.sheet?' selected':'')+'>'+e(s.name||'CSV records')+'</option>').join('')+'</select></label><div class="source-archive-table"><table><thead><tr><th>Source row</th>'+Array.from({length:width},(_,i)=>'<th>'+sourceColumnName(i)+'</th>').join('')+'</tr></thead><tbody>'+archive.rows.map(r=>'<tr><th>'+r.number+'</th>'+r.cells.map(c=>'<td title="'+e(c.type+': '+(c.value??''))+'">'+e(c.value??'')+'</td>').join('')+'</tr>').join('')+'</tbody></table></div><div class="source-pagination"><button type="button" class="button button-secondary" data-source-page="'+Math.max(0,offset-100)+'"'+(!offset?' disabled':'')+'>Previous</button><span>'+ (archive.total?offset+1:0)+'–'+Math.min(offset+archive.rows.length,archive.total)+' of '+archive.total+' stored rows</span><button type="button" class="button button-secondary" data-source-page="'+(offset+100)+'"'+(offset+100>=archive.total?' disabled':'')+'>Next</button></div><details class="source-hash"><summary>Original file fingerprint</summary><code>'+e(archive.fileHash)+'</code><p>The file fingerprint identifies the upload. This viewer reads cell records from SQLite and works without the original file. Spreadsheet formatting and images are retained only in the original file.</p></details>';
  }catch(error){if(sourceViewer.request===request)showError($('#source-dialog'),error);}
}
document.addEventListener('click',event=>{
  const source=event.target.closest('[data-source-archive]');if(source)showSourceArchive(source.dataset.sourceArchive);
  const page=event.target.closest('[data-source-page]');if(page)showSourceArchive(sourceViewer.id,sourceViewer.sheet,Number(page.dataset.sourcePage));
  const category=event.target.closest('[data-statement-batch]');if(category){$('#transaction-dialog').close();triage.grouping='sourceCategory';triage.view='groups';triage.merchant='';triage.sourceGroup=null;triage.sourceCategory=category.dataset.statementBatch;state.selected.clear();navigate('transactions');}
});
document.addEventListener('change',event=>{if(event.target.id==='source-sheet')showSourceArchive(sourceViewer.id,event.target.value,0);});
