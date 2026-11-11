"""本地工单实验入口：创建、执行、暂停、查看和显式恢复。"""
import argparse
import json
from pathlib import Path
from .domain import Mandate
from . import tickets
from .ticket_runner import run_ticket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=tickets.DB, help='工单 SQLite 文件')
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create', help='从 JSON 清单创建本地工单')
    create.add_argument('questions', type=Path)
    create.add_argument('--trigger-id', required=True)
    for name in ('run', 'show', 'pause', 'recover', 'set-retrieval'):
        cmd = commands.add_parser(name)
        cmd.add_argument('ticket_id')
        if name == 'run':
            cmd.add_argument('--max-questions', type=int)
            cmd.add_argument('--retry-failed', action='store_true')
        if name == 'recover':
            cmd.add_argument('--confirm-worker-stopped', action='store_true', required=True,
                             help='确认旧执行进程已经退出；不自动重试未确定的题目')
        if name == 'set-retrieval':
            cmd.add_argument('level', type=int, choices=(0,1,2,3))
    args = parser.parse_args()
    if args.command == 'create':
        questions = json.loads(args.questions.read_text(encoding='utf-8'))
        grant = Mandate(args.trigger_id, 'cli', 'local-demo', 'explicit', 'listed', 'local-demo-v1')
        ticket_id, created = tickets.create_ticket(grant, questions, path=args.db)
        result = {'ticket_id': ticket_id, 'created': created,
                  'notice': '当前为本地工单实验；尚未接入准入和身份认证。'}
    elif args.command == 'run':
        result = run_ticket(args.ticket_id, path=args.db, retry_failed=args.retry_failed, max_questions=args.max_questions)
    elif args.command == 'pause':
        tickets.request_pause(args.ticket_id, path=args.db)
        result = tickets.get_ticket(args.ticket_id, path=args.db)
    elif args.command == 'set-retrieval':
        version = tickets.set_retrieval_level(args.ticket_id, args.level, path=args.db)
        result = {'ticket_id':args.ticket_id,'retrieval_level':args.level,'version':version}
    elif args.command == 'recover':
        tickets.recover_interrupted(args.ticket_id, path=args.db)
        result = tickets.get_ticket(args.ticket_id, path=args.db)
    else:
        result = tickets.get_ticket(args.ticket_id, path=args.db)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
