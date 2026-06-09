"""
内容生成模块 - 连接 LLM + 图片生成 + 视频合成
"""

import json
import os
import subprocess
import time
from pathlib import Path

# 导入知识库
from modules.knowledge_base import get_relevant_materials, get_materials


def generate_copy(product, direction, partner_idea, materials_context=""):
    """基于伙伴创意 + 知识库物料生成朋友圈文案"""
    brand_name = "华为坤灵"
    product_name = product.get("name", "")

    direction_names = {
        "product_showcase": "产品种草",
        "activity": "活动推广",
        "scene_story": "场景故事",
        "user_case": "客户案例",
    }
    direction_name = direction_names.get(direction.get("id", ""), "营销推广")

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

    prompt = f"""产品: {product_name}
营销方向: {direction_name}
合作伙伴的创意想法: {partner_idea}

参考素材:
{materials_context if materials_context else "无特定参考素材"}"""

    content = _call_llm(prompt, system_prompt=system)
    return content


def generate_video_script(product, direction, partner_idea, materials_context=""):
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

    prompt = f"""产品: {product_name}
营销方向: {direction.get("name", "营销推广")}
合作伙伴的创意想法: {partner_idea}

参考素材:
{materials_context if materials_context else "无特定参考素材"}"""

    content = _call_llm(prompt, system_prompt=system)
    return content


def generate_images(product, partner_idea, copy_text, count=1):
    """生成配图 - 调用 Seedream 图像生成"""
    output_dir = Path(__file__).parent.parent / "data" / "generated" / "images"
    output_dir.mkdir(parents=True, exist_ok=True)

    product_name = product.get("name", "")
    timestamp = int(time.time())

    # 先通过 LLM 生成图片描述
    system = "你是一个专业的AI图像生成提示词工程师。根据产品信息和营销意图，生成适合AI绘图的提示词。只输出JSON数组，不要其他内容。"

    prompt = f"""根据以下信息，生成{count}条用于AI图像生成的提示词（prompt），每个prompt描述一张适合朋友圈营销的配图。

产品: {product_name}
创意: {partner_idea}
朋友圈文案: {copy_text[:200]}

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
        img_dir = output_dir / f"gen_{timestamp}_{i}"
        
        # 调用 Seedream 图片生成能力
        result = _call_seedream(img_prompt, img_dir)
        
        if result and Path(result).exists():
            generated.append(result)
        else:
            # 如果 Seedream 不可用，生成占位图描述
            generated.append(None)

    return generated, image_prompts


def generate_video(product, partner_idea, images):
    """生成短视频 - 调用一键成片能力"""
    # 如果有生成的图片，就用图片合成视频
    # 如果没有图片但有创意描述，先生成图片再合成
    
    output_dir = Path(__file__).parent.parent / "data" / "generated" / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    video_path = output_dir / f"video_{timestamp}.mp4"

    # 调用 xiaoyi-vlog-gen 的一键成片脚本
    if images and any(img for img in images):
        valid_images = [img for img in images if img and Path(img).exists()]
        if valid_images:
            _call_vlog_gen(valid_images, str(video_path))

    return str(video_path) if video_path.exists() else None


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


def _call_seedream(prompt, output_dir):
    """调用 Seedream 图片生成"""
    print(f"[图片生成] 提示词: {prompt[:60]}...")
    seedream_script = os.path.expanduser(
        "~/.openclaw/workspace/skills/seedream-image_gen/scripts/generate_seedream.py"
    )
    
    if Path(seedream_script).exists():
        try:
            result = subprocess.run(
                ["python3", seedream_script, "--prompt", prompt, "--output", str(output_dir)],
                capture_output=True, text=True, timeout=180
            )
            if result.returncode == 0:
                # Seedream 会保存到 output_dir/ 目录下，找最新生成的图片
                if output_dir.exists():
                    files = sorted(output_dir.glob("*generated*.jpg")) + sorted(output_dir.glob("*.jpg"))
                    files = [f for f in files if f.is_file()]
                    if files:
                        return str(files[-1])
        except Exception as e:
            print(f"[Seedream Error] {e}")
    
    return None


def _call_vlog_gen(images, output_path):
    """调用一键成片生成视频"""
    vlog_scripts = os.path.expanduser(
        "~/.openclaw/workspace/skills/xiaoyi-vlog-gen/scripts"
    )
    check_script = os.path.join(vlog_scripts, "check-init.sh")
    
    if Path(check_script).exists():
        try:
            subprocess.run(["bash", check_script], capture_output=True, timeout=30)
        except:
            pass

    # 暂以占位形式返回
    print(f"[视频生成] 输入图片: {len(images)}张, 输出: {output_path}")
    return None


def _load_config():
    config_path = Path(__file__).parent.parent / "config.yaml"
    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
