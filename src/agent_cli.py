"""Agent 命令行入口和交互会话。"""
import sys
from openai import APIError, APIConnectionError
from src.agent import run


def interactive():
    from src.memory import compress
    from src.trace import save_memory
    history = []
    print("输入问题开始对话，输入 exit 退出。")
    while True:
        try:
            question = input("你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if question.lower() in ("exit", "quit"):
            print("再见！")
            break
        if not question:
            continue
        try:
            trace_id = None
            def observe(item):
                nonlocal trace_id
                if item['type'] == 'trace_saved':
                    trace_id = item['run_id']
                elif item['type'] == 'memory_compressed' and trace_id is not None:
                    try:
                        save_memory(trace_id, item)
                    except Exception:
                        print('摘要用量未能写入运行轨迹。')
            answer = run(question, history=history, observer=observe)
            if answer:
                history.extend([{"role": "user", "content": question},
                                {"role": "assistant", "content": answer}])
                try:
                    history = compress(history, observer=observe)
                except (APIError, APIConnectionError, ValueError) as exc:
                    print(f"对话摘要失败，保留原历史：{exc}")
        except (APIError, APIConnectionError, ValueError) as exc:
            print(f"请求失败：{exc}", file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print('用法：python -m src.agent "你的问题"')
        return
    if sys.argv[1] == "--interactive":
        interactive()
        return
    try:
        run(" ".join(sys.argv[1:]))
    except (APIError, APIConnectionError, ValueError) as exc:
        print(f"\n请求失败：{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

