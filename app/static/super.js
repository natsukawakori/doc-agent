const $ = id => document.getElementById(id);
const labels = ['仅本地','谨慎联网','积极联网','每题联网'];
const help = ['不发起新的网页搜索或抓取；可判断是否使用已有材料。','本地证据不足、冲突或需要时效时，由模型考虑联网。','更积极地补充核对，但模型不保证每题联网。','每个新文档问题由程序尝试一次网页搜索。'];
let identities = [], ticketId = localStorage.getItem('super_ticket_id'), currentTicket = null, running = false, executing = false, policyDirty = false;
let finalBuffer = '';
const pending = new Map();

async function api(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  if (!response.ok) { let data; try { data = await response.json(); } catch { data = {}; } throw new Error(data.detail || `请求失败 (${response.status})`); }
  return response.json();
}
function post(url, body) { return api(url, {method:'POST',body:JSON.stringify(body)}); }
function setStatus(text, type) { $('status').textContent=text; $('status').className=`badge ${type}`; }
function showError(err) { setStatus('操作失败','err'); addEvent('提示', String(err.message || err),'error'); }
function ticketStatus(data) {
  const states={completed:['工单已完成','ok'],failed:['工单执行失败','err'],paused:['工单已暂停','busy'],pending:['工单待执行','busy'],running:['工单执行中','busy']};
  const state=states[data.status] || [`工单 ${data.status}`,'busy']; setStatus(...state);
}
function addEvent(title, content, type='') {
  const empty = $('events').querySelector('.empty'); if (empty) empty.remove();
  const box = document.createElement('div'); box.className=`event${type ? ' '+type : ''}`;
  const head = document.createElement('strong'); head.textContent=title;
  const body = document.createElement('div'); body.textContent=content || '';
  box.append(head,body); $('events').append(box);
  return {box,body};
}
function showIdentity() {
  const item=identities.find(x => x.role === $('role').value);
  $('identity-info').textContent = item ? `模拟 ID：${item.id}` : '';
  if ($('role').value === 'bot') $('kind').value='inferred';
}
function updateLevel() { const n=Number($('level').value); $('level-label').textContent=`${n} · ${labels[n]}`; $('level-help').textContent=help[n]; }
function setButtons() {
  const runnable = currentTicket && ['pending','paused','failed'].includes(currentTicket.status);
  $('run-one').disabled = running || !runnable; $('run-all').disabled = running || !runnable;
  $('apply-level').disabled = running || !runnable; $('pause').disabled = !ticketId || !(executing || currentTicket?.status === 'running');
  $('submit-trigger').disabled=running; $('refresh-ticket').disabled=!ticketId;
}
async function loadSettings() {
  const data=await api('/api/super/settings'); identities=data.identities;
  $('mode').value=data.policy.mode; $('owner-allowed').checked=data.policy.owner_allowed;
  $('visitor-allowed').checked=data.policy.visitor_allowed; $('bot-allowed').checked=data.policy.bot_allowed;
  $('rule-enabled').checked=data.policy.rule_enabled; $('policy-status').textContent=`当前版本 ${data.policy.version}`;
  policyDirty=false; showIdentity();
}
async function applyPolicy() {
  const body={mode:$('mode').value,owner_allowed:$('owner-allowed').checked,visitor_allowed:$('visitor-allowed').checked,
              bot_allowed:$('bot-allowed').checked,rule_enabled:$('rule-enabled').checked};
  const result=await post('/api/super/policy',body); policyDirty=false;
  $('policy-status').textContent=`已应用 ${result.mode} · ${result.version}`;
  addEvent('接单策略已更新',`模式 ${result.mode}；版本 ${result.version}`);
}
function showDecision(data) {
  const d=data.decision; let assessment=null;
  try { assessment=d.assessment_json ? JSON.parse(d.assessment_json) : null; } catch { assessment=null; }
  let plan=null; try { plan=d.plan_json ? JSON.parse(d.plan_json) : null; } catch { plan=null; }
  const names={ACCEPT:'接单',WOULD_ACCEPT:'观察：会接单，但不执行',IGNORE:'忽略',UNAVAILABLE:'研判失败，可重新提交'};
  const box=$('decision'); box.hidden=false;
  box.textContent=`事件 ${data.trigger_id}\n决定：${names[d.verdict] || d.verdict}\n原因：${d.reason || '—'}\n接单模式：${d.mode || '—'}\n${assessment ? `外层研判：${assessment.reason || '未返回理由'}\n` : '外层研判：本次无需调用\n'}${plan ? `外层规划：${plan.reason || '已生成清单'}\n${plan.questions.map((q,i)=>`${i+1}. ${q}`).join('\n')}\n` : ''}${d.ticket_id ? `工单：${d.ticket_id}` : '没有创建工单'}`;
  if (!d.ticket_id && currentTicket) box.textContent+='\n页面仍显示先前工单；工单按钮操作的是先前工单。';
  const blocked=['WOULD_ACCEPT','IGNORE'].includes(d.verdict);
  addEvent('接单判断',box.textContent,d.verdict==='UNAVAILABLE' ? 'error' : blocked ? 'stop' : '');
  setStatus(d.verdict==='UNAVAILABLE' ? '研判失败' : blocked ? '未执行' : '事件已处理',d.verdict==='UNAVAILABLE' ? 'err' : blocked ? 'busy' : 'ok');
  if (['UNAVAILABLE','WOULD_ACCEPT','IGNORE'].includes(d.verdict)) {
    const button=document.createElement('button'); button.type='button'; button.className='secondary'; button.textContent=d.verdict==='UNAVAILABLE' ? '重试该事件' : '策略变化后重新研判';
    button.onclick=async()=>{ if(running)return; running=true; setButtons(); try {button.disabled=true; setStatus('正在重新处理','busy'); if(policyDirty) await applyPolicy(); const result=await post(`/api/super/triggers/${encodeURIComponent(data.trigger_id)}/process`,{level:Number($('level').value)}); showDecision(result); if(result.decision.ticket_id) await refreshTicket();} catch(err){showError(err);} finally {button.disabled=false;running=false;setButtons();} };
    box.append(document.createElement('br'),button);
  }
  if (d.ticket_id) { ticketId=d.ticket_id; localStorage.setItem('super_ticket_id',ticketId); $('requeue').hidden=true; }
}
function renderTicket(data) {
  currentTicket=data; ticketId=data.id; localStorage.setItem('super_ticket_id',ticketId);
  $('final-box').hidden=false;
  const final=data.final_answer; finalBuffer=final?.answer || '';
  $('final-status').textContent=final ? ({pending:'等待汇总',running:'正在汇总',completed:'汇总完成',failed:`汇总失败：${final.error || '未知错误'}；可勾选重试后继续`}[final.status] || final.status) : (data.status==='completed' ? '这是旧工单，未生成最终汇总；新工单会自动汇总。' : '所有子问题完成后自动生成。');
  renderRich($('final-content'),finalBuffer);
  const p=data.retrieval_policy; $('ticket-summary').textContent=`工单 ${data.id.slice(0,12)} · ${data.status}${p ? ` · 强度 ${p.retrieval_level} / 版本 ${p.version}` : ''}`;
  const container=$('ticket-questions'); container.replaceChildren();
  for (const q of data.questions) {
    const card=document.createElement('div'); card.className='question-card'; card.dataset.position=String(q.position);
    const title=document.createElement('h4'); title.textContent=`${q.position}. ${q.question} · ${q.status} · 第 ${q.attempt} 次`;
    card.append(title);
    if (q.answer) { const body=document.createElement('div'); body.className='rich'; renderRich(body,q.answer); card.append(body); }
    if (q.error) { const error=document.createElement('p'); error.textContent=`失败：${q.error}`; card.append(error); }
    container.append(card);
  }
  const denied=[...data.events].reverse().find(x=>x.event.type==='resume_denied');
  if (denied && ['paused','failed','pending'].includes(data.status)) showRequeue(denied.event.requeued_trigger_id);
  else $('requeue').hidden=true;
  setButtons();
}
function showRequeue(triggerId) {
  const box=$('requeue'); box.hidden=false; box.replaceChildren();
  const message=document.createElement('p'); message.textContent=`恢复未获准，剩余问题已重新排队：${triggerId}`;
  const btn=document.createElement('button'); btn.type='button'; btn.textContent='重新研判排队事件';
  btn.onclick=async()=>{
    if(running)return; running=true; setButtons();
    try {btn.disabled=true; setStatus('外层研判中','busy');
      if(policyDirty) await applyPolicy();
      const d=await post(`/api/super/triggers/${encodeURIComponent(triggerId)}/process`,{level:Number($('level').value)});
      showDecision(d); if(d.decision.ticket_id) await refreshTicket();
    } catch(err) {showError(err);} finally {btn.disabled=false;running=false;setButtons();}
  };
  box.append(message,btn);
}
function renderHistory(data) {
  $('events').replaceChildren();
  for (const item of data.events) {
    const e=item.event, prefix=item.position ? `第 ${item.position} 题 · ` : '';
    if (e.type==='tool') {
      const box=addEvent(`${prefix}${e.name} · ${e.success ? '完成':'失败'}`,e.arguments || '',e.success ? 'tool' : 'error');
      const details=document.createElement('details'), summary=document.createElement('summary'), pre=document.createElement('pre');
      summary.textContent='查看工具返回'; pre.textContent=String(e.result || ''); details.append(summary,pre); box.box.append(details);
    } else if (e.type==='assistant') addEvent(`${prefix}模型输出`,e.content || ((e.tool_calls || []).length ? '模型选择了工具。' : ''),'answer');
    else if (e.type==='question_policy') addEvent(`${prefix}检索策略`,`强度 ${e.retrieval_level} · 版本 ${e.version}`);
    else if (e.type==='policy_choice_reply_excerpt') addEvent(`${prefix}模型对策略变化的说明`,e.content);
    else if (e.type==='notice') addEvent(`${prefix}提示`,e.content || '',e.guard && !['citation','evidence_metadata'].includes(e.guard) ? 'stop' : '');
    else if (['ticket_created','ticket_started','ticket_resumed','ticket_paused','ticket_completed','ticket_failed','resume_denied','admission_policy_changed','retrieval_policy_changed','final_started','final_completed','final_failed','final_notice'].includes(e.type)) addEvent('工单状态',JSON.stringify(e),['ticket_failed','final_failed'].includes(e.type) ? 'error' : ['ticket_paused','resume_denied'].includes(e.type) ? 'stop' : '');
  }
  if (!$('events').children.length) addEvent('动作','暂无记录');
}
async function refreshTicket() { if (!ticketId) return; const data=await api(`/api/super/tickets/${encodeURIComponent(ticketId)}`); renderTicket(data); renderHistory(data); }
function streamEvent(data) {
  if (data.type==='final_start') {
    finalBuffer=''; $('final-box').hidden=false; $('final-content').textContent=''; $('final-status').textContent='正在汇总'; addEvent('最终汇总','正在综合原始目标和子问题回答');
  } else if (data.type==='final_delta') {
    finalBuffer+=data.content; $('final-content').textContent=finalBuffer;
  } else if (data.type==='final_notice') {
    addEvent('最终汇总提示',data.content);
  } else if (data.type==='final_done') {
    $('final-status').textContent='汇总完成'; renderRich($('final-content'),data.answer); addEvent('最终汇总','回答已保存','answer');
  } else if (data.type==='question_start') {
    addEvent(`第 ${data.position} 题开始`,`${data.question}\n检索强度：${data.retrieval_policy?.retrieval_level ?? '默认'}`);
    const card=$('ticket-questions').querySelector(`[data-position="${data.position}"]`);
    if (card) card.querySelector('h4').textContent=`${data.position}. ${data.question} · running · 第 ${data.attempt} 次`;
  } else if (data.type==='question_done') {
    addEvent(`第 ${data.position} 题完成`,'回答已保存');
    const card=$('ticket-questions').querySelector(`[data-position="${data.position}"]`);
    if (card) { const body=document.createElement('div'); body.className='rich'; renderRich(body,data.answer); card.append(body); }
  }
  else if (data.type==='agent_event') {
    const e=data.event, title=`第 ${data.position} 题`;
    if (e.type==='model_start') addEvent(`${title} · 模型`,'正在生成','answer');
    else if (e.type==='tools_pending') for (const c of e.calls || []) pending.set(c.id, addEvent(`${title} · ${c.function?.name || '工具'}准备执行`,c.function?.arguments || '','tool'));
    else if (e.type==='tool') {
      const box=pending.get(e.tool_call_id) || addEvent(`${title} · ${e.name}`,'','tool');
      box.box.className=`event ${e.success ? 'tool' : 'error'}`;
      box.box.querySelector('strong').textContent=`${title} · ${e.name} · ${e.success ? '完成':'失败'}`; box.body.textContent=e.arguments || '';
      const d=document.createElement('details'), s=document.createElement('summary'), pre=document.createElement('pre'); s.textContent='查看工具返回'; pre.textContent=String(e.result || ''); d.append(s,pre); box.box.append(d);
    } else if (e.type==='notice') addEvent(`${title} · 提示`,e.content,e.guard && !['citation','evidence_metadata'].includes(e.guard) ? 'stop' : '');
    else if (e.type==='assistant' && e.content) addEvent(`${title} · 模型输出`,e.content,'answer');
  }
}
async function run(maxQuestions) {
  if (!ticketId || running) return;
  running=true; executing=true; setButtons(); setStatus('工单执行中','busy'); pending.clear();
  try {
    const response=await fetch(`/api/super/tickets/${encodeURIComponent(ticketId)}/run`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({max_questions:maxQuestions,retry_failed:$('retry').checked})});
    if (!response.ok) { const data=await response.json(); throw new Error(data.detail || '执行失败'); }
    const reader=response.body.getReader(), decoder=new TextDecoder(); let buffer='', finished=false, denied=false;
    while (true) {
      const {value,done}=await reader.read(); buffer+=decoder.decode(value || new Uint8Array(),{stream:!done}); let end;
      while ((end=buffer.indexOf('\n\n'))!==-1) {
        const frame=buffer.slice(0,end); buffer=buffer.slice(end+2);
        for (const line of frame.split('\n')) if (line.startsWith('data: ')) {
          const e=JSON.parse(line.slice(6));
          if (e.type==='error') throw new Error(e.message);
          if (e.type==='done') {
            finished=true;
            if (e.result.status==='resume_denied') {
              denied=true;
              showRequeue(e.result.requeued_trigger_id);
            }
          } else streamEvent(e);
        }
      }
      if (done) break;
    }
    if (!finished) throw new Error('事件流中断，后台工单可能仍在运行，请刷新查看。');
    await refreshTicket(); if (denied) setStatus('恢复未获准','busy'); else ticketStatus(currentTicket);
  } catch(err) { showError(err); try { await refreshTicket(); } catch {} }
  finally { running=false; executing=false; setButtons(); }
}

