"""离线汇总人工标注；未知值不参与对应指标的分母。"""
import json
import math
import sys
from collections import Counter
from pathlib import Path


def rate(counts, good, assessed):
    denominator = sum(counts[x] for x in assessed)
    return {'value': counts[good] / denominator if denominator else None,
            'numerator': counts[good], 'denominator': denominator,
            'unknown': counts['unknown'], 'counts': dict(counts)}


def summarize(cases, citations):
    if len({str(x['id']) for x in cases}) != len(cases):
        raise ValueError('重复题目 ID')
    ids = {str(x['id']) for x in cases}
    answers, no_answer, support = Counter(), Counter(), Counter()
    scope_counts, citation_status, explicit_support = {}, Counter(), Counter()
    latencies, token_values = [], []
    for row in cases:
        if row['answer_label'] not in ('correct', 'partial', 'incorrect', 'unknown'):
            raise ValueError('答案标签无效')
        answers[row['answer_label']] += 1
        if row.get('no_answer_label') is not None:
            label = row['no_answer_label']
            if label not in ('correct', 'incorrect', 'unknown'):
                raise ValueError('无依据标签无效')
            no_answer[label] += 1
            scope = row.get('no_answer_scope') or 'unspecified'
            if scope not in ('controlled', 'full_corpus', 'unspecified'):
                raise ValueError('无依据题范围无效')
            scope_counts.setdefault(scope, Counter())[label] += 1
        seconds, tokens = row.get('seconds'), row.get('tokens')
        if seconds is not None:
            if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not math.isfinite(seconds) or seconds < 0:
                raise ValueError('耗时无效')
            latencies.append(seconds)
        if tokens is not None:
            if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
                raise ValueError('token 无效')
            token_values.append(tokens)
    seen = set()
    for row in citations:
        key = (str(row['case_id']), str(row['claim_id']))
        if key in seen or key[0] not in ids:
            raise ValueError('引用标注重复或题目不存在')
        seen.add(key)
        label = row['label']
        if label not in ('supported', 'partial', 'unsupported', 'unknown'):
            raise ValueError('引用标签无效')
        support[label] += 1
        status = row.get('citation_status') or 'unknown'
        if status not in ('cited', 'uncited', 'unknown'):
            raise ValueError('引用状态无效')
        citation_status[status] += 1
        if status == 'cited':
            explicit_support[label] += 1
    latencies.sort()
    return {'cases': len(cases), 'answer_correct_rate': rate(answers, 'correct', ('correct', 'partial', 'incorrect')),
            'citation_support_rate': rate(support, 'supported', ('supported', 'partial', 'unsupported')),
            'explicit_citation_support_rate': rate(explicit_support, 'supported', ('supported', 'partial', 'unsupported')),
            'no_answer_correct_rate': rate(no_answer, 'correct', ('correct', 'incorrect')),
            'no_answer_error_rate': rate(no_answer, 'incorrect', ('correct', 'incorrect')),
            'no_answer_by_scope': {scope: rate(counts, 'incorrect', ('correct', 'incorrect'))
                                   for scope, counts in scope_counts.items()},
            'p95_latency_seconds': latencies[math.ceil(.95 * len(latencies)) - 1] if latencies else None,
            'latency_known': len(latencies), 'tokens_known': len(token_values),
            'token_per_case': sum(token_values) / len(token_values) if token_values else None,
            'citation_annotated': len(citations), 'citation_status': dict(citation_status)}


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('用法: python -m eval.quality_metrics 逐题.jsonl 引用.jsonl 输出.json')
    result = summarize(read_jsonl(sys.argv[1]), read_jsonl(sys.argv[2]))
    output = Path(sys.argv[3])
    with output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
