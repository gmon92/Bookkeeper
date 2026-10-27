'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

const root=path.join(__dirname,'..');
const safeguards=fs.readFileSync(path.join(root,'safeguards.js'),'utf8');
const app=fs.readFileSync(path.join(root,'app.js'),'utf8');
const apiSource=app.slice(app.indexOf('async function api('),app.indexOf('function connectionUI('));

function environment(approve=false){
  const prompts=[],requests=[],downloads=[],listeners={};
  const state={health:{workspaceId:'books-1',profile:{name:'Example books',ruleCount:30,
    rulesFile:'C:\\Books\\bookkeeper.rules.json',settings:{groupImportsBySourceCategory:false}}},
    accounts:[{id:'card',nickname:'Business card'}],businesses:[{id:'business',display_name:'Example LLC'}],
    automation:{rules:[{id:'rule-1',type:'expense',pattern:'OFFICE SHOP',active:1,account_id:'card',business_id:'business',automation_mode:'review',include_expenses:1}]},
    workspace:'all',year:'all',portableLedger:true};
  const context=vm.createContext({state,URLSearchParams,AbortSignal,location:{protocol:'http:'},
    window:{confirm:message=>{prompts.push(message);return approve;}},
    fetch:async(...args)=>{requests.push(args);return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({ok:true})};},
    requireConnection:()=>true,
    document:{body:{classList:{contains:()=>false}},addEventListener:(event,handler)=>{listeners[event]=handler;},
      createElement:()=>({click(){downloads.push(this.href);}})}});
  vm.runInContext(safeguards+'\n'+apiSource,context);
  return {context,prompts,requests,downloads,listeners};
}
const options=body=>({method:'POST',body:JSON.stringify(body)});

test('profile restore safeguard explains destination and rule differences',()=>{
  const {context}=environment();
  const description=context.protectedActionDescription('/api/setup',options({mode:'restore',directory:'C:\\Restored',sourceDirectory:'backup.zip'}));
  assert.equal(description.profile,'Example books');
  assert.match(description.details,/C:\\Restored/);
  assert.match(description.details,/SQLite databases include saved rules/);
  assert.match(description.details,/Excel and ZIP restores exclude rules/);
  assert.match(description.details,/existing profile is preserved/);
});

test('rule saves and toggles explain scope, future review and totals',()=>{
  const {context}=environment();
  const saved=context.protectedActionDescription('/api/automation/rules',options({type:'expense',businessId:'business',accountId:null,mode:'review',includeInTotals:true,patterns:['SUPPLIER']}));
  assert.match(saved.details,/all source accounts/);
  assert.match(saved.details,/Example LLC/);
  assert.match(saved.details,/reviewed automatically/);
  assert.match(saved.details,/totals automatically/);
  const paused=context.protectedActionDescription('/api/automation/rules',options({type:'expense',id:'rule-1',active:false}));
  assert.match(paused.title,/Pause/);
  assert.match(paused.details,/OFFICE SHOP/);
  assert.match(paused.details,/Business card/);
  assert.match(paused.details,/Future imports will stop using this rule/);
});

test('remembering a rule confirms all-account scope even for an account-specific transaction',()=>{
  const {context}=environment();
  const result=context.protectedActionDescription('/api/transactions/tx-1',{method:'PATCH',body:JSON.stringify({rememberRule:true,accountId:'card',ruleAccountId:null,ruleAllAccounts:true,ruleMode:'review',businessId:'business',includeInTotals:true})});
  assert.match(result.details,/all source accounts/);
  assert.match(result.details,/1 selected transaction/);
  assert.match(result.details,/previous rule with the same conditions may be replaced/);
});

test('JSON imports explain updates, additions and trusted future behavior',()=>{
  const {context}=environment();
  const result=context.protectedActionDescription('/api/automation/rules-json',options({rules:[{mode:'review',includeInTotals:true},{mode:'review',active:false}]}));
  assert.match(result.title,/2 JSON rule entries/);
  assert.match(result.details,/existing IDs update/);
  assert.match(result.details,/entries without IDs add/);
  assert.match(result.details,/Existing transactions are unchanged/);
  assert.match(result.details,/1 enabled entry can automatically review/);
});

test('mapped rules imports explain preserved automation and stay quiet during preview',()=>{
  const {context}=environment();
  assert.equal(context.protectedActionDescription('/api/rule-library/preview',options({})),null);
  assert.ok(context.protectedActionDescription('/api/rule-library/export'));
  const result=context.protectedActionDescription('/api/rule-library/apply',options({preserveAutomation:true}));
  assert.match(result.details,/business and account mappings/);
  assert.match(result.details,/keeping existing settings and transactions/);
  assert.match(result.details,/automatically affect future imports/);
});

test('personal rules explain classification and business exclusion',()=>{
  const {context}=environment();
  const result=context.protectedActionDescription('/api/automation/rules',options({type:'expense',businessId:'business',accountId:'card',category:'Personal / non-business',mode:'review'}));
  assert.match(result.details,/no business assignment/);
  assert.match(result.details,/excluded from business totals/);
});

