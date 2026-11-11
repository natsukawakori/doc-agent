"""预先固定规则生成收尾评测，离线执行，不覆盖已有题集。"""
import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path

from eval.prepare_holdout30 import (SOURCE_SHA, SUBSET_SHA, FULL_SHA, OLD_HOLDOUT_SHA,
                                    V2_HOLDOUT_SHA, choose, digest)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/dureader'
SEED = 'doc-agent-final-holdout-20261111-v4'
V3_SHA = '591a53d88592a6058c41a2d4a013c79e603564ceac6d5add53339c52a4701a1f'
EXCLUDE = ('cases.jsonl','evidence_challenge_v1.jsonl','offline_scenarios.jsonl',
           'risk_boundary_v1.jsonl','risk_challenge_v1.jsonl','risk_expanded_v1.jsonl',
           'risk_prompt_holdout_v1.jsonl')


def questions_from(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'question' and isinstance(item,str): yield item
            else: yield from questions_from(item)
    elif isinstance(value,list):
        for item in value: yield from questions_from(item)


def controlled_cases():
    rows = []
    # 每行由项目名称、已知相邻事实和缺失字段组成；不使用真实资料。
    specs = [('澄湖档案','收录了 24 份照片','整理负责人'),('紫穗活动','活动主题是植物绘画','举办地点'),
             ('海屿计划','项目于 2018 年启动','结束年份'),('云鹭研讨','活动分成三个环节','报名截止日期'),
             ('竹陌设备','设备重量为 280 克','电池容量'),('霁光书屋','书屋收藏了 600 本书','每日开放时间'),
             ('松屿展会','展会展示了陶艺作品','参观人数'),('橙湾团队','团队开展了两次访谈','最终获奖情况'),
             ('桐原项目','项目第一版于 2022 年发布','最新版本号'),('蓝澜公司','公司上季度营收为 80 万元','上季度利润')]
    for number,(name,fact,field) in enumerate(specs,1):
        identifier=hashlib.sha256(f'controlled-final-v4:{number}'.encode()).hexdigest()[:32]
        rows.append({'id':f'N{number:02d}','category':'缺失字段','scope':'controlled',
                     'question':f'{name}的{field}是什么？',
                     'documents':[{'id':identifier,'text':f'{name}是虚构场景，现有记录仅说明：{fact}。'}],
                     'expected':'指出给定材料没有所问事实，不编造具体值。'})
    return rows


def generate(output):
    inputs = [(DATA/'dev.jsonl.gz',SOURCE_SHA),(DATA/'subset.json',SUBSET_SHA),
              (DATA/'full_queries.json',FULL_SHA),(DATA/'holdout_30.jsonl',OLD_HOLDOUT_SHA),
              (DATA/'holdout_30_v2.jsonl',V2_HOLDOUT_SHA),(DATA/'holdout_30_v3.jsonl',V3_SHA)]
    hashes = {}
    for path, expected in inputs:
        actual=digest(path)
        if actual != expected: raise ValueError(f'历史输入哈希不一致：{path.name}')
        hashes[path.name]=actual
    prior=json.loads(inputs[1][0].read_text(encoding='utf-8'))['queries']
    prior+=json.loads(inputs[2][0].read_text(encoding='utf-8'))['queries']
    for path,_ in inputs[3:]:
        old=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        if len(old)!=30: raise ValueError(f'历史留出集数量异常：{path.name}')
        prior += [{'id':x['id'],'text':x['question'],'positive_ids':x['gold_passage_ids']} for x in old]
    for name in EXCLUDE:
        path=ROOT/'eval'/name
        hashes['eval/'+name]=digest(path)
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                for question in questions_from(json.loads(line)):
                    prior.append({'id':'external:'+str(len(prior)),'text':question,'positive_ids':[]})
    examples=ROOT/'app/static/super.js'
    hashes['app/static/super.js']=digest(examples)
    for text in re.findall(r"'([^'\n]{5,500})'",examples.read_text(encoding='utf-8')):
        prior.append({'id':'example:'+str(len(prior)),'text':text,'positive_ids':[]})
    with gzip.open(inputs[0][0],'rt',encoding='utf-8') as stream:
        rows=[json.loads(line) for line in stream]
    if len({str(row['query_id']) for row in rows}) != len(rows): raise ValueError('源问题 ID 重复')
    chosen,eligible=choose(rows,prior,count=30,seed=SEED)
    for row in chosen:
        row['gold_passage_id']=row['gold_passage_ids'][0]
        row['category']='retrieval'
    controlled=controlled_cases()
    def encode(rows):
        return ''.join(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n' for x in rows).encode('utf-8')
    raw, no_answer = encode(chosen), encode(controlled)
    manifest={'schema':1,'seed':SEED,'count':len(chosen),'controlled_count':len(controlled),
              'eligible_before_selection_dedup':eligible,'prior_records':len(prior),'inputs':hashes,
              'sampler_sha256':digest(Path(__file__)),'selection_dependency_sha256':digest(ROOT/'eval/prepare_holdout30.py'),
              'holdout_sha256':hashlib.sha256(raw).hexdigest(),'controlled_sha256':hashlib.sha256(no_answer).hexdigest(),
              'limits':'完全重复排除不证明语义独立；无依据题为合成受控材料。'}
    files={'holdout_30.jsonl':raw,'controlled_no_answer_10.jsonl':no_answer,
           'manifest.json':(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode('utf-8')}
    if any((output/name).exists() for name in files): raise FileExistsError('评测题集或清单已存在，拒绝覆盖')
    output.mkdir(parents=True,exist_ok=True)
    for name, content in files.items():
        with (output/name).open('xb') as f: f.write(content)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'eval/holdout')
    args=parser.parse_args()
    print(json.dumps(generate(args.output_dir),ensure_ascii=False))


if __name__=='__main__': main()
