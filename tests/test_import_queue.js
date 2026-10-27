'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function environment(){
  const elements=new Map(),listeners={},requests=[],messages=[];
  const $=selector=>{
    if(!elements.has(selector)){
      const element={value:'',checked:false,hidden:false,disabled:false,textContent:'',handlers:{},
        setAttribute(){},closest(){return {setAttribute(){}};},addEventListener(type,handler){this.handlers[type]=handler;},
        close(){this.open=false;this.handlers.close?.();},
        reportValidity:()=>!!$('#import-account').value&&$('#mapping-confirm').checked};
      Object.defineProperty(element,'innerHTML',{set(value){this.html=value;if(value&&typeof value==='object')this.value=value.selected;}});
      elements.set(selector,element);
    }
    return elements.get(selector);
  };
  let serial=0;
  const context=vm.createContext({$,triage:{},state:{health:{workspaceId:'books'},selected:new Set(),accounts:[{id:'card',nickname:'Amex'},{id:'bank',nickname:'Chase'}]},
    document:{addEventListener:(event,handler)=>{listeners[event]=handler;},querySelector:$},
    requireConnection:()=>true,fileBase64:async file=>file.content||file.name,
    readStatement:async file=>requests.push({single:file.name}),
    toast:message=>messages.push(message),quickOptions:(items,selected)=>({items,selected}),
    accountOptions:selected=>({items:[['','Choose an account'],['card','Amex'],['bank','Chase']],selected}),accountName:account=>account.nickname,e:String,showDialog:()=>{},updateLayoutMemory:()=>{},
    showError:(form,error)=>messages.push(error.message),loadData:async()=>{},saveProfilePreferences:async()=>true,navigate:()=>{},
    post:async(route,body)=>{
      requests.push({route,body});
      if(route==='/api/imports/preview'){
        if(body.filename==='broken.pdf')throw new Error('Unsupported PDF');
        return {token:'token-'+(++serial),filename:body.filename,fileHash:body.contentBase64,rowCount:2,alreadyImported:false};
      }
      if(route==='/api/imports/commit-batch')return {failedIndex:null,imported:body.items.map((item,index)=>({documentId:'document-'+index,rowCount:2}))};
      return {ok:true};
    },
    openImportPreview:()=>{
      $('#import-account').value='';$('#mapping-confirm').checked=false;$('#duplicate-confirm').checked=false;
      $('#remember-import-layout').checked=false;$('#import-source-batch').checked=false;
    }});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'..','import_queue.js'),'utf8'),context);
  const batch=()=>vm.runInContext('statementBatch',context);
  const confirm=async(account='card')=>{
    $('#batch-import-account').value=account;
    await listeners.change({target:{id:'batch-import-account'}});
    $('#batch-import-confirm').checked=true;
    await listeners.change({target:{id:'batch-import-confirm'}});
  };
  return {context,$,requests,messages,listeners,batch,confirm};
}
const files=[{name:'amex.csv',size:100},{name:'chase.pdf',size:100}];

test('single and batch inputs are separate and drag/drop passes every file',()=>{
  const root=path.join(__dirname,'..'),html=fs.readFileSync(path.join(root,'index.html'),'utf8');
  assert.match(html,/id="batch-file-input" multiple/);
  assert.doesNotMatch(html,/id="file-input" multiple/);
  assert.match(html,/Single file/);assert.match(html,/Batch upload/);
  const app=fs.readFileSync(path.join(root,'app.js'),'utf8');
  assert.match(app,/readStatements\(event.target.files,\{batch:true\}\)/);
  assert.match(app,/readStatements\(event.dataTransfer.files\)/);
});

test('one selected file keeps single mode unless batch was explicitly chosen',async()=>{
  const env=environment();await env.context.readStatements([files[0]]);
  assert.equal(env.requests[0].single,'amex.csv');assert.equal(env.batch(),null);
  await env.context.readStatements([files[0]],{batch:true});assert.equal(env.batch().entries.length,1);
});

test('one shared account and settings are sent identically for every file',async()=>{
  const env=environment();await env.context.readStatements(files);
  assert.equal(env.requests.length,2);
  await assert.rejects(env.context.submitStatementBatch(env.$('#import-form')),/shared account/);
  env.$('#batch-remember-layout').checked=true;env.$('#batch-source-groups').checked=true;await env.confirm('bank');
  env.context.displayStatementEntry(1);
  assert.equal(env.$('#batch-import-account').value,'bank');
  assert.equal(env.$('#batch-remember-layout').checked,true);
  assert.equal(env.context.batchReady(),true);
  await env.context.submitStatementBatch(env.$('#import-form'));
  const commits=env.requests.filter(request=>request.route==='/api/imports/commit-batch');
  assert.equal(commits.length,1);
  assert.deepEqual(Array.from(commits[0].body.items,item=>item.accountId),['bank','bank']);
  assert.deepEqual(Array.from(commits[0].body.items,item=>item.rememberLayout),[true,true]);
  assert.equal(env.batch(),null);assert.match(env.messages.at(-1),/2 statements imported.*4 transactions to Chase/);  assert.equal(env.context.triage.view,'groups');assert.equal(env.context.triage.grouping,'sourceCategory');
});

