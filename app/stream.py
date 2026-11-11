"""将 Agent 的可见动作逐项放入事件队列并持久化。"""
import json
import queue
import threading
from pathlib import Path

from src.agent import run
from src.memory import compress
from src.trace import save_memory
from src.execution_control import ExecutionStopped
from app.state import busy, sessions

PROJECT = Path(__file__).resolve().parent.parent


def launch(question, session_id, control=None):
    events = queue.Queue()
    history = list(sessions[session_id])
    folder = PROJECT / "data" / "reports" / "web_sessions"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (session_id + ".jsonl")

    def save(item):
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            f.flush()

    def emit(item):
        save(item)
        events.put(item)

    def worker():
        nonlocal history
        trace_id = None
        def observe(item):
            nonlocal trace_id
            if item['type'] == 'trace_saved':
                trace_id = item['run_id']
                return
            if item['type'] == 'memory_compressed' and trace_id is not None:
                try:
                    save_memory(trace_id, item)
                except Exception:
                    emit({'type': 'notice', 'content': '摘要用量未能写入运行轨迹。'})
            emit(item)
        try:
            emit({"type": "user", "content": question})
            answer = run(question, history=history, observer=observe,
                         on_delta=lambda text: events.put({"type": "delta", "content": text}),
                         execution_control=control)
            if control: control.check()
            if answer:
                history.extend([{"role": "user", "content": question},
                                {"role": "assistant", "content": answer}])
                try:
                    history = compress(history, observer=observe)
                except Exception:
                    emit({"type": "notice", "content": "历史摘要暂时不可用，已保留原有历史。"})
                if control: control.check()
                sessions[session_id] = history
            emit({"type": "done", "answer": answer or "模型未返回最终回答。"})
        except ExecutionStopped as exc:
            emit({'type':'error','code':exc.code,'message':str(exc)})
        except Exception as exc:
            item = {"type": "error", "message": f"{type(exc).__name__}: {exc}"}
            try:
                save(item)
            finally:
                events.put(item)
        finally:
            busy.release()

    threading.Thread(target=worker, name="doc-agent-web", daemon=True).start()
    return events
