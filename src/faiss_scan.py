"""用有界大小的 FAISS 精确索引分片扫描本地向量。"""
import os
import numpy as np
import faiss
from eval.full_guard import available_memory


def scan(query_vectors, vector_path, vector_dtype, width, count, top_k):
    faiss.omp_set_num_threads(min(4, os.cpu_count() or 1))
    scores = [np.empty(0, dtype=np.float32) for _ in query_vectors]
    positions = [np.empty(0, dtype=np.int64) for _ in query_vectors]
    buffer = bytearray(8192 * 512 * width)
    offset = 0
    with vector_path.open("rb") as f:
        while size := f.readinto(buffer):
            if size % (512 * width):
                raise ValueError("向量缓存包含不完整的向量")
            array = np.frombuffer(buffer, dtype=vector_dtype, count=size // width).reshape(-1, 512)
            if width == 2:
                array = array.astype("float32")
            index = faiss.IndexFlatIP(512)
            index.add(array)
            values, indexes = index.search(query_vectors, min(top_k, len(array)))
            for i in range(len(query_vectors)):
                merged = np.concatenate((scores[i], values[i]))
                merged_positions = np.concatenate((positions[i], indexes[i] + offset))
                order = np.lexsort((merged_positions, -merged))[:top_k]
                scores[i], positions[i] = merged[order], merged_positions[order]
            offset += len(array)
            if offset % (8192 * 128) == 0 and available_memory() < 1024**3:
                raise MemoryError("系统可用内存不足 1 GiB，停止 FAISS 检索以避免继续加压")
    if offset != count:
        raise ValueError("向量缓存读取数量异常")
    return [row.tolist() for row in positions], [row.tolist() for row in scores]