$('role').onchange=showIdentity; $('level').oninput=updateLevel;
for (const id of ['mode','owner-allowed','visitor-allowed','bot-allowed','rule-enabled']) $(id).onchange=()=>{ policyDirty=true; $('policy-status').textContent='修改尚未应用'; };
$('save-policy').onclick=()=>applyPolicy().catch(showError);
$('plan-mode').onchange=()=>{ $('manual-questions').hidden=$('plan-mode').value!=='manual'; };
// 手工核对过语料中存在相关段落；不保证模型一定检索命中或回答正确。
const examples = [
  {goal:'根据资料分别解释 Native App 和 Web App，再比较它们的运行方式与特点，注明来源和可能过时的地方。', questions:['Native App 是什么？请注明本地资料来源。','Web App 是什么？请注明本地资料来源。','结合前面回答，比较 Native App 和 Web App 的运行方式及特点，指出资料局限。']},
  {goal:'根据资料解释 Native App 是什么，再整理开发一款 App 时需求分析可以包含哪些内容，注明来源。', questions:['Native App 是什么？请注明本地资料来源。','资料提到编写 App 需求分析应考虑哪些内容？','结合前面两题，整理 Native App 项目需求分析的要点，区分资料陈述和推断。']},
  {goal:'根据资料分别说明美国公立大学和私立大学的经费来源，再比较资料提及的差异和局限，注明来源。', questions:['资料怎样描述美国公立大学的经费来源？','资料怎样描述美国私立大学的经费来源？','结合前面回答，比较两类学校的经费来源及资料提到的其他差异，指出不能一概而论之处。']},
  {goal:'根据资料分别说明服装丝印和烫印，再比较制版、批量和图案复杂度上的差异，注明来源。', questions:['资料怎样描述服装丝印的制版和适用批量？','资料怎样描述服装烫印的制版和图案特点？','结合前面回答，比较两种印花方式的制版、批量和图案复杂度，注明资料局限。']},
  {goal:'根据已有历史资料，整理如何创建微信群和设置群消息免打扰，并注明来源及版本可能变化。', questions:['已有资料怎样描述创建微信群？','已有资料怎样描述设置微信群消息免打扰？','结合前面回答整理操作思路，并提醒界面可能因版本变化。']},
  {goal:'根据已有资料，说明没有电脑能否设置无线路由器，以及资料提到哪些改善 Wi-Fi 信号的方法，注明条件和来源。', questions:['没有电脑能否设置无线路由器？请说明资料中的条件。','资料提到哪些改善 Wi-Fi 信号的方法？','结合前面回答整理一个排查思路，指出不同路由器及资料时效的限制。']},
];
let lastExample = -1;
$('example').onclick=()=>{
  let index=Math.floor(Math.random()*examples.length);
  if (examples.length>1 && index===lastExample) index=(index+1+Math.floor(Math.random()*(examples.length-1)))%examples.length;
  lastExample=index; const example=examples[index];
  $('trigger-text').value=example.goal; $('questions').value=example.questions.join('\n');
  $('example-hint').textContent=`已填入示例 ${index+1}/${examples.length}。相关段落存在于本地语料，但不保证检索命中或内容最新。`;
};
$('submit-trigger').onclick=async()=>{
  const goal=$('trigger-text').value.trim(), auto=$('plan-mode').value==='auto';
  if (!goal) return showError(new Error('请输入原始任务目标。'));
  const questions=auto ? [goal] : $('questions').value.split('\n').map(x=>x.trim()).filter(Boolean);
  if (!questions.length || questions.length>8) return showError(new Error('请输入 1 到 8 个问题，每行一个。'));
  running=true; setButtons(); setStatus('正在判断事件','busy');
  try {
    if (policyDirty) await applyPolicy();
    const result=await post('/api/super/triggers',{role:$('role').value,kind:$('kind').value,text:goal,questions,retrieval_level:Number($('level').value),plan:auto});
    showDecision(result); if (result.decision.ticket_id) await refreshTicket();
  } catch(err){showError(err);} finally {running=false;setButtons();}
};
$('run-one').onclick=()=>run(1); $('run-all').onclick=()=>run(null);
$('refresh-ticket').onclick=()=>refreshTicket().then(()=>ticketStatus(currentTicket)).catch(showError);
$('pause').onclick=()=>post(`/api/super/tickets/${encodeURIComponent(ticketId)}/pause`,{}).then(x=>addEvent('暂停请求',x.message,'stop')).catch(showError);
$('apply-level').onclick=()=>post(`/api/super/tickets/${encodeURIComponent(ticketId)}/retrieval`,{level:Number($('level').value)}).then(x=>{addEvent('检索策略已更新',`强度 ${x.level} · 版本 ${x.version}`);return refreshTicket();}).catch(showError);
(async()=>{ try {updateLevel(); await loadSettings(); if(ticketId) {try {await refreshTicket();} catch {localStorage.removeItem('super_ticket_id');ticketId=null;}} setButtons(); if(currentTicket) ticketStatus(currentTicket); else setStatus('准备就绪','ok');} catch(err){showError(err);} })();
