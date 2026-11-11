"""本地事件接单入口：只处理模拟事件，不提供真实身份认证。"""
import argparse
import json
from pathlib import Path
from . import simulation, tickets, orchestrator


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sim-db',type=Path,default=simulation.DB)
    parser.add_argument('--ticket-db',type=Path,default=tickets.DB)
    commands=parser.add_subparsers(dest='command',required=True)
    decide=commands.add_parser('process')
    decide.add_argument('trigger_id')
    decide.add_argument('--mode',choices=('off','observe','auto'),default='observe')
    policy=commands.add_parser('policy')
    policy.add_argument('--mode',choices=('off','observe','auto'),required=True)
    policy.add_argument('--owner-disabled',action='store_true')
    policy.add_argument('--visitor-enabled',action='store_true')
    policy.add_argument('--bot-disabled',action='store_true')
    policy.add_argument('--rule-disabled',action='store_true')
    execute=commands.add_parser('run')
    execute.add_argument('ticket_id')
    execute.add_argument('--retry-failed',action='store_true')
    execute.add_argument('--max-questions',type=int)
    recover=commands.add_parser('recover-assessment')
    recover.add_argument('trigger_id')
    recover.add_argument('--confirm-worker-stopped',action='store_true',required=True)
    args=parser.parse_args()
    if args.command=='process':
        result=orchestrator.process(args.trigger_id,args.mode,sim_db=args.sim_db,ticket_db=args.ticket_db)
    elif args.command=='policy':
        from dataclasses import asdict
        p=orchestrator.configure(args.mode,owner_allowed=not args.owner_disabled,visitor_allowed=args.visitor_enabled,
            bot_allowed=not args.bot_disabled,rule_enabled=not args.rule_disabled,sim_db=args.sim_db,ticket_db=args.ticket_db)
        result={'version':p.version,'mode':p.mode,'notice':'模拟策略不是真实身份认证'}
    elif args.command=='run':
        result=orchestrator.run_approved(args.ticket_id,sim_db=args.sim_db,ticket_db=args.ticket_db,
                                        retry_failed=args.retry_failed,max_questions=args.max_questions)
    else:
        orchestrator.recover_assessment(args.trigger_id,sim_db=args.sim_db)
        result={'status':'pending','trigger_id':args.trigger_id}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
