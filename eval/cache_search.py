"""重用已完成的本地文档向量缓存检索新问题，不再计算文档向量。"""
import argparse
import json
import os
from pathlib import Path
os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parent.parent / "data" / "huggingface"))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from eval.full_stream import MODEL, REVISION, PREFIX, sha256
from eval.stream_rank import StreamingTopK


def search_vectors(folder, queries, k, device="cpu", verify=False):
    folder = Path(folder)
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("向量缓存尚未完成，找不到 manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    count, dim = manifest["count"], manifest["dimension"]
    vectors_path, ids_path = folder / manifest["vectors_file"], folder / manifest["ids_file"]
    if vectors_path.stat().st_size != count * dim * 4 or ids_path.stat().st_size != count * 32:
        raise ValueError("缓存文件长度不匹配")
    if verify and (sha256(vectors_path) != manifest["vectors_sha256"] or sha256(ids_path) != manifest["ids_sha256"]):
        raise ValueError("缓存文件 SHA256 校验失败")
    if not 1 <= k <= min(100, count) or queries.ndim != 2 or queries.shape[1] != dim:
        raise ValueError("K 或查询向量维度不合法")
    vectors = np.memmap(vectors_path, mode="r", dtype="<f4", shape=(count, dim))
    ids = np.memmap(ids_path, mode="r", dtype="S32", shape=(count,))
    ranker = StreamingTopK(queries.to(device), k=k)
    for offset in range(0, count, 8192):
        end = min(offset + 8192, count)
        batch = torch.from_numpy(np.array(vectors[offset:end], copy=True)).to(device)
        ranker.update(batch, [x.decode('ascii') for x in ids[offset:end]], offset)
    return ranker.results()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/dureader/bge_full_cache"))
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--verify", action="store_true", help="先计算完整缓存文件 SHA256，可能耗时较长")
    args = parser.parse_args()
    manifest = json.loads((args.cache_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["model"] != MODEL or manifest["model_revision"] != REVISION or manifest["max_seq_length"] != 256:
        raise ValueError("缓存向量的模型与查询模型不一致")
    model = SentenceTransformer(MODEL, revision=REVISION, device=args.device)
    model.max_seq_length = 256
    with torch.inference_mode():
        query = model.encode([PREFIX + args.query], normalize_embeddings=True, convert_to_tensor=True)
        result = search_vectors(args.cache_dir, query, args.k, device=args.device, verify=args.verify)
    print(json.dumps({"results": result[0], "note": "仅输出段落 ID 与分数；可用 ID 查找原始语料。"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
