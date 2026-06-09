"""
内容生成模块 - 连接 LLM + 图片生成 + 视频合成
"""

import json
import os
import requests
import subprocess
import time
from pathlib import Path

# 导入知识库
from modules.knowledge_base import get_relevant_materials, get_materials


# ── DashScope（阿里云百炼）API 配置 ──
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
if not DASHSCOPE_API_KEY:
    key_path = Path(__file__).parent.parent / ".dashscope_key"
    if key_path.exists():
        DASHSCOPE_API_KEY = key_path.read_text().strip()


def generate_copy(product, direction, partner_idea, materials_context="", history_context=""):
    """基于伙伴创意 + 知识库物料生成朋友圈文案"""
    brand_name = "华为坤灵"
    product_name = product.get("name", "")

    direction_name = direction.get("name", "营销推广")

    # 读取合规规则嵌入提示词（不在前端展示）
    rules = _load_config().get("rules", {})
    forbidden = rules.get("forbidden_words", [])
    required = rules.get("required_words", [])
    band_phrases = rules.get("brand_phrases", [])

    compliance_rule = ""
    if forbidden:
        compliance_rule += f"❌ 禁止使用的词汇：{'、'.join(forbidden)}\n"
    if required:
        compliance_rule += f"✅ 必须包含的词汇：{'、'.join(required)}\n"
    if band_phrases:
        compliance_rule += f"✅ 品牌话术参考：{'、'.join(band_phrases)}\n"

    system = f"""你是一个{brand_name}官方社交媒体运营专家，负责为{brand_name}的合作伙伴生成朋友圈推广内容。

【要求】
1. 语言风格：专业、亲切、有科技感，符合华为品牌调性
2. 必须包含"{brand_name}"品牌名
3. 内容基于参考素材，不编造虚假信息
4. 适合微信朋友圈传播，字数100-200字
5. 如果合适可以加1-3个相关话题标签
6. 请直接输出朋友圈文案，不要添加多余的说明文字

【合规约束（必须遵守）】
{compliance_rule}"""

    # 构建历史上下文（对话记忆）
    history_block = ""
    if history_context:
        history_block = f"\n【历史对话（AI已有记忆）】\n{history_context.strip()}\n"

    prompt = f"""产品: {product_name}
营销方向: {direction_name}
方向核心策略: {direction.get("prompt_hint", "")}
合作伙伴的创意想法: {partner_idea}{history_block}

参考素材:
{materials_context if materials_context else "无特定参考素材"}"""

    content = _call_llm(prompt, system_prompt=system)
    return content


def generate_video_script(product, direction, partner_idea, materials_context="", history_context=""):
    """生成短视频脚本（分镜）"""
    brand_name = "华为坤灵"
    product_name = product.get("name", "")

    # 读取合规规则嵌入提示词
    rules = _load_config().get("rules", {})
    forbidden = rules.get("forbidden_words", [])
    required = rules.get("required_words", [])
    band_phrases = rules.get("brand_phrases", [])

    compliance_rule = ""
    if forbidden:
        compliance_rule += f"❌ 禁止使用的词汇：{'、'.join(forbidden)}\n"
    if required:
        compliance_rule += f"✅ 必须包含的词汇：{'、'.join(required)}\n"
    if band_phrases:
        compliance_rule += f"✅ 品牌话术参考：{'、'.join(band_phrases)}\n"

    system = f"""你是一个{brand_name}官方短视频导演，负责为合作伙伴创作朋友圈短视频脚本。

【要求】
1. 视频时长15-30秒，适合朋友圈传播
2. 以分镜表格形式输出：镜头序号 | 画面描述 | 旁白/文案 | 时长
3. 画面描述要清晰可拍，包含构图和视觉元素
4. 旁白要简洁有力，突出产品核心卖点
5. 开头3秒必须有吸引眼球的钩子
6. 结尾包含品牌信息和行动呼吁
7. 直接输出分镜脚本，用表格形式

【合规约束（必须遵守）】
{compliance_rule}"""

    # 构建历史上下文（对话记忆）
    history_block = ""
    if history_context:
        history_block = f"\n【历史对话（AI已有记忆）】\n{history_context.strip()}\n"

    prompt = f"""产品: {product_name}
营销方向: {direction.get("name", "营销推广")}
方向核心策略: {direction.get("prompt_hint", "")}
合作伙伴的创意想法: {partner_idea}{history_block}

参考素材:
{materials_context if materials_context else "无特定参考素材"}"""

    content = _call_llm(prompt, system_prompt=system)
    return content


