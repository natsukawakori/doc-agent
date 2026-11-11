"""Preserve the original judgments and create a separately traceable revision."""
import json
from pathlib import Path
from eval.quality_metrics import summarize

P = Path('data/reports/annotation_review_20261106')


def read(name):
    return [json.loads(x) for x in (P/name).read_text(encoding='utf-8').splitlines()]


def main():
    cases, claims = read('cases.jsonl'), read('citations_reconciled.jsonl')
    for c in cases:
        c['original_answer_label'] = c['answer_label']
        if c['id'] == '549':
            c['answer_label'] = 'partial'
            c['revision_reason'] = '回答同时给出互相矛盾的升级边界，按整份回答可靠性评分。'
        if c['id'] == '1061':
            c['answer_label'] = 'partial'
            c['revision_reason'] = '方案六擅自将筋斗云解释成七十二斩并重复列出，无法确认是有效五技能方案。'
        if c['id'] == '869':
            c['answer_label'] = 'partial'
            c['revision_reason'] = '虽提醒安全限制，仍把未经验证的粗盐和按摩作为辅助建议，证据不足。'
        if c['id'] in {'764', '869', '1158', '1357', '1600', '173'}:
            c['review_flag'] = '健康或金融高风险题，当前仅证据内判，事实可靠性未经独立专业核验。'
    out = []
    for c in claims:
        key = (c['case_id'], c['claim_id'])
        if key == ('869', '6'):
            for suffix, text, label in [('a', '粗盐敷腹及排出水分的说法', 'supported'),
                                        ('b', '排水不等于脂肪减少', 'unknown')]:
                out.append({**c, 'claim_id': c['claim_id']+suffix, 'label': label,
                            'split_claim': text, 'review_note': '拆分来源转述与附加判断；后者未作为引用支持结论。'})
        elif key == ('1061', '7'):
            for suffix, text, label in [('a', '方案1至3', 'supported'), ('b', '方案4至5', 'supported'), ('c', '方案6及其五项不重复技能', 'unsupported')]:
                out.append({**c, 'claim_id': c['claim_id']+suffix, 'label': label,
                            'split_claim': text, 'review_note': '对照模型实际看到的来源与答案；方案六把筋斗云解释成七十二斩并重复。'})
        elif key == ('1061', '8'):
            for suffix, text, label in [('a', '来源提及筋斗云', 'supported'), ('b', '筋斗云应为七十二斩', 'unsupported')]:
                out.append({**c, 'claim_id': c['claim_id']+suffix, 'label': label,
                            'split_claim': text, 'review_note': '来源提及筋斗云，但未提供将其改称七十二斩的证据。'})
        else:
            out.append(c)
    def write(name, data):
        path = P/name
        with path.open('x', encoding='utf-8') as f:
            for row in data:
                f.write(json.dumps(row, ensure_ascii=False)+'\n')
    write('cases_revised_v2.jsonl', cases)
    write('citations_revised_v2.jsonl', out)
    summary = summarize(cases, out)
    (P/'revised_summary_v2.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('已保留原标签，生成修订版本；高风险事实未经独立专业核验。')


if __name__ == '__main__':
    main()
