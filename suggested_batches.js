'use strict';

const suggestedBatchView={expanded:false,pairsOpen:false,cards:[],pairs:[],workspaceId:null};

function suggestedPending(t){return t&&['needs_review','suggested'].includes(t.status)&&!t.excluded&&!t.duplicateOf&&!t.relatedTransactionId&&!t.consistencyIssue;}
function refreshSuggestedBatches(rows){
  const target=$('#suggested-batches');if(!target)return;
  const visible=new Set(rows.filter(suggestedPending).map(t=>t.id)),byId=new Map(state.transactions.map(t=>[t.id,t]));
  const scope=new Set(scopedTransactions().map(t=>t.id));
  const data=state.reviewBatches||{groups:[],pairs:[]};
  const cards=(data.groups||[]).map(group=>({...group,ids:group.ids.filter(id=>visible.has(id))})).filter(group=>group.ids.length);
  const pairs=[];
  for(const pair of data.pairs||[]){
    if(!visible.has(pair.creditId))continue;
    const candidates=pair.candidateIds.filter(id=>byId.has(id)&&scope.has(id));
    if(candidates.length)pairs.push({...pair,candidateIds:candidates});
    else cards.push({id:pair.id,ids:[pair.creditId],kind:'credits',title:'Credit needing a decision',category:'',
      question:'What does this credit represent? Its suggested purchase is outside these business books.',reason:'Review this credit separately.',treatment:null,parts:1});
  }
  suggestedBatchView.cards=cards;suggestedBatchView.pairs=pairs;suggestedBatchView.workspaceId=state.health?.workspaceId;
  const covered=new Set([...cards.flatMap(group=>group.ids),...pairs.map(pair=>pair.creditId)]),shown=suggestedBatchView.expanded?cards:cards.slice(0,6);
  target.innerHTML='<section class="panel suggested-batches-panel" aria-labelledby="suggested-batches-title"><div class="suggested-batches-heading"><div><h2 id="suggested-batches-title">Suggested batches</h2><p>Review similar charges together, then preview your decision. Business purpose still needs your confirmation.</p></div><span class="suggested-batches-count">'+covered.size+' pending rows in these filters</span></div>'+
    (cards.length?'<div class="suggested-batches-grid">'+shown.map(group=>{
      const transactions=group.ids.map(id=>byId.get(id)),amount=transactions.reduce((sum,t)=>sum+t.amountCents,0),index=cards.indexOf(group),first=transactions[0];
      return '<article class="suggested-batch-card" data-suggested-group="'+e(group.id)+'"><div class="suggested-batch-meta"><span>'+transactions.length+' '+(group.kind==='credits'?'credit':'charge')+(transactions.length===1?'':'s')+'</span><strong>'+money(amount)+'</strong></div><h3>'+e(group.title)+(group.parts>1?' · batch '+group.part+' of '+group.parts:'')+'</h3><p class="suggested-batch-account">'+e(first.account)+(group.businessId?' · '+e(businessName(group.businessId)):' · Business purpose unconfirmed')+'</p>'+(group.category?'<span class="category-tag">If business: '+e(group.category)+'</span>':'')+'<p class="suggested-batch-question">'+e(group.question)+'</p><p class="suggested-batch-reason">'+e(group.reason)+'</p><div class="suggested-batch-actions"><button type="button" class="button button-secondary button-small" data-suggested-review="'+index+'">'+(group.kind==='credits'?'Review credits':'Review '+transactions.length+' charges')+'</button>'+(group.kind!=='credits'?'<button type="button" class="text-button" data-suggested-personal="'+index+'">Personal…</button>':'')+'</div></article>';
    }).join('')+'</div>'+(cards.length>6?'<button type="button" class="text-button suggested-batches-more" data-suggested-more aria-expanded="'+suggestedBatchView.expanded+'">'+(suggestedBatchView.expanded?'Show fewer batches':'Show all '+cards.length+' batches')+'</button>':''):'')+
    (pairs.length?'<details id="suggested-refund-pairs" class="suggested-refund-pairs"'+(suggestedBatchView.pairsOpen?' open':'')+'><summary>Possible refunds and offsets · '+pairs.length+' credits</summary><p>Compare dates, amounts and purpose. A matching amount does not establish a refund or link the rows.</p><div class="suggested-pairs-list">'+pairs.map((pair,index)=>{
      const credit=byId.get(pair.creditId),purchases=pair.candidateIds.map(id=>byId.get(id));
      return '<article class="suggested-pair"><div><strong>'+e(pair.kind==='offset'?'Possible offset':'Possible refund')+' · '+money(credit.amountCents)+'</strong><p>'+e(credit.date)+' · '+e(credit.merchant||credit.description)+'</p><small>'+purchases.length+' purchase candidate'+(purchases.length===1?'':'s')+' · '+e(pair.reason)+'</small></div><button type="button" class="button button-secondary button-small" data-suggested-pair="'+index+'">Compare & review</button></article>';
    }).join('')+'</div></details>':'')+
    (!cards.length&&!pairs.length?'<p class="suggested-batches-empty">No suggested batches in these filters. Review individual rows or broaden the filters to find repeated charges.</p>':'')+'</section>';
}

