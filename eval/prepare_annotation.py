"""从既有 Agent 记录准备人工标注，不调用模型，也不改动原始记录。"""
import json
import sys
from pathlib import Path


def read(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def prepare(results, events):
    if len({str(row['id']) for row in results}) != len(results):
        raise ValueError('逐题结果 ID 重复')
    cases, sections = [], ['# 人工标注工作单', '', '题集及版本请参照评测目录 config.json；不要仅凭本工作单判断是否为独立留出集。请检查每条答案和引用，勿把模型或语料的陈述当成事实。', '',
        '答案标签：正确 / 部分正确 / 错误 / 无法判断。引用标签：支持 / 部分支持 / 不支持 / 无法判断；没有引用也应记下来。不能确认时填写无法判断。',
        '回答正确与段落支持是两个判断：段落支持只说明材料说过类似内容，不代表材料本身可靠。每题至少挑选一个有代表性的事实主张，写出所对照的段落 ID 和理由。', '']
    for row in results:
        qid = str(row['id'])
        matching = [e for e in events if str(e.get('id')) == qid]
        attempts = ([row['attempt']] if row.get('attempt') else
                    list(dict.fromkeys(e.get('attempt') for e in matching if e.get('type') == 'user')))
        if len(attempts) != 1:
            raise ValueError(f'题目 {qid} 有 {len(attempts)} 次尝试，需人工选择，避免错误关联')
        if not any(e.get('type') == 'user' and e.get('attempt') == attempts[0] for e in matching):
            raise ValueError(f'题目 {qid} 找不到结果对应的尝试')
        tools = [e for e in matching if e.get('attempt') == attempts[0] and e.get('type') == 'tool']
        cases.append({'id': qid, 'answer_label': 'unknown', 'no_answer_label': None,
                      'seconds': row.get('seconds'), 'tokens': row.get('tokens')})
        sections.extend([f'## 题目 {qid}', '', '**问题**', '', row['question'], '', '**回答**', '', row.get('answer') or '（无回答）', '', '**工具返回**', ''])
        for tool in tools:
            result = str(tool.get('result', ''))
            try:
                result = json.dumps(json.loads(result), ensure_ascii=False, indent=2)
            except (ValueError, TypeError):
                pass
            sections.extend([f"工具：{tool.get('name')}；成功：{tool.get('success')}", '', '```text', result, '```', ''])
        sections.extend(['**人工判断**：答案标签 / 理由 / 依据：', '', '**逐条主张与引用**：主张 / 段落 ID / 标签 / 理由：', ''])
    return cases, '\n'.join(sections)


def main():
    if len(sys.argv) != 3:
        raise SystemExit('用法: python -m eval.prepare_annotation 历史报告目录 新建输出目录')
    source, target = map(Path, sys.argv[1:])
    cases, text = prepare(read(source / 'results.jsonl'), read(source / 'events.jsonl'))
    target.mkdir(parents=True, exist_ok=False)
    (target / 'review.md').write_text(text, encoding='utf-8')
    (target / 'cases.jsonl').write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in cases), encoding='utf-8')
    (target / 'citations.jsonl').write_text('', encoding='utf-8')
    print(f'已生成 {len(cases)} 题工作单；所有答案标签初始为 unknown。')


if __name__ == '__main__':
    main()
