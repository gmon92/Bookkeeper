'use strict';

function ruleSafeguardEffect(mode,include){
  const behavior=mode==='review'?'Eligible future matches will be marked reviewed automatically.':mode==='categorize'?'Future matches will be categorized automatically and left for review.':'Future matches will receive suggestions for you to review.';
  return behavior+(include?' Eligible business expenses or refunds can affect expense totals automatically.':' Matches stay outside expense totals until explicitly included.');
}
function ruleSafeguardScope(body){
  const accountId=body.rememberRule?(body.ruleAllAccounts?null:body.ruleAccountId):(body.accountId??body.account_id);
  const businessId=body.businessId??body.business_id;
  const account=state.accounts?.find(a=>a.id===accountId);
  const business=state.businesses?.find(b=>b.id===businessId);
  const personal=(body.type||'expense')==='expense'&&String(body.category??body.category_name??'').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}_]+/gu,' ').trim()==='personal non business';
  return 'Account scope: '+(accountId?(account?.nickname||accountId):'all source accounts in this profile')+'. '+
    (personal?'Personal matches have no business assignment and stay excluded from business totals.':'Business: '+(businessId?(business?.display_name||business?.legal_name||businessId):'outside business books')+'.');
}
function protectedActionDescription(path,options={}){
  const route=path.split('?')[0],method=(options.method||'GET').toUpperCase();
  let body={};
  if(options.body){try{body=JSON.parse(options.body);}catch(error){return null;}}
  if(!body||Array.isArray(body)||typeof body!=='object')return null;
  const profile=state.health?.profile?.name||'the selected profile';
  const savedRules=state.automation?.rules||[];
  const enabled=savedRules.filter(r=>r.active);
  const result=(title,details)=>({title,profile,details});
  if(method==='GET'){
    if(route==='/api/rule-library/export')return result('Export rules and categories?',
      'Downloads category settings and saved rules across every business and account scope. Transactions and source documents are omitted. The active profile stays unchanged.');
    if(route==='/api/automation/rules-json')return result('Export all rules as JSON?',
      'Downloads every saved expense and credit rule, including paused rules, across all businesses and accounts. The file also contains account/business IDs and category names. Saved rules and transactions are unchanged.');
    if(route==='/api/export.sqlite3')return result('Export the complete SQLite profile?',
      'Downloads all businesses and years, transactions, saved rules, account details, preferences and original row data. Report filters do not limit this file. Keep it somewhere appropriate for your bookkeeping data.');
    if(route==='/api/backup')return result('Download a full profile backup?',
      'Creates a ZIP containing the complete SQLite database, saved rules, preferences and retained original statements. ZIP restores omit rule definitions; recover those through the included SQLite database or a separate rules JSON export.');
    if(route==='/api/export.xlsx'&&new URLSearchParams(path.split('?')[1]||'').get('view')==='ledger'&&new URLSearchParams(path.split('?')[1]||'').get('portable')==='1')return result('Export an Excel ledger with reusable books?',
      'The visible report follows your filters. Its embedded books contain every business and year, transaction decisions and preferences, including data outside the visible report. Automation rule definitions are excluded.');
    return null;
  }
  if(route==='/api/rule-library/apply')return result('Import the previewed rules and categories?',
    'Applies the business and account mappings shown in the preview. Adds the previewed categories and rules while keeping existing settings and transactions. '+
    (body.preserveAutomation?'The file’s automation and expense-inclusion settings are retained and may automatically affect future imports.':'Imported rules use Suggest only and stay outside totals until you explicitly change them.'));
  if(route==='/api/setup'){
    const destination=body.directory||'the chosen location',source=body.sourceDirectory||'the uploaded file';
    const details={
      open:['Switch to the selected profile?','Opens '+destination+' as your active books, including that database’s transactions, rules and preferences. Current selections and filters are cleared. Your current profile stays saved at its existing location.'],
      create:['Create and open a new profile?','Creates independent books at '+destination+' for '+(body.profileName||body.businessName||'the new profile')+'. It starts with no transactions or saved rules and becomes your active profile. Existing books are preserved.'],
      copy:['Copy and open this profile?','Copies '+source+' into '+destination+', including transactions, saved rules, preferences and original documents. The copy becomes active and can be edited independently. The original profile is preserved.'],
      restore:['Restore and open exported books?','Restores '+source+' into '+destination+' and opens the new profile. The destination must be new or empty. SQLite databases include saved rules; Excel and ZIP restores exclude rules. Categories, transaction decisions and preferences come from the restored books. Your existing profile is preserved.']
    }[body.mode||'open'];
    return details?result(...details):null;
  }
  if(route==='/api/profile/name')return result('Rename this profile?',
    'Changes the profile name from “'+profile+'” to “'+body.name+'” in the database and profile locator. The database location, saved rules and transactions stay the same.');
  if(route==='/api/profile/settings'&&'groupImportsBySourceCategory' in body&&body.groupImportsBySourceCategory!==state.health?.profile?.settings?.groupImportsBySourceCategory)return result('Change this profile’s import grouping?',
    'New imports will open '+(body.groupImportsBySourceCategory?'in original statement category groups':'in transaction rows')+'. This preference is saved in the active profile and used when it is reopened. It does not create rules or recategorize transactions.');
  if(route==='/api/automation/rules-json'){
    const entries=Array.isArray(body.rules)?body.rules:[];
    const trusted=entries.filter(r=>r&&r.active!==false&&r.mode==='review').length;
    const totals=entries.filter(r=>r&&r.active!==false&&r.includeInTotals===true).length;
    return result('Import '+entries.length+' JSON rule entries?',
      'Entries with existing IDs update those rules; entries without IDs add rules. Identical additions are skipped, and omitted rules remain saved. The whole file is validated before saving. Existing transactions are unchanged.\n\n'+
      trusted+' enabled '+(trusted===1?'entry can':'entries can')+' automatically review future matches; '+totals+' can automatically affect business expense totals. Review the file’s account and business scopes before continuing.');
  }
  if(route==='/api/automation/rules-json/file')return result(body.startup?'Refresh the rules JSON as the app starts?':body.open?'Open the editable rules JSON?':'Copy the rules JSON location?',
    'Creates or refreshes the export at '+(state.health?.profile?.rulesFile||'the active profile folder')+' with all '+(state.health?.profile?.ruleCount??savedRules.length)+' saved rules. External edits are kept; import them explicitly to change saved rules. '+
    (body.refresh?'Replacing an externally edited file also saves a backup beside it. ':'')+
    (body.startup?'This startup refresh exports the saved rules only. It does not import JSON edits or change existing transactions.':body.open?'The file opens in your default application, or in a browser view when a desktop application is unavailable.':'The file path is copied to your clipboard.'));
  if(['/api/automation/rules','/api/rules','/api/credits/rules'].includes(route)){
    const type=body.type||(route==='/api/credits/rules'?'credit':'expense');
    const existing=savedRules.find(r=>r.id===body.id&&r.type===type);
    const activation=body.id&&typeof body.active==='boolean'&&Object.keys(body).every(k=>['id','type','active'].includes(k));
    if(activation)return result((body.active?'Enable':'Pause')+' this rule?',
      'Rule: '+(existing?.pattern||body.id)+'. '+ruleSafeguardScope(existing||body)+'\n\n'+
      (body.active?ruleSafeguardEffect(existing?.automation_mode||'suggest',!!existing?.include_expenses):'Future imports will stop using this rule. Previously reviewed or categorized transactions stay as they are.'));
    return result(body.id?'Save changes to this rule?':'Create this rule?',
      ruleSafeguardScope(body)+'\n\n'+ruleSafeguardEffect(body.mode||'suggest',!!body.includeInTotals)+
      ' Existing rows change only when you explicitly apply rules to them.');
  }
  if(route==='/api/automation/apply')return result('Apply saved rules to existing transactions?',
    'Applies the changes shown in your automation preview across the active profile. Rules may categorize, review or include eligible rows in totals according to their saved settings. Already reviewed rows and conflicts are protected. Undo is available in Data & storage.');
  if(body.rememberRule===true&&(['/api/categorization/apply','/api/credits/apply'].includes(route)||/^\/api\/transactions\/[^/]+$/.test(route)))return result('Save this transaction decision and a future-import rule?',
    'Saves the reviewed changes for '+(body.ids?.length||1)+' selected transaction(s) and remembers the decision for future matches. A previous rule with the same conditions may be replaced. '+
    ruleSafeguardScope(body)+'\n\n'+ruleSafeguardEffect(body.ruleMode||'suggest',body.ruleMode==='review'&&!!body.includeInTotals));
  if(route==='/api/import-profiles/revoke')return result('Revoke this saved import layout?',
    'Future statements with this layout will need their columns and amount interpretation confirmed again. Existing imported statements, saved transaction decisions and automation rules stay unchanged.');
  if(route==='/api/imports/commit'&&(enabled.length||body.rememberLayout))return result('Import this statement using this profile’s saved automation?',
    'Adds the previewed transactions and retains the original file. '+enabled.length+' enabled rules may categorize future matches; trusted rules may mark eligible rows reviewed or include expenses/refunds in totals. The rule definitions themselves are unchanged.'+
    (body.rememberLayout?' The confirmed column layout is also saved in this profile for future imports.':'')+' Automatic decisions can be undone after importing.');
  if(route==='/api/review/undo')return result('Undo this saved review action?',
    'Restores transactions covered by this action where they have not been edited later. Later changes are kept for separate review. Saved rules remain in place and can still affect future imports.');
  return null;
}
function confirmProtectedAction(path,options={}){
  const description=protectedActionDescription(path,options);
  return !description||window.confirm('Are you sure?\n\n'+description.title+'\nProfile: '+description.profile+'\n\n'+description.details+'\n\nSelect OK to continue. Cancel stops this action.');
}
