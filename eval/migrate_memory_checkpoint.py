"""仅迁移已验证的旧检查点签名，保留其排名与向量缓存。"""
import copy
import hashlib
import json
import sys
from pathlib import Path

OLD_ENGINE = "a74980d6d14b80c3ee8306944f9790f1d107c1d5a59efb884bb76792e464e391"
OLD_GUARD = "ee127f633446af2a12718a39cf9f242f9c3cf73eddd103b16d8fdd7a8d8f0512"
ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


def main():
    if len(sys.argv) != 3:
        raise SystemExit("用法: python -m eval.migrate_memory_checkpoint 原始检查点 新检查点")
    old, output = map(Path, sys.argv[1:])
    if output.exists() or old.resolve() == output.resolve():
        raise FileExistsError("目标已存在或与原检查点相同，拒绝覆盖")
    checkpoint = json.loads(old.read_text(encoding="utf-8"))
    sig = checkpoint["signature"]
    if sig["engine_sha256"] != OLD_ENGINE or sig["guard_code_sha256"] != OLD_GUARD:
        raise ValueError("旧版本签名不匹配，拒绝迁移")
    for key, name in [("ranker_sha256", "stream_rank.py"), ("cache_code_sha256", "vector_cache.py")]:
        if sig[key] != digest(ROOT / "eval" / name):
            raise ValueError(f"{name} 与检查点不一致")
    queries = ROOT / "data" / "dureader" / "full_queries.json"
    if sig["queries_sha256"] != digest(queries):
        raise ValueError("问题集与检查点不一致")
    count = checkpoint["processed"]
    if not isinstance(count, int) or count <= 0 or count % 4096 or len(checkpoint["rankings"]) != 100:
        raise ValueError("检查点进度或排名无效")
    cache = Path(sig["cache_dir"]).resolve()
    expected = (ROOT / "data" / "dureader" / "bge_full_cache").resolve()
    if cache != expected:
        raise ValueError("缓存目录不在预期位置")
    vectors, ids = cache / "vectors.f32", cache / "ids.bin"
    if vectors.stat().st_size != count * 512 * 4 or ids.stat().st_size != count * 32:
        raise ValueError("缓存长度与检查点不一致")
    updated = copy.deepcopy(checkpoint)
    updated["signature"].update({
        "engine_sha256": digest(ROOT / "eval" / "full_stream.py"),
        "guard_code_sha256": digest(ROOT / "eval" / "full_guard.py"),
        "memory_code_sha256": digest(ROOT / "eval" / "process_memory.py"),
    })
    updated["migration"] = {"reason": "只调整进程内存监测、等待和导入；不改变向量计算或排名",
                            "original_checkpoint_sha256": digest(old),
                            "vectors_sha256_at_migration": digest(vectors),
                            "ids_sha256_at_migration": digest(ids)}
    assert updated["rankings"] == checkpoint["rankings"]
    assert updated["found_gold_ids"] == checkpoint["found_gold_ids"]
    assert updated["processed"] == count
    with output.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(updated, f, ensure_ascii=False, separators=(",", ":"))
    print(f"已迁移 {count} 段的检查点；原始检查点和缓存均未改写。")
    print(f"新检查点: {output}")


if __name__ == "__main__":
    main()
