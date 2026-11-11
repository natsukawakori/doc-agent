"""固定 20 题的 DuReader Agent 真实验收；失败后保留记录并支持续跑。"""
import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from src.agent import run
from src.trace import DB

PROJECT = Path(__file__).resolve().parent.parent


def append(path, item):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def transcript(path, item):
    with path.open("a", encoding="utf-8") as f:
        f.write(f'\n### 题目 {item["id"]} · {item["type"]}\n\n')
        f.write("```json\n" + json.dumps(item, ensure_ascii=False, indent=2) + "\n```\n")
        f.flush()
        os.fsync(f.fileno())


def scores(completed, expected=20):
    n = len(completed)
    calls = sum(row["steps"] for row in completed)
    latency = sorted(row['seconds'] for row in completed)
    known_tokens = [row['tokens'] for row in completed if row['tokens'] is not None]
    return {"completed": n, "expected": expected,
            "hit@1": sum(row["hit1"] for row in completed) / n,
            "hit@3": sum(row["hit3"] for row in completed) / n,
            "avg_steps": calls / n,
            "avg_latency_seconds": sum(row["seconds"] for row in completed) / n,
            "p95_latency_seconds": latency[math.ceil(.95 * n) - 1],
            "tool_failure_rate": sum(row["failures"] for row in completed) / calls if calls else None,
            "answers_nonempty": sum(bool(row["answer"]) for row in completed),
            "tokens_known": sum(row["tokens"] is not None for row in completed),
            "token_per_case": sum(known_tokens) / len(known_tokens) if known_tokens else None,
            "answer_correct_rate": None, "citation_support_rate": None, "no_answer_rate": None,
            "quality_note": "质量指标需人工逐题核验；留出集本身不构成无依据题集",
            "total_tokens_when_known": sum(row["tokens"] or 0 for row in completed)}


def print_table(completed):
    print("\nID | hit@1 | hit@3 | steps | failures | seconds | tokens", flush=True)
    for row in completed:
        print(f'{row["id"]} | {int(row["hit1"])} | {int(row["hit3"])} | {row["steps"]} | '
              f'{row["failures"]} | {row["seconds"]:.2f} | {row["tokens"]}', flush=True)


