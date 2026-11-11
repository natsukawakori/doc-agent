"""GPU 或 CPU 上分批精确扫描向量，作为 FAISS 的可选对照。"""
import numpy as np
import torch
from eval.full_guard import pace


def scan(q, vector_path, vector_dtype, width, count, top_k, device):
    scores = torch.full((len(q), top_k), float("-inf"), device=device)
    positions = torch.zeros((len(q), top_k), dtype=torch.int64, device=device)
    offset = 0
    buffer = bytearray(8192 * 512 * width)
    with vector_path.open("rb") as f:
        while size := f.readinto(buffer):
            if size % (512 * width):
                raise ValueError("向量缓存包含不完整的向量")
            arr = np.frombuffer(buffer, dtype=vector_dtype, count=size // width).reshape(-1, 512)
            batch = torch.from_numpy(arr).to(device).float()
            values, indexes = torch.topk(q @ batch.T, min(top_k, len(batch)), dim=1)
            candidates = torch.cat((scores, values), dim=1)
            candidates_pos = torch.cat((positions, indexes + offset), dim=1)
            scores, order = torch.topk(candidates, top_k, dim=1)
            positions = torch.gather(candidates_pos, 1, order)
            offset += len(batch)
            if device == "cuda" and offset % (8192 * 64) == 0:
                pace(offset, 0, temp_limit=90)
    if offset != count:
        raise ValueError("向量缓存读取数量异常")
    return positions.tolist(), scores.tolist()
