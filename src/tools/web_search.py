"""公开网页搜索：只返回少量标题、网址与摘要。"""
import json
from urllib.parse import urlparse


def run(query):
    query = query.strip()
    if not query or len(query) > 500:
        raise ValueError("搜索参数须为 1 至 500 个字符")
    # 延迟导入使其他工具在未安装搜索依赖时仍可正常使用。
    from ddgs import DDGS

    results = DDGS(timeout=8).text(query, max_results=5)
    items = []
    for result in results:
        url = str(result.get("href", ""))
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            continue
        items.append({"title": str(result.get("title", ""))[:300],
                      "url": url[:2000], "snippet": str(result.get("body", ""))[:1200]})
    return json.dumps({"query": query, "results": items,
                       "notice": "搜索摘要仅供参考，内容及时间可能不准确。"}, ensure_ascii=False)