def load_cases(manifest, queries_raw, holdout):
    if holdout:
        if hashlib.sha256(queries_raw).hexdigest() != manifest['holdout_sha256']:
            raise ValueError('留出集与冻结清单不一致')
        rows = [json.loads(line) for line in queries_raw.decode('utf-8').splitlines() if line.strip()]
        queries = {str(row['id']): {'text': row['question'], 'positive_ids': row['gold_passage_ids']} for row in rows}
        ids, expected = [str(row['id']) for row in rows], 30
    else:
        if hashlib.sha256(queries_raw).hexdigest() != manifest['queries_sha256']:
            raise ValueError('问题文件与预先固定清单不一致')
        queries = {row['id']: row for row in json.loads(queries_raw)['queries']}
        ids, expected = manifest['query_ids'], 20
    if len(ids) != expected or len(set(ids)) != expected or any(q not in queries for q in ids):
        raise ValueError('题集数量或 ID 不符合清单')
    return queries, ids, expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="继续同一批任务；仅允许字母数字和下划线")
    parser.add_argument("--max-steps", type=int, default=2)
    parser.add_argument("--validate-only", action="store_true", help="只检查题集和哈希，不调用模型或检索")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--holdout", action="store_true", help="运行原冻结留出集（现已转为开发用途）")
    group.add_argument("--holdout-v2", action="store_true", help="运行新冻结的独立留出集")
    group.add_argument("--holdout-v3", action="store_true", help="运行排除前两版的第三版留出集")
    group.add_argument("--holdout-final", action="store_true", help="最终验收时运行预先冻结的新 30 题")
    args = parser.parse_args()
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    if not re.fullmatch(r"[A-Za-z0-9_]+", run_id) or not 1 <= args.max_steps <= 8:
        raise ValueError("run-id 或 max-steps 不合法")
    is_holdout = args.holdout or args.holdout_v2 or args.holdout_v3 or args.holdout_final
    manifest_path = PROJECT / ("eval/holdout/manifest.json" if args.holdout_final else "data/dureader/holdout_30_v3_manifest.json" if args.holdout_v3 else "data/dureader/holdout_30_v2_manifest.json" if args.holdout_v2 else
                               "eval/holdout_30_manifest.json" if args.holdout else "eval/acceptance20_manifest.json")
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    if is_holdout:
        queries_raw = (PROJECT / ("eval/holdout/holdout_30.jsonl" if args.holdout_final else "data/dureader/holdout_30_v3.jsonl" if args.holdout_v3 else "data/dureader/holdout_30_v2.jsonl" if args.holdout_v2 else "data/dureader/holdout_30.jsonl")).read_bytes()
    else:
        queries_raw = (PROJECT / "data/dureader/full_queries.json").read_bytes()
    queries, ids, expected = load_cases(manifest, queries_raw, is_holdout)
    if args.validate_only:
        print(json.dumps({'validated':len(ids),'expected':expected,'holdout':bool(is_holdout),
                          'sha256':hashlib.sha256(queries_raw).hexdigest()},ensure_ascii=False))
        return
    folder = PROJECT / "data/reports" / (("holdout_final_" if args.holdout_final else "holdout_v3_" if args.holdout_v3 else "holdout_v2_" if args.holdout_v2 else "holdout_" if args.holdout else "m3_acceptance_") + run_id)
    folder.mkdir(parents=True, exist_ok=True)
    config_path = folder / "config.json"
    tracked = ("src/agent.py", "src/agent_cli.py", "src/tool_dispatch.py", "src/model_response.py",
               "src/process_runner.py", "src/guard.py", "src/search_cache.py", "src/trace.py", "src/rag.py", "src/batch_dispatch.py",
               "src/batch_worker.py", "src/tool_worker.py", "src/faiss_scan.py", "src/torch_scan.py",
               "src/llm.py", "src/answer_guard.py", "src/execution_control.py", "src/tools/registry.py", "src/tools/search_docs.py", "src/tools/web_search.py", "requirements.txt", "eval/acceptance_m3.py",
               "data/dureader/bge_full_cache/manifest.json", "data/dureader/passage_lookup/manifest.json")
    if os.getenv("DOC_AGENT_VECTOR_DTYPE", "float32").strip().lower() == "float16":
        tracked += ("data/dureader/bge_full_cache/manifest_f16.json",)
    config = {"manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(), "max_steps": args.max_steps,
              "dataset": "holdout_final" if args.holdout_final else "holdout_30_v3" if args.holdout_v3 else "holdout_30_v2" if args.holdout_v2 else "holdout_30" if args.holdout else "acceptance20",
              "model": os.getenv("LLM_MODEL_ID", ""), "run_id": run_id,
              "backend": os.getenv("DOC_AGENT_VECTOR_BACKEND", "faiss"),
              "search_cache": os.getenv("DOC_AGENT_SEARCH_CACHE", "0"),
              "token_budget": os.getenv("DOC_AGENT_TOKEN_BUDGET", ""),
              "provider_sha256": hashlib.sha256(os.getenv("LLM_BASE_URL", "").encode()).hexdigest(),
              "vector_dtype": os.getenv("DOC_AGENT_VECTOR_DTYPE", "float32"),
              "files_sha256": {name: hashlib.sha256((PROJECT / name).read_bytes()).hexdigest() for name in tracked}}
    if config_path.exists():
        if json.loads(config_path.read_text(encoding="utf-8")) != config:
            raise ValueError("续跑配置与已有结果不一致")
    else:
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    output, events_path, transcript_path = folder / "results.jsonl", folder / "events.jsonl", folder / "transcript.md"
    completed = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()] if output.exists() else []
    done = {x["id"] for x in completed}
    print(f"记录目录：{folder}；已有 {len(done)}/{expected} 完成", flush=True)
    for qid in ids:
        if qid in done:
            continue
        case, events = queries[qid], []
        attempt = datetime.now().isoformat(timespec="microseconds")
        user = {"id": qid, "attempt": attempt, "type": "user", "content": case["text"]}
        append(events_path, user)
        transcript(transcript_path, user)
        def observe(event):
            events.append(event)
            item = {"id": qid, "attempt": attempt, **event}
            append(events_path, item)
            transcript(transcript_path, item)
        started = time.perf_counter()
        print(f"\n[{len(done)+1}/{expected}] {qid} {case['text']}", flush=True)
        try:
            answer = run(case["text"], max_steps=args.max_steps, observer=observe)
        except Exception as exc:
            item = {"id": qid, "attempt": attempt, "type": "error", "error": f"{type(exc).__name__}: {exc}"}
            append(events_path, item)
            transcript(transcript_path, item)
            print(f"停止：{type(exc).__name__}: {exc}；已完成结果可续跑。", flush=True)
            raise
        calls = [event for event in events if event["type"] == "tool"]
        first_search = next((event for event in calls if event["name"] == "search_docs" and event["success"]), None)
        retrieved = []
        if first_search:
            retrieved = [x["source"].removeprefix("DuReader:") for x in json.loads(first_search["result"])]
        gold = set(case["positive_ids"])
        trace_id=next((event['run_id'] for event in reversed(events) if event.get('type')=='trace_saved'),None)
        with sqlite3.connect(DB) as db:
            trace = db.execute("SELECT total_tokens FROM runs WHERE id=?", (trace_id,)).fetchone() if trace_id is not None else None
        row = {"id": qid, "attempt": attempt, "question": case["text"], "answer": answer, "hit1": bool(gold & set(retrieved[:1])),
               "hit3": bool(gold & set(retrieved[:3])), "steps": len(calls),
               "failures": sum(not e["success"] for e in calls), "seconds": time.perf_counter()-started,
               "tokens": trace[0] if trace else None}
        append(output, row)
        completed.append(row)
        done.add(qid)
        print(json.dumps({k: row[k] for k in ("id", "hit1", "hit3", "steps", "failures", "seconds", "tokens")}, ensure_ascii=False), flush=True)
    if len(completed) == expected:
        summary = scores(completed, expected)
        (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print_table(completed)
        print("\n完整汇总：" + json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
