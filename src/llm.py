"""DeepSeek 官方模型接口，密钥来自本机独立配置文件。"""
import os
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import dotenv_values
from openai import OpenAI

PROJECT = Path(__file__).resolve().parent.parent
KEYS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL_ID")


def configure_profile(root=PROJECT):
    """只加载官方配置，避免读取旧服务商的环境文件。"""
    path = root / ".env.deepseek"
    # 无配置时仍可启动服务和运行离线测试；实际调用会给出明确错误。
    values = dotenv_values(path, interpolate=False) if path.is_file() else {}
    # 缺失配置不能静默复用其他环境变量中的旧密钥。
    for key in KEYS:
        os.environ[key] = (values.get(key) or "").strip()
    return 'deepseek'


PROFILE = configure_profile()


def chat(messages, stream=False, tools=None):
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL_ID", "").strip()
    if not all((base_url, api_key, model)):
        raise ValueError("请在 .env.deepseek 中填写 LLM_BASE_URL、LLM_API_KEY 和 LLM_MODEL_ID。")
    url = urlsplit(base_url)
    if (url.scheme != 'https' or url.netloc not in ('api.deepseek.com', 'api.deepseek.com:443')
            or url.path.rstrip('/') not in ('', '/v1') or url.query or url.fragment):
        raise ValueError('LLM_BASE_URL 需要使用 DeepSeek 官方 API 地址。')
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=90.0)
    options = {"model": model, "messages": messages, "stream": stream}
    if stream and os.getenv("LLM_INCLUDE_USAGE", "1").strip() != "0":
        options["stream_options"] = {"include_usage": True}
    if tools:
        options["tools"] = tools
    return client.chat.completions.create(**options)
