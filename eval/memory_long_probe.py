"""真实模型的受控 15 轮摘要验证；只测合成事实，不使用留出集。"""
import json
from pathlib import Path
from src.llm import chat
from src.memory import compress

messages = []
for i in range(1, 16):
    fact = '这一轮的项目代号是蓝色海星。' if i == 3 else f'这是第{i}轮的普通讨论。'
    messages.extend([{'role': 'user', 'content': fact + '以下是测试填充内容。' * 18},
                     {'role': 'assistant', 'content': f'已记录第{i}轮。' + '保留上下文用于测试。' * 15}])
events = []
compressed = compress(messages, threshold=100, keep=4, observer=events.append)
response = chat(compressed + [{'role': 'user', 'content': '第3轮的项目代号是什么？只按已有对话回答。'}])
answer = response.choices[0].message.content or ''
usage = getattr(response, 'usage', None)
result = {'turns': 15, 'memory_event': events[0], 'answer': answer,
          'answer_mentions_code': '蓝色海星' in answer,
          'answer_prompt_tokens': getattr(usage, 'prompt_tokens', None),
          'answer_completion_tokens': getattr(usage, 'completion_tokens', None)}
folder = Path('data/reports/memory_long_probe_20261106')
folder.mkdir(parents=True, exist_ok=False)
(folder/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