test('read-only previews and ordinary view preferences do not trigger confirmations',()=>{
  const {context}=environment();
  for(const route of ['/api/health','/api/rules','/api/setup','/api/automation'])assert.equal(context.protectedActionDescription(route),null);
  for(const route of ['/api/automation/rules/preview','/api/automation/preview','/api/categorization/preview'])assert.equal(context.protectedActionDescription(route,options({})),null);
  assert.equal(context.protectedActionDescription('/api/profile/settings',options({sort:'amount-desc'})),null);
  assert.ok(context.protectedActionDescription('/api/profile/settings',options({groupImportsBySourceCategory:true})));
});

test('malformed JSON documents remain subject to normal server validation',()=>{
  const {context}=environment();
  for(const body of ['null','[]','"not an object"','{']){
    assert.equal(context.protectedActionDescription('/api/automation/rules-json',{method:'POST',body}),null);
  }
});

test('copy/open explains the JSON file write and external edits safeguard',()=>{
  const {context}=environment();
  const result=context.protectedActionDescription('/api/automation/rules-json/file',options({open:true}));
  assert.match(result.title,/Open/);
  assert.match(result.details,/all 30 saved rules/);
  assert.match(result.details,/C:\\Books\\bookkeeper.rules.json/);
  assert.match(result.details,/External edits are kept/);
  assert.match(result.details,/default application/);
});

test('cancelling protected API actions prevents every network request',async()=>{
  const actions=[['/api/setup',{mode:'open',directory:'C:\\Other books'}],['/api/profile/name',{name:'Renamed'}],
    ['/api/automation/rules',{id:'rule-1',type:'expense',active:false}],['/api/automation/rules-json',{rules:[]}],
    ['/api/automation/rules-json/file',{open:true}],['/api/automation/apply',{}],
    ['/api/categorization/apply',{rememberRule:true,ids:['a','b'],ruleMode:'review'}],
    ['/api/credits/apply',{rememberRule:true,ids:['credit']}],['/api/import-profiles/revoke',{id:'layout'}],
    ['/api/imports/commit',{token:'preview',rememberLayout:true}],['/api/review/undo',{actionId:'action'}]];
  for(const [route,body] of actions){
    const env=environment();
    await assert.rejects(env.context.api(route,options(body)),error=>error.cancelled===true);
    assert.equal(env.requests.length,0,route);
    assert.equal(env.prompts.length,1,route);
    assert.match(env.prompts[0],/Are you sure\?/);
    assert.match(env.prompts[0],/Profile: Example books/);
  }
});

test('approval sends the original request once with the correct profile identity',async()=>{
  const env=environment(true);
  const body={type:'expense',id:'rule-1',active:false};
  await env.context.post('/api/automation/rules',body);
  assert.equal(env.prompts.length,1);
  assert.equal(env.requests.length,1);
  assert.equal(env.requests[0][1].body,JSON.stringify(body));
  assert.equal(env.requests[0][1].headers['X-Bookkeeper-Workspace'],'books-1');
});

test('cancelled exports do not start downloads; approved exports download once',()=>{
  const start=app.indexOf("document.addEventListener('click',event=>{");
  const end=app.indexOf("document.addEventListener('change',event=>{",start);
  for(const approve of [false,true])for(const action of ['backup','export-database']){
    const env=environment(approve);
    vm.runInContext(app.slice(start,end),env.context);
    env.listeners.click({target:{closest:selector=>selector==='[data-action]'?{dataset:{action}}:null}});
    assert.equal(env.prompts.length,1,action);
    assert.equal(env.downloads.length,approve?1:0,action);
  }
});

function reportExportEnvironment(){
  const env=environment(false),shown=[],messages=[];
  const elements={'#report-export-format':{value:'xlsx'},'#report-export-description':{},'#report-export-scope':{},'#report-export-dialog':{close(){this.closed=true;}}};
  env.context.$=selector=>elements[selector];
  env.context.workspaceName=()=> 'Example LLC';
  env.context.showDialog=id=>shown.push(id);
  env.context.toast=message=>messages.push(message);
  vm.runInContext(app.slice(app.indexOf('let reportExport=null;'),app.indexOf('function openAccount(')),env.context);
  return {...env,elements,shown,messages};
}

test('export button opens a format chooser before starting a download',()=>{
  const start=app.indexOf("document.addEventListener('click',event=>{");
  const end=app.indexOf("document.addEventListener('change',event=>{",start);
  const env=reportExportEnvironment();
  vm.runInContext(app.slice(start,end),env.context);
  env.listeners.click({target:{closest:selector=>selector==='[data-action]'?{dataset:{action:'export'}}:null}});
  assert.equal(env.prompts.length,0);
  assert.deepEqual(env.shown,['report-export-dialog']);
  assert.deepEqual(env.downloads,[]);
  env.context.downloadReportExport();
  assert.deepEqual(env.downloads,['/api/export.xlsx?view=summary']);
  assert.ok(env.context.protectedActionDescription('/api/export.xlsx?view=ledger&portable=1'));
});

