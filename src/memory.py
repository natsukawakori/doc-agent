"""对较长的对话做摘要，保留最近的完整问答。"""
import time
from src.llm import chat


def compress(messages, threshold=12000, keep=4, observer=None):
    if len(messages) <= keep or sum(len(str(m.get("content") or "")) for m in messages) <= threshold:
        return messages
    older, recent = messages[:-keep], messages[-keep:]
    prompt = [
        {"role": "system", "content": "请将对话压缩成简洁中文摘要，保留用户需求、事实、约束和未解决的问题，不要编造。"},
        {"role": "user", "content": "\n".join(f'{m["role"]}: {m.get("content", "")}' for m in older)},
    ]
    started = time.perf_counter()
    response = chat(prompt)
    seconds = time.perf_counter() - started
    summary = response.choices[0].message.content
    if not summary or not summary.strip():
        raise ValueError("摘要为空，保留原对话")
    compressed = [{"role": "system", "content": "之前的对话摘要：" + summary.strip()}] + recent
    if observer:
        usage = getattr(response, 'usage', None)
        observer({'type': 'memory_compressed',
                  'seconds': seconds,
                  'before_chars': sum(len(str(m.get('content') or '')) for m in messages),
                  'after_chars': sum(len(str(m.get('content') or '')) for m in compressed),
                  'summary_input_tokens': getattr(usage, 'prompt_tokens', None),
                  'summary_output_tokens': getattr(usage, 'completion_tokens', None)})
    return compressed
