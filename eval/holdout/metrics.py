"""汇总人工评定；不会根据模型文本自动判定正确性。"""
import json
import hashlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

ANSWER = {'correct','partial','incorrect','unknown'}
CITATION = {'supported','partial','unsupported','unknown'}
PRESENCE = {'present','absent','unknown'}
NO_ANSWER = {'correct','incorrect','unknown'}


def ratio(numerator,denominator):
    return {'numerator':numerator,'denominator':denominator,
            'value':numerator/denominator if denominator else None}


def summarize(cases,citations,no_answers):
    if len(cases)!=30 or len(no_answers)!=10:
        raise ValueError('须提供 30 条普通题和 10 条受控题的完整人工记录')
    if len({str(x.get('id')) for x in cases})!=30 or len({str(x.get('id')) for x in no_answers})!=10:
        raise ValueError('题目 ID 缺失或重复')
    if any(not x.get('id') or x.get('answer_label') not in ANSWER or x.get('citation_presence') not in PRESENCE for x in cases):
        raise ValueError('普通题标签或引用状态无效')
    if any(not x.get('id') or x.get('label') not in NO_ANSWER for x in no_answers):
        raise ValueError('受控无依据题标签无效')
    by_id={str(x['id']):x for x in cases}; grouped=defaultdict(list); seen=set()
    for row in citations:
        case_id=str(row.get('case_id','')); claim=row.get('claim_id'); source=row.get('citation_id'); label=row.get('label')
        key=(case_id,claim,source)
        if case_id not in by_id or not isinstance(claim,str) or not claim or not isinstance(source,str) or not source or label not in CITATION or key in seen:
            raise ValueError('引用项无效、重复或不属于普通题')
        if by_id[case_id]['citation_presence']!='present': raise ValueError('无引用或状态未知的题目不能关联引用项')
        seen.add(key); grouped[case_id].append(label)
    if any(x['citation_presence']=='present' and not grouped[str(x['id'])] for x in cases):
        raise ValueError('标有引用的题目必须至少填写一条实际引用项')
    answers=Counter(x['answer_label'] for x in cases)
    no_answer=Counter(x['label'] for x in no_answers)
    support=Counter(x['label'] for x in citations)
    presence=Counter(x['citation_presence'] for x in cases)
    assessed=sum(support[x] for x in ('supported','partial','unsupported'))
    cited_full=sum(all(label=='supported' for label in labels) for labels in grouped.values())
    return {
        'answer_counts':{x:answers[x] for x in sorted(ANSWER)},
        'answer_correct_all':ratio(answers['correct'],30),
        'answer_correct_assessed':ratio(answers['correct'],30-answers['unknown']),
        'citation_counts':{x:support[x] for x in sorted(CITATION)},
        'citation_item_fully_supported':ratio(support['supported'],assessed),
        'citation_case_fully_supported':ratio(cited_full,presence['present']),
        'citation_presence':{x:presence[x] for x in sorted(PRESENCE)},
        'no_answer_scope':'controlled',
        'no_answer_counts':{x:no_answer[x] for x in sorted(NO_ANSWER)},
        'no_answer_correct_all':ratio(no_answer['correct'],10),
        'no_answer_correct_assessed':ratio(no_answer['correct'],10-no_answer['unknown']),
        'note':'根据人工标签汇总；引用仅覆盖显式标注项，不等于事实真实性或全语料无答案率。'}


def read(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def verify_ids(cases,no_answers,folder):
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    for rows,name,key in ((cases,'holdout_30.jsonl','holdout_sha256'),
                          (no_answers,'controlled_no_answer_10.jsonl','controlled_sha256')):
        raw=(folder/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=manifest[key]: raise ValueError('冻结题集哈希不一致')
        expected={str(json.loads(line)['id']) for line in raw.decode('utf-8').splitlines() if line.strip()}
        if {str(row.get('id')) for row in rows}!=expected: raise ValueError('人工标注的题目 ID 与冻结题集不一致')


def main():
    if len(sys.argv)!=5:
        raise SystemExit('用法: python -m eval.holdout.metrics 普通题标注.jsonl 引用项.jsonl 受控题标注.jsonl 新输出.json')
    cases,citations,no_answers=(read(path) for path in sys.argv[1:4])
    verify_ids(cases,no_answers,Path(__file__).resolve().parent)
    result=summarize(cases,citations,no_answers)
    with Path(sys.argv[4]).open('x',encoding='utf-8',newline='\n') as out:
        json.dump(result,out,ensure_ascii=False,indent=2); out.write('\n')


if __name__=='__main__': main()
