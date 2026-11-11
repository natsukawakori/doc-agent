"""保留人工原文；提取标注并附上当时工具实际返回的证据。"""
import json
import re
import sys
from pathlib import Path


def reconcile(annotation, results, events):
    by_id = {str(x['id']): x for x in results}
    cases, claims, lines = [], [], ['# 人工标注核对材料', '', '以下证据来自当时模型收到的工具返回，不是事后扩展全文。', '']
    sections = re.findall(r'^## \d+\. 题目 (\d+) .*?(?=^## \d+\.|\Z)', annotation, re.M | re.S)
    blocks = list(re.finditer(r'^## \d+\. 题目 (\d+) .*?(?=^## \d+\.|\Z)', annotation, re.M | re.S))
    if len(sections) != 20 or len(set(sections)) != 20 or set(sections) != set(by_id):
        raise ValueError('标注题目与结果不一致')
    mapping = {'正确': 'correct', '部分正确': 'partial', '错误': 'incorrect', '无法判断': 'unknown'}
    for m in blocks:
        qid, block = m.group(1), m.group()
        label = re.search(r'### 人工判断[：:]\s*\*\*(部分正确|正确|错误|无法判断)', block)
        if not label:
            raise ValueError('未找到答案标签：' + qid)
        result = by_id[qid]
        cases.append({'id': qid, 'answer_label': mapping[label.group(1)], 'no_answer_label': None,
                      'seconds': result.get('seconds'), 'tokens': result.get('tokens')})
        snippets = {}
        for event in events:
            if str(event.get('id')) != qid or event.get('type') != 'tool':
                continue
            try:
                data = json.loads(event['result'])
            except (ValueError, TypeError):
                continue
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        snippets[item.get('source', '')] = item.get('text', '')
        lines += [f'## {qid}', '', f"问题：{result['question']}", '', f"回答：{result.get('answer')}", '']
        parts = re.split(r'(?m)^\d+\. \*\*主张\*\*[：:]?', block)[1:]
        for index, part in enumerate(parts, 1):
            label = re.search(r'标签[：:]\s*\*\*(支持|不支持|待核|不适用)', part)
            if not label:
                raise ValueError(f'未找到主张标签：{qid}/{index}')
            kind = label.group(1)
            # 组合主张出现部分待核时，整体保守归为 unknown。
            value = {'支持': 'supported', '不支持': 'unsupported', '待核': 'unknown'}.get(kind)
            if value and '待核' in part:
                value = 'unknown'
            ids = list(dict.fromkeys(re.findall(r'DuReader:[a-f0-9]{32}', part)))
            if value:
                claims.append({'case_id': qid, 'claim_id': str(index), 'label': value,
                               'source_ids': ids, 'annotation': part.strip()})
            if kind == '待核' or '待核' in part or kind == '不支持':
                lines += [f'### 主张 {index}', '', part.strip(), '']
                for source in ids:
                    lines += [f'**{source}：当时工具返回**', '', snippets.get(source, '【该 ID 不在本次工具结果中】'), '']
    return cases, claims, '\n'.join(lines)


def main():
    if len(sys.argv) != 4:
        raise SystemExit('用法: python -m eval.reconcile_annotations 标注.md 原报告目录 新建输出目录')
    ann, original, output = map(Path, sys.argv[1:])
    read = lambda p: [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
    cases, claims, report = reconcile(ann.read_text(encoding='utf-8'), read(original/'results.jsonl'), read(original/'events.jsonl'))
    output.mkdir(parents=True, exist_ok=False)
    for name, data in [('cases.jsonl', cases), ('citations.jsonl', claims)]:
        (output/name).write_text(''.join(json.dumps(x, ensure_ascii=False)+'\n' for x in data), encoding='utf-8')
    (output/'evidence_review.md').write_text(report, encoding='utf-8')
    print(f'整理 {len(cases)} 题、{len(claims)} 项主张；待核项不计入支持率。结果是初稿，须人工复核。')


if __name__ == '__main__':
    main()
