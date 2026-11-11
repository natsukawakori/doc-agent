"""从实际受控场景运行记录生成待填写工作单，不判定答案。"""
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path


def prepare(source, manifest_path, results_path, target):
    source,manifest_path,results_path,target=map(Path,(source,manifest_path,results_path,target))
    raw=source.read_bytes()
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if hashlib.sha256(raw).hexdigest()!=manifest['controlled_sha256']:
        raise ValueError('受控题集哈希不匹配')
    cases=[json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    if len({str(x['id']) for x in cases})!=len(cases): raise ValueError('场景 ID 重复')
    records=defaultdict(list)
    for line in results_path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            item=json.loads(line); records[str(item['id'])].append(item)
    if set(records)-{str(x['id']) for x in cases}: raise ValueError('运行记录包含额外题目')
    sections=[]
    for number,case in enumerate(cases,1):
        qid=str(case['id']); attempts=records[qid]
        complete=[x for x in attempts if x.get('status')=='completed']
        if len(complete)>1: raise ValueError('同一场景有多个成功尝试，需要人工选择')
        result=complete[0] if complete else None
        if result and (result.get('question')!=case['question'] or result.get('documents')!=case['documents']):
            raise ValueError('工作单材料与运行记录不一致')
        filename=f'{number:02d}_{qid}.md'
        body=[f'# 受控场景 {qid}','','## 问题','',case['question'],'','## 模拟资料','']
        for doc in case['documents']:
            body += [f"模拟段落 ID：`{doc['id']}`",'',doc['text'],'']
        body += ['## 模型实际回答','',str(result.get('answer') or '（无回答）') if result else '（尚未成功完成）','',
                 f'运行尝试数：{len(attempts)}；失败次数：{sum(x.get("status")=="error" for x in attempts)}。',
                 '','## 人工标注（请填写）','','- 判断：正确 / 错误 / 无法判断','- 理由：',
                 '- 是否明确说明材料缺少所问事实：','- 是否编造了具体值：','',
                 '仅判定提供的合成材料，不表示整个 DuReader 语料不存在答案。','']
        sections.append((filename,'\n'.join(body),qid))
    target.mkdir(parents=True,exist_ok=False)
    index=['# 受控无依据场景：人工核验','','按 `eval/holdout/rubric.md` 填写；所有判断留空，原始运行记录不修改。','']
    for filename,body,qid in sections:
        (target/filename).write_text(body,encoding='utf-8')
        index.append(f'- [{qid}]({filename})')
    (target/'阅读与填写指引.md').write_text('\n'.join(index)+'\n',encoding='utf-8')
    return len(sections)


def main():
    if len(sys.argv)!=3:
        raise SystemExit('用法: python -m eval.holdout.prepare_controlled_review 受控结果.jsonl 新工作单目录')
    root=Path(__file__).resolve().parent
    count=prepare(root/'controlled_no_answer_10.jsonl',root/'manifest.json',sys.argv[1],sys.argv[2])
    print(f'已生成 {count} 份受控场景工作单，尚未判分。')


if __name__=='__main__': main()
