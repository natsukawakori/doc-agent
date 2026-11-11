"""将模型流分片合并为可用的文本与工具调用。"""
from src.console import safe_print as print


def read_response(messages, tools, usage=None, on_delta=None, *, chat):
    """实时显示文字，并拼接流中分片的工具调用。"""
    text_parts, reasoning_parts, calls = [], [], {}
    for chunk in chat(messages, stream=True, tools=tools):
        if usage is not None and getattr(chunk, "usage", None) and chunk.usage.total_tokens:
            usage["last"] = chunk.usage.total_tokens
            usage['input'] = getattr(chunk.usage, 'prompt_tokens', None)
            usage['output'] = getattr(chunk.usage, 'completion_tokens', None)
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            if on_delta:
                on_delta(delta.content)
            if not text_parts:
                print("[助手] ", end="", flush=True)
            text_parts.append(delta.content)
            print(delta.content, end="", flush=True)
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            reasoning_parts.append(reasoning)
        for part in delta.tool_calls or []:
            call = calls.setdefault(part.index, {"id": "", "type": "function",
                                    "function": {"name": "", "arguments": ""}})
            if part.id:
                call["id"] += part.id
            if part.function:
                call["function"]["name"] += part.function.name or ""
                call["function"]["arguments"] += part.function.arguments or ""
    if text_parts:
        print(flush=True)
    message = {"role": "assistant", "content": "".join(text_parts) or None}
    if calls:
        message["tool_calls"] = [calls[i] for i in sorted(calls)]
    if reasoning_parts:
        message["reasoning_content"] = "".join(reasoning_parts)
    return message


