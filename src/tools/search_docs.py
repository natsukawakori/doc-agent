"""检索 DuReader 并向 Agent 返回片段与段落 ID。"""
import json


def run(query):
    from src.rag import search
    return json.dumps(search(query), ensure_ascii=False)
