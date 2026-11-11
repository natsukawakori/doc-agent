"""命令行多轮对话：输入 exit 或 quit 结束。"""
from openai import APIError, APIConnectionError
from src.llm import chat
from src.memory import compress


def main():
    messages = []
    print("输入问题开始对话，输入 exit 退出。")
    while True:
        try:
            prompt = input("你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if prompt.lower() in ("exit", "quit"):
            print("再见！")
            break
        if not prompt:
            continue
        messages.append({"role": "user", "content": prompt})
        answer = []
        try:
            print("助手：", end="", flush=True)
            for chunk in chat(messages, stream=True):
                if chunk.choices:
                    content = chunk.choices[0].delta.content or ""
                    print(content, end="", flush=True)
                    answer.append(content)
            print()
            if not answer:
                raise ValueError("模型未返回文本内容，请检查模型配置。")
            messages.append({"role": "assistant", "content": "".join(answer)})
            try:
                messages = compress(messages)
            except (APIError, APIConnectionError, ValueError) as exc:
                print(f"对话摘要失败，保留原历史：{exc}")
        except (APIError, APIConnectionError, ValueError) as exc:
            messages.pop()
            print(f"\n请求失败：{exc}")


if __name__ == "__main__":
    main()

