"""
DeepSeek V4 / LLM API 调用模块
支持本地 OpenClaw 环境和 Streamlit Cloud 环境（通过环境变量）
"""

import json
import os
import requests
from pathlib import Path


def _get_api_config():
    """获取 API 配置：优先 OpenClaw models.json，其次环境变量"""
    # 方案 1: OpenClaw 本地配置
    models_path = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "models.json"
    if models_path.exists():
        try:
            with open(models_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            provider = cfg.get("providers", {}).get("xiaoyiprovider", {})
            model_cfg = provider.get("models", [{}])[0] if provider.get("models") else {}
            return {
                "base_url": provider.get("baseUrl", "").rstrip("/"),
                "api_key": provider.get("headers", {}).get("x-api-key", ""),
                "x_uid": provider.get("headers", {}).get("x-uid", ""),
                "model": model_cfg.get("id", "LLM_DeepSeekV4_Thinking"),
                "timeout": provider.get("timeoutSeconds", 600),
            }
        except Exception:
            pass

    # 方案 2: 环境变量（适用于 Streamlit Cloud / 其他部署）
    return {
        "base_url": os.environ.get("LLM_BASE_URL", "").rstrip("/"),
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "x_uid": os.environ.get("LLM_X_UID", ""),
        "model": os.environ.get("LLM_MODEL", "LLM_DeepSeekV4_Thinking"),
        "timeout": int(os.environ.get("LLM_TIMEOUT", "60")),
    }


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
    调用 LLM 生成内容 (SSE 流式 / 非流式均支持)
    """
    config = _get_api_config()

    # 降级模式：未配置 LLM 时返回模拟文案，让界面仍然可用
    if not config["base_url"] or not config["api_key"]:
        return _mock_llm_response(system_prompt, user_prompt)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    headers = {
        "Accept": "text/event-stream",
        "x-request-from": "openclaw",
        "x-uid": config["x_uid"],
        "x-api-key": config["api_key"],
        "Content-Type": "application/json",
    }

    body = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    if json_mode:
        body["response_format"] = {"type": "json_object"}

    try:
        resp = requests.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=body,
            timeout=config["timeout"],
            stream=True,
        )
        resp.raise_for_status()
        full_text = _parse_sse_response(resp.text)
        return full_text if full_text else "[LLM返回为空]"
    except Exception as e:
        return f"[LLM调用失败: {type(e).__name__}: {e}]"


def _mock_llm_response(system_prompt, user_prompt):
    """
    降级模式：当 LLM 不可用时返回模拟文案
    让用户可以先体验界面交互流程
    """
    return (
        "【演示模式 - 未配置 LLM API】\n\n"
        "📱 华为灵眸 DF10 — 守护你的每一个重要时刻\n\n"
        "不管是在家、在公司，还是在路上，"
        "灵眸 DF10 智能摄像头都能给你全天候的安心守护。\n"
        "高清画质、智能告警、AI 人形检测——\n"
        "看得清，辨得准，反应快。\n\n"
        "智慧安防，一「眸」了然。\n\n"
        "💡 提示：请在 Streamlit Cloud Secrets 中配置以下环境变量即可启用真实 AI：\n"
        "LLM_BASE_URL / LLM_API_KEY / LLM_X_UID"
    )
