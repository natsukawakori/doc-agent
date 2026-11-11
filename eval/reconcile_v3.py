"""Convert completed v3 worksheets without changing the human's labels."""
import json
import re
import sys
import hashlib
from pathlib import Path

def main():
    report, out = map(Path, sys.argv[1:])
    read = lambda p: [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]
    results = {str(r['id']): r for r in read(report/'results.jsonl')}
    events = read(report/'events.jsonl')
    files = sorted((report/'人工核验工作单').glob('[0-9][0-9]_*.md'))
    files = [p for p in files if not p.name.startswith('00_')]
    if len(files) != 30 or len(results) != 30:
        raise ValueError('expected 30 result records and 30 worksheets')
    answer_map = {'正确':'correct', '部分正确':'partial', '错误':'incorrect', '无法判断':'unknown'}
    label_map = {'支持':'supported', '部分支持':'partial', '不支持':'unsupported', '无法判断':'unknown', '待核':'unknown'}
    cases, claims, issues, hashes = [], [], [], {}
    for path in files:
        number, qid = path.stem.split('_', 1)
        row = results.pop(qid)
        text = path.read_text(encoding='utf-8')
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        match = re.search(r'\*\*人工判断\*\*[：:]\s*\*\*(正确|部分正确|错误|无法判断)\*\*', text)
        if not match: raise ValueError(f'missing answer label: {path.name}')
        original = text.split('**回答**',1)[1].split('**工具返回**',1)[0].strip()
        if original != (row.get('answer') or '（无回答）').strip():
            issues.append({'id':qid, 'issue':'worksheet answer differs from original result'})
        cases.append({'id':qid, 'answer_label':answer_map[match.group(1)], 'no_answer_label':None,
                      'seconds':row.get('seconds'), 'tokens':row.get('tokens')})
        tail = text.split('**逐条主张与引用**',1)[1]
        blocks = list(re.finditer(r'(?ms)^\s*(\d+)\.\s*\*\*主张\*\*[：:](.*?)(?=^\s*\d+\.\s*\*\*主张\*\*[：:]|\Z)',tail))
        if not blocks: raise ValueError(f'missing claims: {path.name}')
        source_results = '\n'.join(str(e.get('result','')) for e in events if str(e.get('id')) == qid and e.get('attempt') == row.get('attempt') and e.get('type') == 'tool' and e.get('success'))
        for block in blocks:
            claim = block.group(2).strip()
            label = re.search(r'(?m)^\s*标签[：:]\s*\*\*(支持|部分支持|不支持|无法判断|待核|不适用)\*\*', claim)
            if not label: raise ValueError(f'missing claim label: {path.name}/{block.group(1)}')
            if label.group(1) == '不适用': continue
            sources = list(dict.fromkeys(re.findall(r'DuReader:[0-9a-f]{32}', claim, re.I)))
            absent = [s for s in sources if s.lower() not in source_results.lower()]
            if absent: issues.append({'id':qid,'claim':block.group(1),'issue':'source absent from successful tool results','sources':absent})
            claims.append({'case_id':qid,'claim_id':block.group(1),'label':label_map[label.group(1)],
                           'citation_status':'unknown','source_ids':sources,'annotation':claim,'worksheet':path.name})
    if results: raise ValueError('missing worksheets')
    out.mkdir(parents=True, exist_ok=False)
    for filename, rows in [('cases.jsonl', cases), ('citations.jsonl', claims)]:
        (out/filename).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf-8')
    (out/'audit.json').write_text(json.dumps({'worksheet_sha256':hashes,'issues':issues,'case_count':len(cases),'claim_count':len(claims)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'cases':len(cases),'claims':len(claims),'issues':issues},ensure_ascii=False))

if __name__ == '__main__': main()
