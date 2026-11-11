"""DuReader Agent 小样本真实模型测试，逐事件写入完整可阅读记录。"""
import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from src.agent import run

PROJECT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="+", default=["14", "1703"], help="固定问题 ID")
    parser.add_argument("--max-steps", type=int, default=2)
    args = parser.parse_args()
    queries = json.loads((PROJECT / "data/dureader/full_queries.json").read_text(encoding="utf-8"))["queries"]
    by_id = {row["id"]: row for row in queries}
    if len(set(args.ids)) != len(args.ids) or any(q not in by_id for q in args.ids):
        raise ValueError("问题 ID 重复或不在固定问题集")
    folder = PROJECT / "data" / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("dureader_agent_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".md")
    print(f"完整测试记录：{path}", flush=True)
    with path.open("x", encoding="utf-8") as output:
        def write(text):
            output.write(text)
            output.flush()
            os.fsync(output.fileno())

        def observe(event):
            write("\n### " + ("Agent 消息" if event["type"] == "assistant" else "工具返回") + "\n\n")
            write("```json\n" + json.dumps(event, ensure_ascii=False, indent=2) + "\n```\n")

        write("# DuReader Agent 真实模型测试记录\n\n")
        write("按先后顺序记录用户输入、模型可见消息、工具调用参数和完整返回；"
              "模型内部推理不属于可见输出。网页内容未经核验，勿将记录视为事实依据。\n\n")
        write(f"模型：{os.getenv('LLM_MODEL_ID', '见本机配置')}；每题工具上限：{args.max_steps}。\n")
        for qid in args.ids:
            question = by_id[qid]["text"]
            write(f"\n## 问题 {qid}\n\n### 用户\n\n{question}\n")
            print(f"\n问题 {qid}：{question}", flush=True)
            started = time.perf_counter()
            try:
                answer = run(question, max_steps=args.max_steps, observer=observe)
                write(f"\n### 测试状态\n\n完成；耗时 {time.perf_counter()-started:.2f} 秒；"
                      f"最终回答{'非空' if answer else '为空'}。\n")
            except Exception as exc:
                write(f"\n### 测试状态\n\n失败：{type(exc).__name__}: {exc}\n")
                print(f"问题 {qid} 失败：{type(exc).__name__}: {exc}", flush=True)
                break
    print(f"记录已保存：{path}", flush=True)


if __name__ == "__main__":
    main()