def generate_images(product, partner_idea, copy_text, count=1, logo_path=None, creative_refs=None, style_refs=None):
    """生成配图 - 调用通义万相 wan2.6-t2i"""
    output_dir = Path(__file__).parent.parent / "data" / "generated" / "images"
    output_dir.mkdir(parents=True, exist_ok=True)

    product_name = product.get("name", "")
    timestamp = int(time.time())

    # 先通过 LLM 生成图片描述提示词
    # 构建参考素材上下文
    ref_extra = ""
    if creative_refs:
        ref_extra += "\n【创意参考：已提供" + str(len(creative_refs)) + "个参考文件，请尽量参考其创意方向】"
    if style_refs:
        ref_extra += "\n【风格参考：已提供" + str(len(style_refs)) + "个风格文件，请尽量参考其画面风格和色调】"
    if logo_path:
        ref_extra += "\n【Logo已上传，生成后叠加角标】"

    system = "你是一个专业的AI图像生成提示词工程师。根据产品信息和营销意图，生成适合AI绘图的提示词。只输出JSON数组，不要其他内容。"

    prompt = f"""根据以下信息，生成{count}条用于AI图像生成的提示词（prompt），每个prompt描述一张适合朋友圈营销的配图。

产品: {product_name}
创意: {partner_idea}
朋友圈文案: {copy_text[:200]}{ref_extra}

要求：
1. 风格可以是产品实拍感、场景氛围感、科技简约感
2. 适合社交媒体传播，视觉吸引力强
3. 每个prompt用中文，简洁描述画面、构图、色调
4. 输出为JSON数组格式：["prompt1", "prompt2"]"""

    image_prompts_str = _call_llm(prompt, system_prompt=system)
    try:
        image_prompts = json.loads(image_prompts_str)
    except:
        image_prompts = [f"{product_name}产品展示，科技感构图，高端质感"]

    generated = []
    for i, img_prompt in enumerate(image_prompts[:count]):
        result = _call_wanx_image(img_prompt, output_dir, f"wanx_{timestamp}_{i}")
        if result and Path(result).exists():
            generated.append(result)
        else:
            generated.append(None)


    # Logo 叠加（如果有）
    if logo_path and Path(str(logo_path)).exists():
        try:
            from PIL import Image, ImageDraw
            logo_img = Image.open(str(logo_path))
            # 等比缩放 Logo 宽度为图片宽度的 12%
            for gi, gen_path in enumerate(generated):
                if gen_path and Path(gen_path).exists():
                    img = Image.open(gen_path)
                    lw = int(img.width * 0.12)
                    lh = int(logo_img.height * (lw / logo_img.width))
                    logo_resized = logo_img.resize((lw, lh), Image.LANCZOS)
                    # 右下角贴 Logo（留 20px 边距）
                    pos = (img.width - lw - 20, img.height - lh - 20)
                    if logo_resized.mode == "RGBA":
                        img.paste(logo_resized, pos, logo_resized)
                    else:
                        img.paste(logo_resized, pos)
                    img.save(gen_path)
                    print(f"[Logo] ✅ 叠加到 {gen_path}")
        except Exception as e:
            print(f"[Logo] ❌ 叠加失败: {e}")

    return generated, image_prompts


def generate_video(product, partner_idea, images=None, prompt=None):
    """生成短视频 - 调用可灵AI kling-v3-video-generation"""
    output_dir = Path(__file__).parent.parent / "data" / "generated" / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    video_path = output_dir / f"video_{timestamp}.mp4"

    # 构造可灵视频提示词
    if not prompt:
        product_name = product.get("name", "")
        prompt = f"{product_name}产品展示场景，高质量营销视频"

    result = _call_kling_video(prompt, str(video_path))
    if result and Path(result).exists():
        return result
    return None


def check_compliance(text, product):
    """内容合规检查"""
    config = _load_config()
    rules = config.get("rules", {})
    
    issues = []

    # 检查必须包含的词
    for word in rules.get("required_words", []):
        if word not in text:
            issues.append(f"缺少必须包含的关键词：{word}")

    # 检查违禁词
    for word in rules.get("forbidden_words", []):
        if word in text:
            issues.append(f"包含敏感词：{word}，请替换")

    # 检查品牌话术
    brand_name = config.get("brand", {}).get("name", "")
    if brand_name not in text:
        issues.append(f"内容中未包含品牌名「{brand_name}」")

    return issues


