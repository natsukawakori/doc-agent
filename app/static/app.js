const $ = id => document.getElementById(id);
let sessionId = null;
let currentMessage = null;
let activeController = null;
let stoppedByGuard = false;
const pending = new Map();

function setStatus(text, type) { $('status').textContent=text; $('status').className=`badge ${type}`; }

function clearEmpty(container) {
  const empty = container.querySelector('.empty');
  if (empty) empty.remove();
}

function item(container, label, text, className) {
  clearEmpty(container);
  const box = document.createElement('div');
  box.className = className;
  if (label) { const title = document.createElement('strong'); title.textContent = label; box.append(title); }
  const body = document.createElement('div');
  body.textContent = text || '';
  box.append(body); container.append(box);
  return { box, body };
}

async function recommendations() {
  const response = await fetch('/api/recommendations');
  if (!response.ok) throw new Error('推荐问题加载失败');
  const data = await response.json();
  $('suggestions').replaceChildren();
  for (const q of data.questions) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'chip'; button.textContent = q;
    button.onclick = () => { $('question').value = q; $('question').focus(); };
    $('suggestions').append(button);
  }
}

function displayEvent(event) {
  if (event.type === 'model_start') {
    currentMessage = item($('events'), '模型响应', '等待模型输出…', 'event answer');
  } else if (event.type === 'delta') {
    if (!currentMessage) currentMessage = item($('events'), '模型响应', '', 'event answer');
    if (currentMessage.body.textContent === '等待模型输出…') currentMessage.body.textContent = '';
    currentMessage.body.textContent += event.content;
  } else if (event.type === 'assistant') {
    if (currentMessage && event.content) renderRich(currentMessage.body, event.content);
    else if (currentMessage && currentMessage.body.textContent === '等待模型输出…')
      currentMessage.body.textContent = '模型选择了工具。';
  } else if (event.type === 'tools_pending') {
    for (const call of event.calls) {
      const name = call.function?.name || '工具';
      const box = item($('events'), `${name} · 准备执行`, call.function?.arguments || '', 'event tool');
      pending.set(call.id, box);
    }
  } else if (event.type === 'tool') {
    const box = pending.get(event.tool_call_id) || item($('events'), event.name, '', 'event tool');
    box.box.className = `event ${event.success ? 'tool' : 'error'}`;
    const mode = event.shared_batch ? ' · 共享批次' : event.reused ? ' · 复用结果' : '';
    const seconds=typeof event.seconds==='number' ? ` · ${event.seconds.toFixed(2)} 秒` : '';
    box.box.querySelector('strong').textContent = `${event.name} · ${event.success ? '完成' : '失败'}${mode}${seconds}`;
    box.body.textContent = event.arguments;
    const details = document.createElement('details');
    const summary = document.createElement('summary'); summary.textContent = '查看工具完整返回';
    const pre = document.createElement('pre');
    try { pre.textContent = JSON.stringify(JSON.parse(event.result), null, 2); } catch { pre.textContent = event.result; }
    details.append(summary, pre); box.box.append(details);
  } else if (event.type === 'notice') {
    const stopped=['token_budget','usage_unavailable','idle','cleanup_uncertain','repeated_errors','max_steps'].includes(event.guard)
      || /连续三次同类工具错误|工具进程清理状态不确定/.test(event.content || '');
    if (stopped) stoppedByGuard=true;
    item($('events'), '提示', event.content, stopped ? 'event stop' : 'event');
  } else if (event.type === 'done') {
    const answer = item($('messages'), '', '', 'message assistant');
    renderRich(answer.body, event.answer);
    setStatus(stoppedByGuard ? '已停止并返回结果' : '已完成',stoppedByGuard ? 'busy' : 'ok');
  } else if (event.type === 'error') {
    item($('events'), '执行失败', event.message, 'event error');
    setStatus('执行失败','err');
  }
}

async function send(question) {
  if (activeController) return;
  const controller=new AbortController(); activeController=controller;
  const started=Date.now();
  const timer=setInterval(()=>setStatus(`正在处理 · ${Math.floor((Date.now()-started)/1000)}s`,'busy'),1000);
  item($('messages'), '', question, 'message user');
  $('send').disabled = true; $('stop').disabled=false; setStatus('正在处理 · 0s','busy');
  currentMessage = null; stoppedByGuard=false; pending.clear();
  try {
    const response = await fetch('/chat', { method: 'POST', signal:controller.signal, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, question }) });
    if (!response.ok) { const data = await response.json(); throw new Error(data.detail || '请求失败'); }
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let buffer = '', finished = false;
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      let end;
      while ((end = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, end); buffer = buffer.slice(end + 2);
        for (const line of frame.split('\n')) if (line.startsWith('data: ')) {
          const parsed = JSON.parse(line.slice(6));
          displayEvent(parsed);
          if (parsed.type === 'done' || parsed.type === 'error') { finished = true; clearInterval(timer); }
        }
      }
      if (done) break;
    }
    if (!finished) throw new Error('事件流提前中断，后台任务可能仍在执行。');
  } catch (err) {
    if (controller.signal.aborted) {
      item($('events'), '已请求停止', '页面已停止接收；后台会在可控边界停止，正在执行的调用可能仍需等待。', 'event stop');
      setStatus('已停止接收','busy');
    } else { item($('events'), '请求失败', String(err.message || err), 'event error'); setStatus('连接失败','err'); }
  }
  finally { clearInterval(timer); activeController=null; $('stop').disabled=true; $('send').disabled = false; $('question').focus(); }
}

$('form').addEventListener('submit', event => {
  event.preventDefault(); const question = $('question').value.trim();
  if (question && sessionId) { $('question').value = ''; send(question); }
});
$('question').addEventListener('keydown', event => {
  if (!event.isComposing && event.key==='Enter' && (event.ctrlKey || event.metaKey) && !event.shiftKey) {
    event.preventDefault(); if (!$('send').disabled) $('form').requestSubmit();
  }
});
$('stop').onclick=()=>{ if(activeController) { $('stop').disabled=true; setStatus('正在请求停止','busy'); activeController.abort(); } };
$('refresh').onclick = () => recommendations().catch(err => { $('suggestions').textContent = err.message; });
(async () => {
  try {
    const response = await fetch('/api/session', { method: 'POST' });
    if (!response.ok) throw new Error('会话创建失败');
    sessionId = (await response.json()).session_id;
    await recommendations(); setStatus('准备就绪','ok');
  } catch (err) { setStatus('连接失败','err'); $('suggestions').textContent = err.message; }
})();
