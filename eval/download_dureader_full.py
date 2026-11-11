"""下载并校验公开 DuReader Retrieval 全量压缩语料，可续传。"""
import hashlib
import os
import sys
import time
import urllib.request
from pathlib import Path

REVISION = "519a29f2934a650967d7c6c99f4c53ed99e083d0"
URL = ("https://huggingface.co/datasets/zyznull/dureader-retrieval-corpus/resolve/"
       + REVISION + "/passage_collection.tsv.gz")
SIZE = 3551639620
SHA256 = "4c185a9d143488043d0ed64cc425d21ff5cf56edb5fc75f7939f867218ae6a69"


def verify(path):
    if path.stat().st_size != SIZE:
        raise ValueError(f"文件长度不符：{path.stat().st_size}，期望 {SIZE}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    if digest.hexdigest() != SHA256:
        raise ValueError("SHA256 不符：保留文件供检查，不将其标记为完成")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("用法: python -m eval.download_dureader_full 目标文件.gz")
    target = Path(sys.argv[1])
    partial = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        print("目标文件已存在，正在验证，不会覆盖。", flush=True)
        verify(target)
        print("已有文件校验成功。", flush=True)
        return
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > SIZE:
        raise ValueError("临时文件比预期大，保留文件供检查")
    for attempt in range(5):
        if offset == SIZE:
            break
        try:
            request = urllib.request.Request(URL, headers={"Range": f"bytes={offset}-"} if offset else {})
            with urllib.request.urlopen(request, timeout=120) as response:
                if offset and (response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")):
                    raise ValueError("服务器未确认续传范围，拒绝追加以防文件损坏")
                with partial.open("ab" if offset else "wb") as out:
                    last = offset
                    while block := response.read(4 * 1024 * 1024):
                        out.write(block)
                        offset += len(block)
                        if offset - last >= 256 * 1024 * 1024:
                            print(f"已下载 {offset / 1024**3:.2f}/{SIZE / 1024**3:.2f} GiB", flush=True)
                            last = offset
            if offset != SIZE:
                raise OSError(f"连接结束时只有 {offset}/{SIZE} 字节")
        except (OSError, TimeoutError) as exc:
            print(f"下载中断，将尝试续传：{type(exc).__name__}", flush=True)
            if attempt == 4:
                raise
            time.sleep(min(2 ** attempt, 10))
    print("下载完成，正在校验 SHA256……", flush=True)
    verify(partial)
    if target.exists():
        raise FileExistsError("目标文件在下载期间出现，拒绝覆盖")
    os.rename(partial, target)
    print(f"全量语料校验成功：{target}，{SIZE} bytes", flush=True)


if __name__ == "__main__":
    main()