test('each report format preserves the selected business and year',()=>{
  for(const format of ['xlsx','csv','pdf']){
    const env=reportExportEnvironment();env.context.state.workspace='business';env.context.state.year='2025';
    env.context.openReportExport();env.elements['#report-export-format'].value=format;
    env.context.downloadReportExport();
    assert.deepEqual(env.downloads,[`/api/export.${format}?view=${format==='csv'?'transactions':'summary'}&businessId=business&year=2025`]);
    assert.equal(env.elements['#report-export-dialog'].closed,true);
  }
});

test('changed profile or filters block a stale export selection',()=>{
  for(const change of ['profile','year','business']){
    const env=reportExportEnvironment();env.context.openReportExport();
    if(change==='profile')env.context.state.health.workspaceId='different';
    if(change==='year')env.context.state.year='2025';
    if(change==='business')env.context.state.workspace='business';
    env.context.downloadReportExport();assert.deepEqual(env.downloads,[]);
    assert.match(env.messages[0],/profile or report filters changed/);
  }
  const env=reportExportEnvironment();
  assert.throws(()=>env.context.reportExportTarget('exe',{workspace:'all',year:'all'}),/Choose Excel, CSV or PDF/);
});

test('personal category rows stay outside report totals despite legacy inclusion flags',()=>{
  const env=environment();
  vm.runInContext(app.slice(app.indexOf('function included('),app.indexOf('function contribution(')),env.context);
  const row={excluded:false,status:'approved',classification:'business',includeInTotals:true,direction:'debit',kind:'expense',category:'Personal / non-business'};
  assert.equal(env.context.included(row),false);
  assert.equal(env.context.included({...row,category:'Office supplies'}),true);
});

function startupEnvironment(approve,startupError=false){
  const env=environment(approve),context=env.context;
  context.$=()=>({classList:{add(){},remove(){}}});
  context.toast=message=>env.messages.push(message);
  env.messages=[];
  for(const name of ['resetProfileView','populateWorkspaces','connectionUI','render'])context[name]=()=>{};
  context.triage={};context.creditView={};
  context.fetch=async(route,request)=>{
    env.requests.push([route,request]);
    let payload=[];
    const rulesFile=route==='/api/automation/rules-json/file';
    if(route==='/api/health')payload={setupRequired:false,workspaceId:'books-1',profile:context.state.health.profile};
    else if(route==='/api/automation')payload={rules:[]};
    else if(rulesFile)payload=startupError?{error:'File is read-only'}:{path:'C:\\Books\\bookkeeper.rules.json',created:false,exported:true,ruleCount:30,externalEdits:false};
    return {ok:!(startupError&&rulesFile),headers:{get:()=> 'application/json'},json:async()=>payload};
  };
  vm.runInContext(app.slice(app.indexOf('let startupRulesJsonAttempted=false;'),app.indexOf('async function handleReportRulesFile(')),context);
  vm.runInContext(app.slice(app.indexOf('async function loadData('),app.indexOf('function populateWorkspaces(')),context);
  return env;
}

test('loading the app refreshes rules JSON once without visiting Reports',async()=>{
  const env=startupEnvironment(true);
  env.context.state.page='overview';
  await env.context.loadData({quiet:true});
  await env.context.loadData({quiet:true});
  const refreshes=env.requests.filter(([route])=>route==='/api/automation/rules-json/file');
  assert.equal(refreshes.length,1);
  assert.equal(JSON.parse(refreshes[0][1].body).startup,true);
  assert.equal(env.prompts.length,1);
  assert.match(env.prompts[0],/as the app starts/);
  assert.match(env.prompts[0],/does not import JSON edits/);
  assert.equal(env.context.state.health.profile.rulesFileExists,true);
  assert.match(env.messages.at(-1),/updated with 30 saved rules/);
});

test('cancelling startup refresh keeps the app connected and does not repeat the prompt',async()=>{
  const env=startupEnvironment(false);
  await env.context.loadData({quiet:true});
  await env.context.loadData({quiet:true});
  assert.equal(env.requests.filter(([route])=>route==='/api/automation/rules-json/file').length,0);
  assert.equal(env.prompts.length,1);
  assert.equal(env.context.state.connected,true);
  assert.match(env.messages.at(-1),/Cancelled/);
});

test('a failed startup export leaves books connected and usable',async()=>{
  const env=startupEnvironment(true,true);
  await env.context.loadData({quiet:true});
  assert.equal(env.context.state.connected,true);
  assert.equal(env.context.state.ready,true);
  assert.match(env.messages.at(-1),/Rules JSON could not refresh: File is read-only/);
});