test('editing shared settings requires a fresh batch confirmation',async()=>{
  const env=environment();await env.context.readStatements(files);await env.confirm('card');
  env.$('#batch-import-account').value='bank';
  await env.listeners.change({target:{id:'batch-import-account'}});
  assert.equal(env.batch().confirmed,false);assert.equal(env.$('#batch-import-confirm').checked,false);
  assert.equal(env.context.batchReady(),false);
});

test('duplicates require explicit shared consent before importing',async()=>{
  const env=environment();await env.context.readStatements(files.map(file=>({...file,content:'same-bytes'})));
  assert.equal(env.batch().entries[0].preview.alreadyImported,false);
  assert.equal(env.batch().entries[1].preview.alreadyImported,true);
  await env.confirm('card');
  await assert.rejects(env.context.submitStatementBatch(env.$('#import-form')),/duplicate files/);
  env.$('#batch-allow-duplicates').checked=true;await env.confirm('card');
  await env.context.submitStatementBatch(env.$('#import-form'));
  const commit=env.requests.find(request=>request.route==='/api/imports/commit-batch');
  assert.equal(commit.body.items.every(item=>item.allowDuplicate===true),true);
});

test('bad files can be removed while valid previews and shared settings remain',async()=>{
  const env=environment();await env.context.readStatements([{name:'broken.pdf',size:100},files[0]]);await env.confirm('card');
  assert.equal(env.$('#import-submit').disabled,true);
  await env.listeners.click({target:{closest:selector=>selector==='#import-batch-skip'}});
  assert.equal(env.batch().entries.length,1);assert.equal(env.batch().settings.accountId,'card');
  assert.equal(env.batch().confirmed,false);await env.confirm('card');assert.equal(env.context.batchReady(),true);
});

test('cancel releases previews and a new batch starts without old account or settings',async()=>{
  const env=environment();await env.context.readStatements(files);
  env.$('#batch-remember-layout').checked=true;env.$('#batch-allow-duplicates').checked=true;await env.confirm('card');
  env.$('#import-dialog').close();
  assert.equal(env.batch(),null);assert.equal(env.context.state.preview,null);
  const discard=env.requests.find(request=>request.route==='/api/imports/discard');
  assert.deepEqual(Array.from(discard.body.tokens),['token-1','token-2']);
  await env.context.readStatements(files);
  assert.equal(env.batch().settings.accountId,'');assert.equal(env.batch().settings.rememberLayout,false);
  assert.equal(env.batch().settings.allowDuplicate,false);assert.equal(env.batch().confirmed,false);
});

test('changed profile and oversized selections cannot import',async()=>{
  const env=environment();await env.context.readStatements(Array(26).fill(files[0]));assert.equal(env.requests.length,0);
  await env.context.readStatements([{...files[0],size:101*1024*1024},files[1]]);assert.equal(env.requests.length,0);
  await env.context.readStatements(files);await env.confirm('card');env.context.state.health.workspaceId='different';
  await assert.rejects(env.context.submitStatementBatch(env.$('#import-form')),/profile changed/);
  assert.equal(env.requests.some(request=>request.route==='/api/imports/commit-batch'),false);
});

test('partial results keep settings fixed and retries submit only the remaining file',async()=>{
  const env=environment();await env.context.readStatements(files);await env.confirm('card');
  const originalPost=env.context.post;
  env.context.post=async(route,body)=>{
    if(route==='/api/imports/commit-batch')return {imported:[{documentId:'saved',rowCount:2}],failedIndex:1,error:'Temporary disk problem.'};
    return originalPost(route,body);
  };
  await assert.rejects(env.context.submitStatementBatch(env.$('#import-form')),/1 statements saved/);
  assert.equal(env.batch().entries[0].result.documentId,'saved');assert.equal(env.batch().index,1);
  assert.equal(env.$('#batch-import-account').disabled,true);
  env.context.post=originalPost;await env.context.reloadStatementEntry();
  env.$('#batch-import-confirm').checked=true;await env.listeners.change({target:{id:'batch-import-confirm'}});
  await env.context.submitStatementBatch(env.$('#import-form'));
  const retry=env.requests.find(request=>request.route==='/api/imports/commit-batch');
  assert.equal(retry.body.items.length,1);assert.equal(retry.body.items[0].accountId,'card');
});