document.querySelector('#categorize-description').insertAdjacentHTML('afterend','<p id="categorize-purpose-question" class="callout" hidden></p>');
document.querySelector('#credit-description').insertAdjacentHTML('afterend','<section id="suggested-credit-context" class="suggested-credit-context" hidden></section>');

function seedSuggestedCategory(scope){
  const question=$('#categorize-purpose-question');question.hidden=!scope?.question;question.textContent=scope?.question||'';
  if(scope?.suggestedCategory){
    const option=[...$('#bulk-category').options].find(item=>item.value.toLowerCase()===scope.suggestedCategory.toLowerCase());
    if(option){$('#bulk-category').value=option.value;syncBulkCustom();}
  }
}
function showSuggestedCreditContext(context){
  const target=$('#suggested-credit-context');target.hidden=!context;
  if(!context){target.innerHTML='';return;}
  const candidates=(context.candidateIds||[]).map(id=>state.transactions.find(t=>t.id===id)).filter(Boolean);
  target.innerHTML='<strong>'+e(context.question)+'</strong><p>'+e(context.reason)+'</p>'+(candidates.length?'<div class="quick-preview-table"><table><thead><tr><th>Possible purchase</th><th>Amount / current decision</th><th></th></tr></thead><tbody>'+candidates.map(t=>'<tr><td>'+e(t.date)+'<small>'+e(t.description)+'</small><small>'+e(t.account)+'</small></td><td>'+money(t.amountCents)+'<small>'+e(t.category)+' · '+e(t.classification)+'</small><small>'+(t.status==='approved'?'Already reviewed':'Awaiting review')+'</small></td><td><button type="button" class="text-button" data-batch-fix="credit" data-row-id="'+e(t.id)+'">Inspect purchase</button></td></tr>').join('')+'</tbody></table></div><p class="field-hint">'+(context.candidateCount>candidates.length?'Showing '+candidates.length+' of '+context.candidateCount+' candidates. ':'')+'Purchases are shown for comparison, including rows outside the current queue filters. Confirm the related purchase before linking. Benefits and points redemptions need their own treatment.</p>':'');
}

document.addEventListener('click',event=>{
  const review=event.target.closest('[data-suggested-review]'),personal=event.target.closest('[data-suggested-personal]'),pair=event.target.closest('[data-suggested-pair]');
  if(event.target.closest('[data-suggested-more]')){suggestedBatchView.expanded=!suggestedBatchView.expanded;refreshSuggestedBatches(filteredLedger());return;}
  if(!review&&!personal&&!pair)return;
  if(!requireConnection())return;
  if(suggestedBatchView.workspaceId!==state.health?.workspaceId){toast('The profile changed. Refresh the suggested batches before reviewing.');return;}
  if(pair){
    const item=suggestedBatchView.pairs[Number(pair.dataset.suggestedPair)];
    if(item&&suggestedPending(state.transactions.find(t=>t.id===item.creditId)))openCreditDecision([item.creditId],{...item,treatment:item.kind==='refund'?'refund':null});
    return;
  }
  const group=suggestedBatchView.cards[Number((review||personal).dataset[review?'suggestedReview':'suggestedPersonal'])];
  if(!group)return;
  const ids=group.ids.filter(id=>suggestedPending(state.transactions.find(t=>t.id===id)));
  if(!ids.length){toast('These transactions have already changed. Refresh to see the remaining batches.');return;}
  if(personal){openBatch('personal',ids);return;}
  if(group.kind==='credits')openCreditDecision(ids,{question:group.question,reason:group.reason,treatment:group.treatment});
  else openCategorize(ids,'categorize',{label:group.title,question:group.question,suggestedCategory:group.category});
});
document.addEventListener('toggle',event=>{if(event.target.id==='suggested-refund-pairs')suggestedBatchView.pairsOpen=event.target.open;},true);
