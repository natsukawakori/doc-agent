"""真实服务商用量对照：相同合成历史，完整输入与摘要输入分别回答。"""
import json
from pathlib import Path
from src.llm import chat
from src.memory import compress


def usage(response):
    data = getattr(response, 'usage', None)
    return {'input': getattr(data, 'prompt_tokens', None), 'output': getattr(data, 'completion_tokens', None)}


def main():
    history = []
    for i in range(1, 16):
        fact = '这一轮的项目代号是蓝色海星。' if i == 3 else f'这是第{i}轮的普通讨论。'
        history.extend([{'role': 'user', 'content': fact + '以下是测试填充内容。' * 18},
                        {'role': 'assistant', 'content': f'已记录第{i}轮。' + '保留上下文用于测试。' * 15}])
    question = {'role': 'user', 'content': '第3轮的项目代号是什么？只按已有对话回答。'}
    events = []
    compressed = compress(history, threshold=100, keep=4, observer=events.append)
    original_answer = chat(history + [question])
    compressed_answer = chat(compressed + [question])
    original, compact = usage(original_answer), usage(compressed_answer)
    result = {'turns': 15, 'compression': events[0], 'full_usage': original, 'compressed_usage': compact,
              'full_answer': original_answer.choices[0].message.content,
              'compressed_answer': compressed_answer.choices[0].message.content,
              'input_token_reduction': (1 - compact['input'] / original['input']) if original['input'] and compact['input'] is not None else None}
    output = Path('data/reports/memory_token_compare_20261106.json')
    with output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
