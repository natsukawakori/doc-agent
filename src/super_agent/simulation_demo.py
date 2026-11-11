"""离线演示三类身份和明确/推断事件，不调用 Agent。"""
import json
from dataclasses import asdict
from pathlib import Path
from . import simulation


def main():
    root = Path(__file__).resolve().parents[2]
    folder = root/'data/reports/simulation_stage2_demo'
    folder.mkdir(parents=True, exist_ok=False)
    db = folder/'simulation.sqlite3'
    identities = simulation.initialize(db)
    questions = json.loads((root/'examples/对比问题清单.json').read_text(encoding='utf-8'))
    situations = [('owner','submit','请处理这张问题清单'),
                  ('visitor','submit','访客提交清单'),
                  ('bot','inferred','模拟检测到新清单')]
    items = []
    for role, kind, text in situations:
        trigger = simulation.emit(role,kind,text,questions,db)
        event = simulation.get_event(trigger.id,db)
        if simulation.to_trigger(event) != trigger:
            raise RuntimeError('事件重建失败')
        items.append({'role':role, 'event_kind':kind, 'trigger':asdict(trigger), 'status':event['status']})
    try:
        simulation.emit('bot','submit','不允许的明确请求',questions,db)
    except ValueError as exc:
        bot_refusal = str(exc)
    else:
        raise RuntimeError('机器人明确请求不应被接受')
    result = {'identities':identities,'events':items,'bot_submit_refusal':bot_refusal,
              'notice':'仅生成待研判事件，没有接单、模型调用或工具执行。'}
    (folder/'结果.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'roles':len(identities),'events':len(items),'status':'pending',
                      'report':str(folder/'结果.json')},ensure_ascii=False))


if __name__ == '__main__':
    main()
