"""把完整运行结果整理成逐题工作单；只读取实际运行证据。"""
import json
import re
import sys
from pathlib import Path
from eval.prepare_annotation import prepare, read


def main():
    if len(sys.argv) != 3:
        raise SystemExit('用法: python -m eval.prepare_review_packets 报告目录 新建工作单目录')
    source, target = map(Path, sys.argv[1:])
    rows, events = read(source / 'results.jsonl'), read(source / 'events.jsonl')
    if not rows or len({str(row['id']) for row in rows}) != len(rows):
        raise ValueError('结果为空或题目 ID 重复')
    sections = []
    for number, row in enumerate(rows, 1):
        qid = str(row['id'])
        if not re.fullmatch(r'[A-Za-z0-9_-]+', qid):
            raise ValueError('题目 ID 不适合作文件名')
        _, body = prepare([row], events)
        sections.append((f'{number:02d}_{qid}.md', body, row['question']))
    target.mkdir(parents=True, exist_ok=False)
    index = ['# 逐题人工核验', '', '每题一份工作单，按顺序打开填写。保留无法判断，不要猜测。', '',
             '1. 先读问题和回答，判断是否完整、正确；不能从提供材料或可靠依据判断时写“无法判断”。',
             '2. 再选取至少一条可独立核对的事实主张，找到其引用段落或网址，判断支持、部分支持、不支持或无法判断。',
             '3. 写下理由及依据；未给出引用、只有截短 ID、材料缺失或资料本身过时，都如实注明。',
             '4. 如果题目涉及医疗等专业知识而你不能确认，不需要自行给出专业结论，选“无法判断”。', '',
             '可以直接在每份文件末尾填写“人工判断”和“逐条主张与引用”。完成后交回该文件夹即可；原始答案和证据请保留。', '']
    for filename, body, question in sections:
        (target / filename).write_text(body, encoding='utf-8')
        index.append(f'- [{filename}]({filename})：{question}')
    (target / '阅读与填写指引.md').write_text('\n'.join(index) + '\n', encoding='utf-8')
    (target / 'source.json').write_text(json.dumps({'report': str(source.resolve()), 'count': len(rows)}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'已生成 {len(rows)} 份逐题工作单。')


if __name__ == '__main__':
    main()
