"""生成可复核的引用位置审计，不自动判断引用是否支持主张。"""
import json
import re
import sys
from difflib import SequenceMatcher
from collections import Counter
from pathlib import Path

HEX = re.compile(r'(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])')


def nearby_candidate(claim, answer, ids):
    """生成辅助定位，不把单行匹配当作引用缺失的事实判断。"""
    best = (0, '')
    for line in answer.splitlines():
        match = SequenceMatcher(None, claim[:500], line[:2000], autojunk=False).find_longest_match()
        if match.size > best[0]:
            best = (match.size, line)
    if best[0] < 8:
        return {'anchor_length': best[0], 'status': 'no_reliable_anchor', 'line': None}
    has_id = bool(set(ids) & set(HEX.findall(best[1])))
    return {'anchor_length': best[0], 'status': 'id_on_same_line' if has_id else 'check_nearby', 'line': best[1]}


def audit(results, events, claims):
    answers = {str(row['id']): row.get('answer') or '' for row in results}
    sources = {qid: set() for qid in answers}
    for event in events:
        qid = str(event.get('id'))
        if qid not in sources or event.get('type') != 'tool' or event.get('name') != 'search_docs':
            continue
        try:
            items = json.loads(event.get('result', ''))
        except (ValueError, TypeError):
            continue
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and isinstance(item.get('source'), str):
                    sources[qid].update(HEX.findall(item['source']))
    case_audit = []
    for qid, answer in answers.items():
        ids = set(HEX.findall(answer))
        case_audit.append({'case_id': qid, 'answer_ids': sorted(ids),
                           'not_in_tool_results': sorted(ids - sources[qid])})
    claim_audit = []
    for row in claims:
        qid = str(row['case_id'])
        if qid not in answers:
            raise ValueError('主张引用了不存在的题目')
        ids = [match for source in row.get('source_ids', []) for match in HEX.findall(source)]
        mentioned = sorted(set(ids) & set(HEX.findall(answers[qid])))
        description = row.get('split_claim') or row.get('annotation', '').splitlines()[:1] or ['']
        description = description if isinstance(description, str) else description[0]
        claim_audit.append({'case_id': qid, 'claim_id': str(row['claim_id']),
                            'declared_sources': ids, 'present_somewhere_in_answer': mentioned,
                            'status': 'needs_context_review' if mentioned else 'not_detected',
                            'claim': description, 'position_candidate': nearby_candidate(description, answers[qid], ids)})
    return case_audit, claim_audit


def main():
    if len(sys.argv) != 4:
        raise SystemExit('用法: python -m eval.audit_citations 原报告目录 标注.jsonl 新建输出目录')
    source, claim_file, output = map(Path, sys.argv[1:])
    read = lambda p: [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
    cases, claims = audit(read(source/'results.jsonl'), read(source/'events.jsonl'), read(claim_file))
    output.mkdir(parents=True, exist_ok=False)
    for name, data in [('cases.jsonl', cases), ('claims.jsonl', claims)]:
        (output/name).write_text(''.join(json.dumps(x, ensure_ascii=False)+'\n' for x in data), encoding='utf-8')
    counts = Counter(x['status'] for x in claims)
    summary = {'cases': len(cases), 'claims': len(claims), 'claim_id_presence': dict(counts),
               'position_candidates': dict(Counter(x['position_candidate']['status'] for x in claims)),
               'cases_with_ids_not_in_tools': sum(bool(x['not_in_tool_results']) for x in cases),
               'limitations': '全文中出现 ID 或同一行匹配均不证明引用支持主张；未识别可能是短 ID、跨行引用或未引用，候选均须人工复核。'}
    (output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
