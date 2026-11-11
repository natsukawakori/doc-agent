"""追加保存可复用的 float32 文档向量和固定长度段落 ID。"""
import os
from pathlib import Path


class VectorCache:
    def __init__(self, folder, dimension, processed, resume=False):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.dimension = dimension
        self.vectors_path = self.folder / "vectors.f32"
        self.ids_path = self.folder / "ids.bin"
        exists = self.vectors_path.exists(), self.ids_path.exists()
        if exists[0] != exists[1] or resume != all(exists) or (processed and not resume):
            raise ValueError("向量缓存与检查点不匹配；保留已有文件，拒绝覆盖")
        self.vectors = self.vectors_path.open("r+b" if exists[0] else "x+b")
        self.ids = self.ids_path.open("r+b" if exists[1] else "x+b")
        vector_offset = processed * dimension * 4
        id_offset = processed * 32
        if self.vectors_path.stat().st_size < vector_offset or self.ids_path.stat().st_size < id_offset:
            raise ValueError("向量缓存比检查点短，拒绝恢复")
        self.vectors.seek(vector_offset)
        self.ids.seek(id_offset)

    def append(self, ids, vectors):
        if vectors.ndim != 2 or vectors.shape != (len(ids), self.dimension):
            raise ValueError("缓存向量维度不匹配")
        if any(len(docid) != 32 or any(c not in "0123456789abcdef" for c in docid) for docid in ids):
            raise ValueError("遇到非 32 位小写十六进制段落 ID")
        self.vectors.write(vectors.detach().to("cpu").contiguous().numpy().astype("<f4", copy=False).tobytes())
        self.ids.write("".join(ids).encode("ascii"))

    def sync(self):
        for file in (self.vectors, self.ids):
            file.flush()
            os.fsync(file.fileno())

    def finish(self, processed):
        self.vectors.truncate(processed * self.dimension * 4)
        self.ids.truncate(processed * 32)
        self.sync()
        self.vectors.close()
        self.ids.close()
