'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {randomUUID}=require('node:crypto');
const app=fs.readFileSync(path.join(__dirname,'..','app.js'),'utf8');

function environment(){
  const elements=new Map(),requests=[],errors=[],events=[];
  const defaults={id:'',description:'',date:'',amount:'',accountId:'',businessId:'business',
    classification:'unknown',direction:'debit',kind:'expense',category:'Uncategorized / review',notes:''};
  const form={data:{...defaults},dataset:{workspaceId:'books',creationId:randomUUID()},elements:{},
    reset(){this.data={...defaults};},addEventListener(type,handler){this.handler=handler;}};
  for(const name of Object.keys(defaults)){
    const field={};Object.defineProperty(field,'value',{get:()=>form.data[name],set:value=>{form.data[name]=value;}});form.elements[name]=field;
  }
  form.elements.includeInTotals={checked:false,disabled:false};
  const mapped={'#transaction-form':form,'#edit-account':form.elements.accountId,'#edit-business':form.elements.businessId};
  const $=selector=>{
    if(mapped[selector])return mapped[selector];
    if(!elements.has(selector)){
      const element={textContent:'',checked:false,hidden:false,close(){events.push('closed');}};
      Object.defineProperty(element,'innerHTML',{set(value){this.html=value;if(value&&typeof value==='object'&&'selected' in value)this.value=value.selected;}});
      if(selector.includes('input[name=classification]'))Object.defineProperty(element,'checked',{set(value){if(value)form.data.classification='unknown';}});
      elements.set(selector,element);
    }
    return elements.get(selector);
  };
  for(const [selector,field] of Object.entries(mapped))if(selector!=='#transaction-form')Object.defineProperty(field,'innerHTML',{set(value){field.value=value.selected;}});
  const sections=[{hidden:false},{hidden:false}];
  const context=vm.createContext({$, $$:()=>sections,crypto:{randomUUID},Date,
    state:{health:{workspaceId:'books'},accounts:[{id:'card'}],businesses:[{id:'business'}],workspace:'all',selected:new Set()},triage:{},
    requireConnection:()=>true,toast:message=>events.push(message),openAccount:()=>events.push('account'),
    accountOptions:(selected='')=>({selected}),businessOptions:selected=>({selected}),
    setCategories:(business,category)=>{form.data.category=category;},syncEditor:()=>{},showDialog:()=>events.push('opened'),
    busy:()=>{},isPersonalCategory:name=>name==='Personal / non-business',decisionRulePayload:()=>({rememberRule:true,ruleAccountId:'card'}),
    showError:(form,error)=>errors.push(error.message),loadData:async()=>{},navigate:()=>{},
    post:async(route,body,method)=>{requests.push({route,body,method});return {id:'created'};},
    FormData:class {constructor(form){return new Map(Object.entries(form.data));}}});
  vm.runInContext(app.slice(app.indexOf('function openManualTransaction('),app.indexOf('function openEditor(')),context);
  vm.runInContext(app.slice(app.indexOf("$('#transaction-form').addEventListener('submit'"),app.indexOf("$('#batch-form').addEventListener('submit'")),context);
  return {context,form,$,requests,errors,events,sections,submit:()=>form.handler({preventDefault(){},currentTarget:form})};
}

test('new manual entry clears the previous amount, account, totals, notes and rule choice',()=>{
  const env=environment();Object.assign(env.form.data,{id:'old',amount:'250.00',description:'Old merchant',accountId:'card',notes:'Old note'});
  env.form.elements.includeInTotals.checked=true;env.$('#edit-remember-rule').checked=true;
  env.context.openManualTransaction();
  assert.equal(env.form.data.id,'');assert.equal(env.form.data.amount,'');assert.equal(env.form.data.accountId,'');
  assert.equal(env.form.data.notes,'');assert.equal(env.form.data.classification,'unknown');
  assert.equal(env.form.elements.includeInTotals.checked,false);assert.equal(env.$('#edit-remember-rule').checked,false);
  assert.equal(env.sections.every(section=>section.hidden),true);
  assert.match(env.form.data.date,/^\d{4}-\d{2}-\d{2}$/);
  const first=env.form.dataset.creationId;env.context.openManualTransaction();assert.notEqual(env.form.dataset.creationId,first);
});

test('manual save uses the create endpoint, exact cents, and no inherited rule',async()=>{
  const env=environment();env.context.openManualTransaction();
  Object.assign(env.form.data,{description:'Receipt',accountId:'card',date:'2026-10-27',amount:'12.05'});
  await env.submit();
  const request=env.requests[0];assert.equal(request.route,'/api/transactions');assert.equal(request.method,'POST');
  assert.equal(request.body.amountCents,1205);assert.equal(request.body.status,'needs_review');
  assert.equal(request.body.includeInTotals,false);assert.equal(request.body.requestId,env.form.dataset.creationId);
  assert.equal(request.body.rememberRule,undefined);assert.deepEqual(env.errors,[]);
});

test('only explicit eligible inclusion marks a manual transaction reviewed',async()=>{
  const env=environment();env.context.openManualTransaction();
  Object.assign(env.form.data,{description:'Receipt',accountId:'card',date:'2026-10-27',amount:'12.05',classification:'business',category:'Meals'});
  env.form.elements.includeInTotals.checked=true;await env.submit();
  assert.equal(env.requests[0].body.status,'approved');assert.equal(env.requests[0].body.includeInTotals,true);
});

test('failed save retains the request identity for a safe retry',async()=>{
  const env=environment();env.context.openManualTransaction();
  Object.assign(env.form.data,{description:'Receipt',accountId:'card',date:'2026-10-27',amount:'12.05'});
  const original=env.context.post;let first;
  env.context.post=async(route,body)=>{first=body.requestId;throw new Error('Connection interrupted');};
  await env.submit();assert.equal(env.events.includes('closed'),false);
  env.context.post=original;await env.submit();assert.equal(env.requests[0].body.requestId,first);
});

test('profile changes or invalid fractional amounts cannot create entries',async()=>{
  for(const value of ['12.345','-2','0']){
    const env=environment();env.context.openManualTransaction();env.form.data.amount=value;await env.submit();
    assert.equal(env.requests.length,0);assert.equal(env.errors.length,1);
  }
  const env=environment();env.context.openManualTransaction();env.context.state.health.workspaceId='another-profile';
  await env.submit();assert.equal(env.requests.length,0);assert.match(env.errors[0],/profile changed/);
});

test('existing transactions still use PATCH and their explicit saved-rule choices',async()=>{
  const env=environment();Object.assign(env.form.data,{id:'existing',description:'Receipt',date:'2026-10-27',amount:'12.05',accountId:'card'});
  await env.submit();assert.equal(env.requests[0].route,'/api/transactions/existing');assert.equal(env.requests[0].method,'PATCH');
  assert.equal(env.requests[0].body.requestId,undefined);assert.equal(env.requests[0].body.ruleAccountId,'card');
});

test('manual entry without an account opens account setup first',()=>{
  const env=environment();env.context.state.accounts=[];env.context.openManualTransaction();
  assert.equal(env.events.includes('account'),true);assert.equal(env.events.includes('opened'),false);
});
