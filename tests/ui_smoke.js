// 轻量 DOM 模拟：不调用模型、不依赖浏览器或第三方包。
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

function harness(script) {
  const elements = new Map();
  function element(id) {
    if (elements.has(id)) return elements.get(id);
    const e = {id, textContent:'', className:'', value:'', disabled:false, hidden:false, children:[], handlers:{}, dataset:{},
      append(...nodes){this.children.push(...nodes);}, replaceChildren(...nodes){this.children=nodes;},
      querySelector(selector){if(selector==='strong') return this.children.find(x=>x.tag==='strong'); return null;},
      addEventListener(type,fn){this.handlers[type]=fn;}, focus(){}, requestSubmit(){this.submitted=true;},
      setAttribute(name,value){this[name]=value;}};
    elements.set(id,e); return e;
  }
  const document = {getElementById:element, createElement(tag){return {tag,textContent:'',className:'',children:[],
    append(...x){this.children.push(...x);},querySelector(selector){return selector==='strong' ? this.children.find(x=>x.tag==='strong') : null;},
    remove(){},setAttribute(){}};}};
  const fetch = async url => {
    if(url==='/api/session') return {ok:true,json:async()=>({session_id:'test'})};
    if(url==='/api/recommendations') return {ok:true,json:async()=>({questions:['示例']})};
    if(url==='/api/super/settings') return {ok:true,json:async()=>({identities:[],policy:{mode:'observe',version:'v',owner_allowed:true,visitor_allowed:false,bot_allowed:true,rule_enabled:true}})};
    if(url==='/chat') return new Promise((resolve,reject)=>{context.pendingFetch={resolve,reject};});
    throw Error(`unexpected fetch ${url}`);
  };
  const context=vm.createContext({document,fetch,AbortController,TextDecoder,Date,Map,Math,JSON,Error,
    localStorage:{getItem(){return null;},setItem(){},removeItem(){}},renderRich(e,v){e.textContent=v;},
    setInterval,clearInterval,Promise,console});
  vm.runInContext(fs.readFileSync(script,'utf8'),context,{filename:script});
  return {context,element};
}

async function main() {
  const a=harness('app/static/app.js');
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.element('status').className,'badge ok');
  vm.runInContext("displayEvent({type:'tools_pending',calls:[{id:'a',function:{name:'search_docs',arguments:'{}'}}]})",a.context);
  vm.runInContext("displayEvent({type:'tool',tool_call_id:'a',name:'search_docs',success:false,arguments:'{}',result:'timeout',seconds:1})",a.context);
  assert.equal(a.element('events').children.at(-1).className,'event error');
  vm.runInContext("displayEvent({type:'error',message:'timeout'})",a.context);
  assert.equal(a.element('status').className,'badge err');
  vm.runInContext("displayEvent({type:'done',answer:'完成'})",a.context);
  assert.equal(a.element('status').className,'badge ok');
  vm.runInContext("displayEvent({type:'notice',guard:'token_budget',content:'预算已用完'}); displayEvent({type:'done',answer:'部分结果'})",a.context);
  assert.equal(a.element('status').textContent,'已停止并返回结果');
  assert.equal(a.element('status').className,'badge busy');
  const sent=vm.runInContext("send('测试')",a.context);
  assert.equal(a.element('stop').disabled,false);
  a.element('stop').onclick();
  a.context.pendingFetch.reject(Object.assign(new Error('aborted'),{name:'AbortError'}));
  await sent;
  assert.equal(a.element('status').textContent,'已停止接收');
  assert.equal(a.element('status').className,'badge busy');
  assert.equal(a.element('send').disabled,false);
  let prevented=false;
  a.element('question').handlers.keydown({key:'Enter',ctrlKey:true,metaKey:false,shiftKey:false,isComposing:false,preventDefault(){prevented=true;}});
  assert(prevented && a.element('form').submitted);

  const b=harness('app/static/super.js');
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext("showDecision({trigger_id:'x',decision:{verdict:'UNAVAILABLE',reason:'bad',mode:'auto'}})",b.context);
  assert.equal(b.element('status').className,'badge err');
  vm.runInContext("showDecision({trigger_id:'x',decision:{verdict:'WOULD_ACCEPT',reason:'observe',mode:'observe'}})",b.context);
  assert.equal(b.element('events').children.at(-1).className,'event stop');
  vm.runInContext("currentTicket={id:'old'}; showDecision({trigger_id:'x',decision:{verdict:'WOULD_ACCEPT',reason:'observe',mode:'observe'}})",b.context);
  assert(b.element('decision').textContent.includes('页面仍显示先前工单'));
  vm.runInContext("streamEvent({type:'agent_event',position:1,event:{type:'tool',name:'search_docs',tool_call_id:'x',success:false,arguments:'{}',result:'timeout'}})",b.context);
  assert.equal(b.element('events').children.at(-1).className,'event error');
  vm.runInContext("ticketStatus({status:'failed'})",b.context);
  assert.equal(b.element('status').className,'badge err');
  vm.runInContext("ticketStatus({status:'completed'})",b.context);
  assert.equal(b.element('status').className,'badge ok');
  console.log('UI 状态、事件分类、停止和快捷键模拟通过；未调用 LLM。');
}
main().catch(err=>{console.error(err);process.exitCode=1;});
