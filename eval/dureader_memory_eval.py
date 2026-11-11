"""Two-turn Agent test: separate retrieval, synthesis, and history recall."""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.agent import run

first = ("请分别检索 Native App 和 Web App 两个概念，分别调用 search_docs 查找每个概念，"
         "然后根据检索结果比较它们的运行环境和安装方式，并标注来源。")
second = "不再调用检索工具。刚才我让你分别查询哪两个概念？你比较了哪两个方面？请根据我们之前的对话回答。"
folder = ROOT / "data/reports"
folder.mkdir(parents=True, exist_ok=True)
path = folder / ("dureader_memory_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".md")
print(f"多轮测试记录：{path}", flush=True)
with path.open("x", encoding="utf8") as output:
    def write(text):
        output.write(text)
        output.flush()
        os.fsync(output.fileno())

    def observe(event):
        write("\n### " + ("Agent 消息" if event["type"] == "assistant" else "工具返回") + "\n\n")
        write("```json\n" + json.dumps(event, ensure_ascii=False, indent=2) + "\n```\n")

    write("# DuReader Agent 多轮检索与记忆测试\n\n")
    write("记录用户输入、Agent 可见输出、工具调用及完整工具返回，不包含模型内部推理。\n")
    history = []
    for i, question in enumerate((first, second), 1):
        write(f"\n## 第 {i} 轮\n\n### 用户\n\n{question}\n")
        print(f"\n第 {i} 轮：{question}", flush=True)
        start = time.perf_counter()
        try:
            answer = run(question, max_steps=4, history=history, observer=observe)
            write(f"\n### 测试状态\n\n完成；耗时 {time.perf_counter()-start:.2f} 秒；"
                  f"最终回答{'非空' if answer else '为空'}。\n")
            if not answer:
                break
            history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer}])
        except Exception as exc:
            write(f"\n### 测试状态\n\n失败：{type(exc).__name__}: {exc}\n")
            raise
print(f"记录已保存：{path}", flush=True)
