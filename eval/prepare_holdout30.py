"""固定历史排除集合，按 SHA-256 排序抽取 30 题；不调用模型。"""
import gzip
import argparse
import hashlib
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'dureader'
SOURCE_SHA = '72fbf56f18e162bcec5f8c2c8940f2fe331e7e67336606a7b591047696281c32'
SUBSET_SHA = '07708dbaaa4e52120a07d83ebb8746d76cb51c63e0009b17eaf9ed4de89601cc'
FULL_SHA = '723ee7d23a68e6edb6485e02192d34a93fbd8dbd1a5c3d16cffbd32061318b72'
SEED = 'doc-agent-holdout-20261106-v1'
NEXT_SEED = 'doc-agent-holdout-20261107-v2'
FINAL_SEED = 'doc-agent-holdout-20261107-v3'
OLD_HOLDOUT_SHA = 'ceceac0f48e34f1b3410773a93e1f5c024075b39f1267574df29cd62f1610f81'
V2_HOLDOUT_SHA = '4a25776f4f983212e0d1cf891e85e5873c667021fb100fb7d6562e14b9422a62'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text):
    return ''.join(unicodedata.normalize('NFKC', text).casefold().split())


def choose(rows, prior, count=30, seed=SEED):
    ids = {str(q['id']) for q in prior}
    texts = {normalize(q['text']) for q in prior}
    positives = {str(x) for q in prior for x in q['positive_ids']}
    eligible = []
    for row in rows:
        qid = str(row['query_id'])
        text = row['query']
        gold = sorted({str(p['docid']) for p in row.get('positive_passages', [])})
        if (not gold or not row.get('negative_passages') or not normalize(text)
                or qid in ids or normalize(text) in texts or positives.intersection(gold)):
            continue
        score = hashlib.sha256((seed + ':' + qid).encode()).hexdigest()
        eligible.append((score, qid, text, gold))
    chosen = []
    for _, qid, text, gold in sorted(eligible):
        if normalize(text) in texts or positives.intersection(gold):
            continue
        chosen.append({'id': qid, 'question': text, 'gold_passage_ids': gold,
                       'category': None, 'answer_keywords': []})
        texts.add(normalize(text))
        positives.update(gold)
        if len(chosen) == count:
            break
    if len(chosen) != count:
        raise ValueError('符合排重条件的题目不足')
    return chosen, len(eligible)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--next', action='store_true', help='排除原留出集并抽取第二版')
    group.add_argument('--final-v3', action='store_true', help='排除历史集合和前两版已使用留出集')
    args = parser.parse_args()
    source, subset, full = (DATA / n for n in ('dev.jsonl.gz', 'subset.json', 'full_queries.json'))
    for path, expected in ((source, SOURCE_SHA), (subset, SUBSET_SHA), (full, FULL_SHA)):
        if digest(path) != expected:
            raise ValueError(f'文件哈希不符：{path.name}')
    prior = json.loads(subset.read_text(encoding='utf-8'))['queries'] + json.loads(full.read_text(encoding='utf-8'))['queries']
    if len(prior) != 150 or len({str(q['id']) for q in prior}) != 150:
        raise ValueError('历史题集数量或 ID 不符合预期')
    if args.next or args.final_v3:
        old = DATA / 'holdout_30.jsonl'
        if digest(old) != OLD_HOLDOUT_SHA:
            raise ValueError('原留出集哈希不符')
        previous = [json.loads(line) for line in old.read_text(encoding='utf-8').splitlines() if line.strip()]
        if len(previous) != 30:
            raise ValueError('原留出集数量不符')
        prior += [{'id':x['id'], 'text':x['question'], 'positive_ids':x['gold_passage_ids']} for x in previous]
    if args.final_v3:
        old_v2 = DATA / 'holdout_30_v2.jsonl'
        if digest(old_v2) != V2_HOLDOUT_SHA:
            raise ValueError('第二版留出集哈希不符')
        previous = [json.loads(line) for line in old_v2.read_text(encoding='utf-8').splitlines() if line.strip()]
        if len(previous) != 30:
            raise ValueError('第二版留出集数量不符')
        prior += [{'id': x['id'], 'text': x['question'], 'positive_ids': x['gold_passage_ids']} for x in previous]
    with gzip.open(source, 'rt', encoding='utf-8') as stream:
        rows = [json.loads(line) for line in stream]
    if len({str(r['query_id']) for r in rows}) != len(rows):
        raise ValueError('源文件问题 ID 重复')
    seed = FINAL_SEED if args.final_v3 else NEXT_SEED if args.next else SEED
    chosen, eligible = choose(rows, prior, seed=seed)
    suffix = '_v3' if args.final_v3 else '_v2' if args.next else ''
    output = DATA / f'holdout_30{suffix}.jsonl'
    manifest = DATA / f'holdout_30{suffix}_manifest.json'
    if output.exists() or manifest.exists():
        raise FileExistsError('留出集或清单已存在，拒绝覆盖')
    content = ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n' for row in chosen).encode('utf-8')
    metadata = {'schema': 1, 'seed': seed, 'source_sha256': SOURCE_SHA, 'subset_sha256': SUBSET_SHA,
                'full_queries_sha256': FULL_SHA, 'count': len(chosen), 'eligible_before_selection_dedup': eligible,
                'holdout_sha256': hashlib.sha256(content).hexdigest(), 'sampler_sha256': digest(Path(__file__))}
    if args.next or args.final_v3:
        metadata['excluded_holdout_sha256'] = OLD_HOLDOUT_SHA
        metadata['prior_questions'] = len(prior)
    if args.final_v3:
        metadata['excluded_holdout_v2_sha256'] = V2_HOLDOUT_SHA
    with output.open('xb') as f:
        f.write(content)
    with manifest.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(metadata, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write('\n')
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == '__main__':
    main()
