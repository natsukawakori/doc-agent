"""批次向量与查询向量精确比较，并保留每个查询的全局前 K。"""
import heapq
import math
import torch


class StreamingTopK:
    def __init__(self, query_vectors, k=10, state=None):
        if query_vectors.ndim != 2 or k < 1:
            raise ValueError("查询矩阵或 K 不合法")
        self.queries = query_vectors
        self.k = k
        self.heaps = [[] for _ in range(len(query_vectors))]
        if state is not None:
            if len(state) != len(self.heaps):
                raise ValueError("检查点的查询数不匹配")
            for heap, rows in zip(self.heaps, state):
                if len(rows) > k:
                    raise ValueError("检查点的候选数超过 K")
                for score, ordinal, docid in rows:
                    if not math.isfinite(score) or not isinstance(docid, str):
                        raise ValueError("检查点含无效分数或段落 ID")
                    heap.append((float(score), int(ordinal), docid))
                heapq.heapify(heap)

    def update(self, vectors, ids, offset):
        if vectors.ndim != 2 or len(vectors) != len(ids) or vectors.shape[1] != self.queries.shape[1]:
            raise ValueError("段落向量与 ID 不匹配")
        if not ids:
            return
        values, indexes = torch.topk(self.queries @ vectors.T, min(self.k, len(ids)), dim=1)
        scores, indexes = values.cpu().tolist(), indexes.cpu().tolist()
        for heap, score_row, index_row in zip(self.heaps, scores, indexes):
            for score, local in zip(score_row, index_row):
                if not math.isfinite(score):
                    raise ValueError("向量得分非有限数")
                entry = (float(score), -(offset + local), str(ids[local]))
                if len(heap) < self.k:
                    heapq.heappush(heap, entry)
                elif entry > heap[0]:
                    heapq.heapreplace(heap, entry)

    def state(self):
        return [[list(item) for item in heap] for heap in self.heaps]

    def results(self):
        return [[{"id": docid, "score": score} for score, _, docid in sorted(heap, reverse=True)]
                for heap in self.heaps]
