"""查看模拟身份并创建本地事件；本阶段不接单、不调用 LLM。"""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from . import simulation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=simulation.DB)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('identities')
    create = commands.add_parser('emit')
    create.add_argument('--role', choices=tuple(simulation.ROLES), required=True)
    create.add_argument('--kind', choices=tuple(simulation.EVENTS), required=True)
    create.add_argument('--text', required=True)
    create.add_argument('--questions', type=Path, required=True)
    show = commands.add_parser('show')
    show.add_argument('trigger_id')
    args = parser.parse_args()
    if args.command == 'identities':
        result = {'identities': simulation.initialize(args.db), 'notice':'这是本地模拟身份，不是登录认证。'}
    elif args.command == 'emit':
        questions = json.loads(args.questions.read_text(encoding='utf-8'))
        trigger = simulation.emit(args.role, args.kind, args.text, questions, args.db)
        result = {'trigger': asdict(trigger), 'status':'pending', 'notice':'已保存事件；尚未准入、接单或调用模型。'}
    else:
        result = simulation.get_event(args.trigger_id, args.db)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
