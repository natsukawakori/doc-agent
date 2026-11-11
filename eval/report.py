"""将离线质量指标转换为 Markdown；不伪造未完成的评估。"""
import json
import sys
from pathlib import Path


def report(summary):
    lines = ['| 指标 | 结果 |', '| --- | --- |']
    for key, label in [('answer_correct_rate', '答案完全正确率'),
                       ('citation_support_rate', '标注来源支持率（含引用状态未知）'),
                       ('no_answer_correct_rate', '无依据正确拒答率')]:
        entry = summary[key]
        value = '未评估' if entry['value'] is None else f"{entry['value']:.2%}（{entry['numerator']}/{entry['denominator']}）"
        lines.append(f'| {label} | {value}；无法判断 {entry["unknown"]} |')
    if 'no_answer_error_rate' in summary:
        entry = summary['no_answer_error_rate']
        value = '未评估' if entry['value'] is None else f"{entry['value']:.2%}（{entry['numerator']}/{entry['denominator']}）"
        lines.append(f'| 无依据误答率 | {value}；无法判断 {entry["unknown"]} |')
        for scope, entry in summary.get('no_answer_by_scope', {}).items():
            value = '未评估' if entry['value'] is None else f"{entry['value']:.2%}（{entry['numerator']}/{entry['denominator']}）"
            lines.append(f'| 无依据误答率：{scope} | {value}；无法判断 {entry["unknown"]} |')
    if 'explicit_citation_support_rate' in summary:
        entry = summary['explicit_citation_support_rate']
        value = '未评估' if entry['value'] is None else f"{entry['value']:.2%}（{entry['numerator']}/{entry['denominator']}）"
        lines.append(f'| 已明确引用主张的支持率 | {value}；无法判断 {entry["unknown"]} |')
    for key, label, unit in [('p95_latency_seconds', 'P95 耗时', '秒'), ('token_per_case', '平均每题 token（有值样本）', '')]:
        value = summary[key]
        lines.append(f'| {label} | {"未评估" if value is None else f"{value:.2f} {unit}"} |')
    lines.append(f'\n题目数：{summary["cases"]}；引用主张标注数：{summary["citation_annotated"]}；token 有值题数：{summary["tokens_known"]}。')
    if 'citation_status' in summary:
        lines.append(f'引用状态计数（人工标注，未知不推断）：{summary["citation_status"]}。')
    lines.append('\n注意：仅反映输入标注和样本；未经独立事实核验的答案及待核条目不可视为最终质量结论。')
    return '\n'.join(lines)+'\n'


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('用法: python -m eval.report 汇总.json 输出.md')
    summary = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    with Path(sys.argv[2]).open('x', encoding='utf-8') as f:
        f.write(report(summary))