def _call_llm(prompt, system_prompt="", temperature=0.7, max_tokens=2000):
    """调用 DeepSeek V4 生成内容"""
    from modules.llm_api import call_llm as deepseek_call
    return deepseek_call(
        system_prompt=system_prompt,
        user_prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _call_wanx_image(prompt, output_dir, filename_base):
    """
    调用通义万相 wan2.6-t2i 文生图（同步）
    返回本地图片路径，失败返回 None
    """
    if not DASHSCOPE_API_KEY:
        print("[通义万相] 未配置 DASHSCOPE_API_KEY")
        return None

    print(f"[通义万相] 生成中: {prompt[:60]}...")

    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "model": "wan2.6-t2i",
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ]
        },
        "parameters": {
            "size": "1024*1024",
            "n": 1
        }
    }

    try:
        resp = requests.post(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
            headers=headers,
            json=body,
            timeout=60
        )
        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("output", {}).get("choices", [])
            if choices:
                for item in choices[0].get("message", {}).get("content", []):
                    if "image" in item:
                        url = item["image"]
                        img_resp = requests.get(url, timeout=30)
                        ext = "png"
                        local_path = output_dir / f"{filename_base}.{ext}"
                        output_dir.mkdir(parents=True, exist_ok=True)
                        with open(local_path, "wb") as f:
                            f.write(img_resp.content)
                        print(f"[通义万相] ✅ 保存: {local_path} ({len(img_resp.content)} bytes)")
                        return str(local_path)
        else:
            print(f"[通义万相] ❌ {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[通义万相] ❌ 异常: {type(e).__name__}: {e}")

    return None


def _call_kling_video(prompt, output_path):
    """
    调用可灵AI kling-v3-video-generation 文生视频（异步）
    返回本地视频路径，失败返回 None
    """
    if not DASHSCOPE_API_KEY:
        print("[可灵AI] 未配置 DASHSCOPE_API_KEY")
        return None

    print(f"[可灵AI] 生成中: {prompt[:60]}...")

    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }

    body = {
        "model": "kling/kling-v3-video-generation",
        "input": {"prompt": prompt},
        "parameters": {
            "duration": 5,
            "size": "720*1280",
        }
    }

    try:
        # 1. 提交任务
        resp = requests.post(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis",
            headers=headers,
            json=body,
            timeout=30
        )
        if resp.status_code != 200:
            print(f"[可灵AI] ❌ 提交失败: {resp.text[:200]}")
            return None

        task_id = resp.json().get("output", {}).get("task_id", "")
        if not task_id:
            print("[可灵AI] ❌ 未获取到task_id")
            return None

        print(f"[可灵AI] ⏳ 任务已提交: {task_id}")

        # 2. 轮询结果（最多3分钟）
        poll_headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}"}
        for _ in range(36):  # 36 * 5s = 180s
            time.sleep(5)
            query = requests.get(
                f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}",
                headers=poll_headers,
                timeout=10
            )
            qdata = query.json()
            status = qdata.get("output", {}).get("task_status", "")

            if status == "SUCCEEDED":
                # 可灵返回的是 video 字段（数组）
                videos = qdata.get("output", {}).get("video", [])
                if not videos:
                    videos = qdata.get("output", {}).get("results", [])
                if videos:
                    video_url = None
                    if isinstance(videos, list):
                        video_url = videos[0].get("url", "") or videos[0].get("url", "")
                    elif isinstance(videos, dict):
                        video_url = videos.get("url", "")
                    else:
                        video_url = str(videos)

                    if video_url and video_url.startswith("http"):
                        vid_resp = requests.get(video_url, timeout=60)
                        with open(output_path, "wb") as f:
                            f.write(vid_resp.content)
                        print(f"[可灵AI] ✅ 保存: {output_path} ({len(vid_resp.content)} bytes)")
                        return output_path
            elif status == "FAILED":
                err_msg = qdata.get("output", {}).get("message", "未知错误")
                print(f"[可灵AI] ❌ 生成失败: {err_msg}")
                return None
            else:
                print(f"[可灵AI] ⏳ 状态: {status}")

        print("[可灵AI] ⏰ 超时")
    except Exception as e:
        print(f"[可灵AI] ❌ 异常: {type(e).__name__}: {e}")

    return None


def _load_config():
    config_path = Path(__file__).parent.parent / "config.yaml"
    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
