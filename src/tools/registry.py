"""工具及其 OpenAI 兼容参数描述。"""
from src.tools import calc, web_fetch, web_search, search_docs

TOOLS = {
    "search_docs": ("检索 DuReader 公开语料，返回重排后的段落及 ID。", "query", "要检索的问题", search_docs.run),
    "calc": ("计算简单的四则运算表达式。", "expression", "数学表达式，例如 2*(3+4)", calc.run),
    "web_fetch": ("读取公开 HTTP 或 HTTPS 网页的文本。", "url", "网页地址", web_fetch.run),
    "web_search": ("搜索公开网页，返回标题、网址和摘要；搜索内容不一定可靠。", "query", "要搜索的问题或关键词", web_search.run),
}

# 搜索需要扫描大规模本地语料；普通工具使用较短超时。
TOOL_LIMITS = {'search_docs': (300, 1), 'calc': (30, 1), 'web_fetch': (30, 1), 'web_search': (30, 0)}


def limits(name):
    return TOOL_LIMITS.get(name, (30, 0))


def schemas():
    result = []
    for name, (description, parameter, detail, _) in TOOLS.items():
        result.append({"type": "function", "function": {
            "name": name, "description": description,
            "parameters": {"type": "object", "properties": {
                parameter: {"type": "string", "description": detail}},
                "required": [parameter], "additionalProperties": False}}})
    return result


def execute(name, arguments):
    if name not in TOOLS:
        raise ValueError(f"未知工具：{name}")
    _, parameter, _, function = TOOLS[name]
    if set(arguments) != {parameter} or not isinstance(arguments[parameter], str):
        raise ValueError(f"工具 {name} 需要一个字符串参数 {parameter}")
    return function(arguments[parameter])

