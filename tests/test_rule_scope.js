'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function environment(){
  const elements=new Map(),choices=new Map();
  const $=selector=>{
    if(!elements.has(selector)){
      const element={value:'',checked:false,disabled:false,reset(){}};
      Object.defineProperty(element,'innerHTML',{set(options){
        choices.set(selector,options.items);this.value=options.selected;
      }});
      elements.set(selector,element);
    }
    return elements.get(selector);
  };
  const context=vm.createContext({$,state:{accounts:[{id:'amex',nickname:'Amex'},{id:'chase',nickname:'Chase'}],
    transactions:[],businesses:[],workspace:'all'},ruleDesk:{},savedRules:[],
    requireConnection:()=>true,automationRules:()=>context.savedRules,
    quickOptions:(items,selected)=>({items,selected}),accountName:a=>a.nickname,
    autoCategoryOptions:()=>{},invalidateAutoRule:()=>{},syncAutoEditor:()=>{},showDialog:()=>{},
    decisionRuleGroups:()=>[],autoSourceCategories:c=>c.sourceCategories||[]});
  const automation=fs.readFileSync(path.join(__dirname,'..','automation.js'),'utf8');
  vm.runInContext(automation.slice(automation.indexOf('function openAutomationRule('),automation.indexOf('function invalidateAutoRule(')),context);
  const categorize=fs.readFileSync(path.join(__dirname,'..','categorize.js'),'utf8');
  vm.runInContext(categorize.slice(categorize.indexOf('function initializeDecisionRule('),categorize.indexOf('function syncDecisionRule(')),context);
  vm.runInContext(categorize.slice(categorize.indexOf('function decisionRulePayload('),categorize.indexOf('function decisionRulePreview(')),context);
  return {context,$,choices};
}

test('a blank new rule never inherits universal or account scope from the previous rule',()=>{
  const {context,$,choices}=environment();
  for(const previous of ['*','amex','chase']){
    $('#auto-account').value=previous;
    context.openAutomationRule();
    assert.equal($('#auto-account').value,'');
    assert.throws(()=>context.autoRulePayload(),/Choose an account or Universal/);
  }
  assert.match(choices.get('#auto-account').find(([value])=>value==='*')[1],/Universal.*current and future/);
});

test('single-account seeds stay scoped; multi-account seeds require a choice',()=>{
  const {context,$}=environment();
  context.openAutomationRule('expense','',{accountId:'chase'});
  assert.equal($('#auto-account').value,'chase');
  assert.equal(context.autoRulePayload().accountId,'chase');
  context.openAutomationRule('expense','',{accountId:null});
  assert.equal($('#auto-account').value,'');
  $('#auto-account').value='*';
  assert.equal(context.autoRulePayload().accountId,null);
});

test('editing preserves the saved scope, including universal rules',()=>{
  const {context,$}=environment();
  for(const account of [null,'amex']){
    context.savedRules=[{id:'saved',type:'expense',account_id:account,pattern:'SHOP'}];
    context.openAutomationRule('expense','saved',{accountId:'chase'});
    assert.equal($('#auto-account').value,account??'*');
    assert.equal(context.autoRulePayload().accountId,account);
  }
});

test('remembering decisions resets scope and requires explicit universal selection across accounts',()=>{
  const {context,$}=environment();
  for(const prefix of ['edit','bulk','credit']){
    const selector='#'+prefix+'-rule-account';
    $(selector).value='*';
    context.initializeDecisionRule(prefix,[{accountId:'amex'}]);
    assert.equal($(selector).value,'amex');
    assert.equal($('#'+prefix+'-remember-rule').checked,false);
    context.initializeDecisionRule(prefix,[{accountId:'amex'},{accountId:'chase'}]);
    assert.equal($(selector).value,'');
    $('#'+prefix+'-remember-rule').checked=true;
    assert.throws(()=>context.decisionRulePayload(prefix,true),/Choose an account or Universal/);
    $(selector).value='*';
    const universal=context.decisionRulePayload(prefix,true);
    assert.equal(universal.ruleAllAccounts,true);
    assert.equal(universal.ruleAccountId,null);
    $(selector).value='chase';
    const scoped=context.decisionRulePayload(prefix,true);
    assert.equal(scoped.ruleAllAccounts,false);
    assert.equal(scoped.ruleAccountId,'chase');
  }
});
