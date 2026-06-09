"""
DeepSeek / LLM API 调用模块
默认使用 DeepSeek 官方 API，也支持环境变量配置
"""

import json
import os
import requests
from pathlib import Path


# DeepSeek 官方配置
DEEPSEEK_API_KEY = ""
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


def set_api_key(api_key):
    """设置 DeepSeek API Key（可在运行时切换）"""
    global DEEPSEEK_API_KEY
    DEEPSEEK_API_KEY = api_key


def _get_api_config():
    """获取 API 配置：优先环境变量（Streamlit Cloud），其次代码内置"""
    # 方案 1: 环境变量（适用于 Streamlit Cloud 部署）
    env_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if env_key:
        return {
            "base_url": os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL).rstrip("/"),
            "api_key": env_key,
            "model": os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_MODEL),
            "timeout": int(os.environ.get("LLM_TIMEOUT", "60")),
        }

    # 方案 2: 代码内置 API Key（本地部署）
    if DEEPSEEK_API_KEY:
        return {
            "base_url": DEEPSEEK_BASE_URL,
            "api_key": DEEPSEEK_API_KEY,
            "model": DEEPSEEK_MODEL,
            "timeout": 60,
        }

    # 方案 3: 旧的 OpenClaw 配置（兼容）
    models_path = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "models.json"
    if models_path.exists():
        try:
            with open(models_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            provider = cfg.get("providers", {}).get("xiaoyiprovider", {})
            return {
                "base_url": provider.get("baseUrl", "").rstrip("/"),
                "api_key": provider.get("headers", {}).get("x-api-key", ""),
                "x_uid": provider.get("headers", {}).get("x-uid", ""),
                "model": "LLM_DeepSeekV4_Thinking",
                "timeout": 60,
            }
        except Exception:
            pass

    return {"base_url": "", "api_key": "", "model": "", "timeout": 60}


def _parse_sse_response(text):
    """解析 SSE 流式响应，合并所有 delta.content"""
    full_text = ""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data: ") and line != "data: [DONE]":
            try:
                data = json.loads(line[6:])
                choices = data.get("choices", [])
                if choices:
                    msg = choices[0].get("delta", None) or choices[0].get("message", {})
                    content = msg.get("content", "")
                    if content:
                        full_text += content
            except json.JSONDecodeError:
                continue
    return full_text.strip()


def call_llm(
    system_prompt="",
    user_prompt="",
    temperature=0.7,
    max_tokens=2000,
    json_mode=False,
):
    """
    调用 LLM 生成内容
    默认使用 DeepSeek 官方 API，支持 SSE 流式 / 非流式
    """
    config = _get_api_config()

    # 未配置 API Key
    if not config["api_key"]:
        return _mock_llm_response(system_prompt, user_prompt)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    # 构建请求头
    is_deepseek = "api.deepseek.com" in config.get("base_url", "")
    if is_deepseek or config["base_url"] == DEEPSEEK_BASE_URL:
        # DeepSeek 官方 API 标准格式
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }
        base_url = DEEPSEEK_BASE_URL
        model = config.get("model", DEEPSEEK_MODEL)
    else:
        # 兼容模式（xiaoyiprovider 等）
        headers = {
            "Accept": "text/event-stream",
            "x-request-from": "openclaw",
            "x-uid": config.get("x_uid", ""),
            "x-api-key": config["api_key"],
            "Content-Type": "application/json",
        }
        base_url = config["base_url"]
        model = config.get("model", "LLM_DeepSeekV4_Thinking")

    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    if json_mode:
        body["response_format"] = {"type": "json_object"}

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=body,
            timeout=config.get("timeout", 60),
            stream=True,
        )
        resp.raise_for_status()
        full_text = _parse_sse_response(resp.text)
        return full_text if full_text else "[LLM返回为空]"
    except Exception as e:
        return f"[LLM调用失败: {type(e).__name__}: {e}]"


def _mock_llm_response(system_prompt, user_prompt):
    """
    降级模式：当 LLM 不可用时返回提示文案
    """
    return (
        "【演示模式 - 未配置 LLM API】\n\n"
        "📱 华为灵眸 DF10 — 守护你的每一个重要时刻\n\n"
        "不管是在家、在公司，还是在路上，"
        "灵眸 DF10 智能摄像头都能给你全天候的安心守护。\n"
        "高清画质、智能告警、AI 人形检测——\n"
        "看得清，辨得准，反应快。\n\n"
        "智慧安防，一「眸」了然。\n\n"
        "💡 提示：请在页面后台设置 DeepSeek API Key 以启用真实 AI"
    )
