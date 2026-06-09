"""
华为伙伴营销内容协作平台 v0.1 Demo
Streamlit 网页应用
"""

import streamlit as st
import sys
import os
import json
import time
from pathlib import Path

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent))

# 初始化 LLM 配置 - DeepSeek 官方 Key
# 本地部署直接内置，Streamlit Cloud 通过环境变量覆盖
from modules.llm_api import set_api_key
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
if not DEEPSEEK_KEY:
    # 从配置文件读取本地 Key
    key_path = Path(__file__).parent / ".api_key"
    if key_path.exists():
        DEEPSEEK_KEY = key_path.read_text().strip()
if DEEPSEEK_KEY:
    set_api_key(DEEPSEEK_KEY)

from modules.knowledge_base import (
    get_materials, add_material, add_link,
    get_links, delete_link, add_links_batch, unified_search,
    get_knowledge_stats, load_config
)
from modules.content_gen import (
    generate_copy, generate_video_script, generate_images,
    generate_video
)
from modules.db import (
    submit_content, save_video, get_pending_contents, get_approved_contents,
    get_rejected_contents, get_all_contents, get_content_by_id,
    approve_content, reject_content, get_videos_for_content,
    get_downloadable_videos
)
from modules.partner_scraper import search_and_fetch_materials

st.set_page_config(
    page_title="华为伙伴营销内容协作平台",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── 初始化 Session State ───────────────────────────────────
DEFAULT_STATE = {
    "partner_idea": "",
    "generated_content": None,
    "generated_images": None,
    "image_prompts": None,
    "submitted": False,
    "current_tab": "伙伴端",
    "review_queue": [],
    "materials_loaded": False,
    "_sel_dir": None,
    "_reviewing": None,
    "chat_messages": [],
    "_revise_idea": "",
    "_revise_result_id": None,
    "logo_file": None,
    "logo_file_name": "",
    "creative_ref_files": [],
    "style_ref_files": [],
}
for key, val in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = val

config = load_config()
products = config.get("products", [])


# ═══════════════════════════════════════════════════════════════
# 伙伴端页面
# ═══════════════════════════════════════════════════════════════
def render_partner_page(product, config):
    """伙伴端 — 对话式AI界面，类似豆包对话框"""
    # 初始化对话记忆
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
        st.session_state._pending_regenerate = False

    directions = product.get("directions", [])
    all_output_types = ["文案+配图", "短视频", "脚本"]

    # ─── 顶栏：产品信息 ───
    st.markdown(f"### 🎬 创作伙伴 — {product['name']}")
    st.caption("像聊天一样描述你的想法，AI 自动生成营销内容并支持反复打磨 ✨")

    # ─── 建议框（直接提交管理端） ───
    with st.expander("💬 给管理端提建议（可选）"):
        st.caption("你的建议会直接发送给管理端，帮助平台优化")
        suggestion = st.text_area(
            "输入建议内容",
            placeholder="例如：希望增加更多产品参考素材 / 建议优化某个方向的生成效果…",
            key="suggestion_input",
            label_visibility="collapsed",
        )
        if st.button("📨 提交建议", type="primary", use_container_width=True, key="submit_suggestion"):
            if suggestion.strip():
                from modules.db import submit_content
                submit_content(
                    product_id=product.get("id", ""),
                    product_name=product.get("name", ""),
                    partner="伙伴建议",
                    idea=suggestion.strip(),
                    direction_id="suggestion",
                    direction_name="💬 伙伴建议",
                    copy="",
                    status="pending",
                )
                st.success("✅ 建议已提交给管理端，感谢你的反馈！")
                st.balloons()
                st.rerun()
            else:
                st.warning("请输入建议内容")

    # ─── 上传区域（可折叠） ───
    with st.expander("📎 上传参考素材（可选）"):
        col_logo, col_creative, col_style = st.columns(3)

        # 1. Logo 上传
        with col_logo:
            st.markdown("**🏢 Logo（伙伴公司）**")
            st.caption("上传后自动作为角标叠加到图片/视频")
            uploaded_logo = st.file_uploader(
                "选择 Logo 图片", type=["png", "jpg", "jpeg"],
                key="logo_upload", label_visibility="collapsed"
            )
            if uploaded_logo:
                logo_dir = Path(__file__).parent / "data" / "uploads" / "logos"
                logo_dir.mkdir(parents=True, exist_ok=True)
                logo_path = logo_dir / uploaded_logo.name
                with open(logo_path, "wb") as f:
                    f.write(uploaded_logo.getbuffer())
                st.session_state.logo_file = str(logo_path)
                st.session_state.logo_file_name = uploaded_logo.name
                st.success(f"✅ Logo 已上传：{uploaded_logo.name}")
            if st.session_state.get("logo_file"):
                if st.button("🗑️ 清除 Logo", key="clear_logo", use_container_width=True):
                    st.session_state.logo_file = None
                    st.session_state.logo_file_name = ""
                    st.rerun()

        # 2. 创意参考上传
        with col_creative:
            st.markdown("**💡 创意参考**")
            st.caption("AI 尽量参考这里的创意风格")
            creative_files = st.file_uploader(
                "上传参考图", type=["png", "jpg", "jpeg", "pdf", "pptx"],
                accept_multiple_files=True,
                key="creative_ref", label_visibility="collapsed"
            )
            if creative_files:
                ref_dir = Path(__file__).parent / "data" / "uploads" / "creative_refs"
                ref_dir.mkdir(parents=True, exist_ok=True)
                paths = []
                for f in creative_files:
                    fp = ref_dir / f.name
                    with open(fp, "wb") as out:
                        out.write(f.getbuffer())
                    paths.append(str(fp))
                st.session_state.creative_ref_files = paths
                st.success(f"✅ {len(paths)} 个参考文件已上传")

        # 3. 风格参考上传
        with col_style:
            st.markdown("**🎨 风格参考**")
            st.caption("AI 尽量参考这里的画面风格")
            style_files = st.file_uploader(
                "上传风格图", type=["png", "jpg", "jpeg"],
                accept_multiple_files=True,
                key="style_ref", label_visibility="collapsed"
            )
            if style_files:
                style_dir = Path(__file__).parent / "data" / "uploads" / "style_refs"
                style_dir.mkdir(parents=True, exist_ok=True)
                paths = []
                for f in style_files:
                    fp = style_dir / f.name
                    with open(fp, "wb") as out:
                        out.write(f.getbuffer())
                    paths.append(str(fp))
                st.session_state.style_ref_files = paths
                st.success(f"✅ {len(paths)} 个风格参考文件已上传")

        # 显示当前已上传状态
        if st.session_state.get("logo_file") or st.session_state.get("creative_ref_files") or st.session_state.get("style_ref_files"):
            st.divider()
            st.caption("📌 已上传素材：")
            if st.session_state.get("logo_file"):
                st.caption(f"  🏢 Logo: {st.session_state.logo_file_name}")
            if st.session_state.get("creative_ref_files"):
                st.caption(f"  💡 创意参考: {len(st.session_state.creative_ref_files)} 个文件")
            if st.session_state.get("style_ref_files"):
                st.caption(f"  🎨 风格参考: {len(st.session_state.style_ref_files)} 个文件")

    # ─── 显示对话历史（类似豆包 / ChatGPT） ───
    chat_container = st.container()
    with chat_container:
        if not st.session_state.chat_messages:
            # 空状态引导
            st.info("💡 在下方输入你的创意想法，比如：\n\n"
                    "> 「我想突出 DF10 的防偷拍检测功能，用'出差住酒店安全检测'这个场景」\n\n"
                    "AI 会自动根据你选择的营销方向和输出形式生成内容。")

        else:
            for msg in st.session_state.chat_messages:
                with st.chat_message(msg["role"]):
                    if msg["role"] == "user":
                        st.markdown(msg["content"])
                    else:
                        result = msg.get("result", {})
                        # 文案始终显示（所有模式都生成）
                        if result.get("copy"):
                            st.markdown("**📝 朋友圈文案**")
                            st.markdown(f"""<div style="background:#f0f8ff;padding:16px;border-radius:10px;border:1px solid #b0d4f1;"><pre style="white-space:pre-wrap;font-family:inherit;margin:0;">{result['copy']}</pre></div>""", unsafe_allow_html=True)
                            st.button("📋 复制", key=f"cpy_{msg['id']}")
                        if result.get("script"):
                            st.markdown("**🎬 视频分镜脚本**")
                            st.markdown(f"""<div style="background:#f8f9fa;padding:16px;border-radius:10px;border:1px solid #e0e0e0;"><pre style="white-space:pre-wrap;font-family:inherit;margin:0;">{result['script']}</pre></div>""", unsafe_allow_html=True)
                        if result.get("video_copy"):
                            st.markdown("**🎬 短视频配文**")
                            with st.container(border=True):
                                st.markdown(result["video_copy"])
                        if result.get("images"):
                            st.markdown("**🖼️ 配图**")
                            for i, img_path in enumerate(result["images"]):
                                if img_path and Path(img_path).exists():
                                    cap = ""
                                    if result.get("image_prompts") and i < len(result["image_prompts"]):
                                        cap = result["image_prompts"][i]
                                    st.image(img_path, caption=cap, width=350)
                                elif result.get("image_prompts") and i < len(result["image_prompts"]):
                                    st.info(f"🖼️ {result['image_prompts'][i]}")
                        if result.get("video_path"):
                            st.markdown("**🎬 短视频**")
                            vp = result["video_path"]
                            if Path(vp).exists():
                                st.success("✅ 视频已生成 [待审核通过后可下载]")
                            else:
                                st.info("🎬 视频生成中...")
                        
                        # 该条消息的提交/继续按钮
                        if msg.get("can_submit") and not msg.get("submitted"):
                            c1, c2 = st.columns([1, 1])
                            with c1:
                                if st.button("✋ 满意了，提交审核", type="primary", use_container_width=True,
                                             key=f"submit_{msg['id']}"):
                                    _submit_content(product, msg.get("direction") or directions[0],
                                                     msg["content"], result)
                                    msg["submitted"] = True
                                    st.rerun()
                            with c2:
                                if st.button("🔄 继续修改", use_container_width=True,
                                             key=f"regen_{msg['id']}"):
                                    st.session_state._revise_idea = msg["content"]
                                    st.session_state._revise_result_id = msg["id"]
                                    st.rerun()

    # ─── 底部固定输入栏（类似豆包） ───
    st.markdown("---")
    bottom_col1, bottom_col2, bottom_col3 = st.columns([3, 1, 1])

    # ─── 方向选择 + 一键生成提示词按钮 ───
    dir_options = {d["name"]: {**d} for d in directions}
    dir_names = list(dir_options.keys())

    # 在方向选择右侧放一个按钮
    dir_col1, dir_col2 = st.columns([3, 1])
    with dir_col1:
        sel_dir_name = st.selectbox("方向", dir_names, index=0, label_visibility="collapsed", key="chat_dir")
        current_direction = dir_options[sel_dir_name]
        hint = current_direction.get("prompt_hint", "")
        if sel_dir_name == "其他":
            custom_hint = st.text_input("自定义方向描述", placeholder="例如：新品发布会倒计时预热", key="custom_dir_hint")
            if custom_hint:
                current_direction = {
                    "id": "custom",
                    "name": f"其他 - {custom_hint}",
                    "prompt_hint": custom_hint,
                }
                st.caption(f"💡 {custom_hint}")
        elif hint:
            st.caption(f"💡 {hint}")

    with dir_col2:
        st.caption("&nbsp;")  # 对齐
        if st.button("✨ 一键生成提示词", use_container_width=True, key="gen_prompt"):
            # 用当前方向和 hint 生成提示词填入输入框
            hint_text = current_direction.get("prompt_hint", "")
            dir_name = sel_dir_name
            if sel_dir_name == "其他":
                custom = st.session_state.get("custom_dir_hint", "")
                hint_text = custom or dir_name
                if custom:
                    dir_name = f"其他 - {custom}"
            gen_text = f"【方向：{dir_name}】"
            if hint_text:
                gen_text += f" {hint_text}"
            gen_text += " 请根据这一方向生成对应的营销内容。"
            st.session_state.chat_input_override = gen_text
            st.rerun()

    # 读取可能被一键生成的提示词覆盖
    if "chat_input_override" in st.session_state and st.session_state.chat_input_override:
        input_default = st.session_state.chat_input_override
    else:
        input_default = st.session_state.get("_revise_idea", "")

    with bottom_col1:
        user_input = st.text_input(
            "💬 描述你的创意",
            placeholder="例如：突出防偷拍检测，酒店出差场景…",
            label_visibility="collapsed",
            key="chat_input",
            value=input_default,
        )

    # 覆盖使用后清除
    if "chat_input_override" in st.session_state and not user_input:
        pass

    with bottom_col2:
        pass  # 方向已在上方

    with bottom_col3:
        # 输出形式：单选，文案始终附带
        sel_type = st.radio(
            "输出形式", all_output_types,
            index=0, horizontal=True,
            label_visibility="collapsed",
            key="chat_output_type",
        )

    # 发送按钮
    send_col1, send_col2 = st.columns([3, 1])
    with send_col1:
        pass
    with send_col2:
        send_clicked = st.button("🚀 发送", type="primary", use_container_width=True)

    # ─── 处理发送 ───
    if send_clicked and user_input.strip():
        # 清除覆盖
        st.session_state.chat_input_override = ""
        # 清除输入框中的修改草稿
        st.session_state._revise_idea = ""

        # 构建上下文（最近 N 轮的历史）
        history_context = ""
        recent = st.session_state.chat_messages[-6:]
        for m in recent:
            role = "用户" if m["role"] == "user" else "AI"
            if m["role"] == "user":
                history_context += f"[用户] {m['content']}\n"
            else:
                summary = m.get("result", {}).get("copy", "")[:100]
                history_context += f"[AI] {summary}\n"

        # 收集知识库素材
        prod_links = get_links(product.get("id"))
        prod_materials = get_materials(product.get("id"))
        matched = list(prod_links.values()) + list(prod_materials.values())
        materials_context = ""
        if matched:
            names = [m.get("name", m.get("title", "")) for m in matched[:3]]
            materials_context = "、".join(n for n in names if n)

        # 添加用户消息
        user_msg_id = f"u_{int(time.time())}"
        st.session_state.chat_messages.append({
            "role": "user",
            "id": user_msg_id,
            "content": user_input.strip(),
        })

        # 生成内容
        with st.spinner("🤔 AI 正在思考中..."):
            result = {}
            try:
                # 文案始终生成（所有模式）
                result["copy"] = generate_copy(
                    product, current_direction,
                    user_input.strip(), materials_context, history_context,
                )
                if sel_type == "短视频" or sel_type == "脚本":
                    result["script"] = generate_video_script(
                        product, current_direction,
                        user_input.strip(), materials_context, history_context,
                    )
                if sel_type == "短视频":
                    result["video_copy"] = result.get("copy", "")
                if sel_type == "文案+配图":
                    logo_path = st.session_state.get("logo_file")
                    creative_refs = st.session_state.get("creative_ref_files", [])
                    style_refs = st.session_state.get("style_ref_files", [])

                    ref_context = ""
                    if creative_refs:
                        ref_context += f"\n【创意参考素材已提供，请参考其创意方向】共计{len(creative_refs)}个文件"
                    if style_refs:
                        ref_context += f"\n【风格参考素材已提供，请参考其画面风格】共计{len(style_refs)}个文件"
                    if logo_path:
                        ref_context += "\n【Logo已上传，生成后叠加角标】"

                    images, prompts = generate_images(
                        product, user_input.strip() + ref_context,
                        result.get("copy", ""), count=1,
                        logo_path=logo_path,
                        creative_refs=creative_refs,
                        style_refs=style_refs,
                    )
                    result["images"] = images
                    result["image_prompts"] = prompts
                if sel_type == "短视频":
                    video_prompt = f"{user_input.strip()}\n产品: {product.get('name', '')} 营销推广视频，竖屏"
                    result["video_path"] = generate_video(product, user_input.strip(), prompt=video_prompt)
            except Exception as e:
                result["error"] = str(e)

        # 添加 AI 回复
        assistant_msg_id = f"a_{int(time.time())}"
        st.session_state.chat_messages.append({
            "role": "assistant",
            "id": assistant_msg_id,
            "content": f"已根据你的创意「{user_input.strip()[:40]}…」生成内容 👇",
            "result": result,
            "direction": current_direction,
            "can_submit": True,
            "submitted": False,
        })

        st.rerun()

    # 清除一键生成的覆盖（防止 sticky）
    if "chat_input_override" in st.session_state and st.session_state.chat_input_override:
        st.session_state.chat_input_override = ""

# ═══════════════════════════════════════════════════════════════
# 审核端页面
# ═══════════════════════════════════════════════════════════════
def render_admin_page(config):
    st.title("🔍 内容审核中心")
    st.caption("审核合作伙伴提交的营销内容，支持填写修改意见，通过后伙伴才能下载")

    tab1, tab2, tab3 = st.tabs(["📋 待审核", "✅ 已通过", "📦 全部记录"])

    with tab1:
        pending = get_pending_contents()
        if not pending:
            st.info("暂无待审核内容 🎉")
        else:
            for item in pending:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**{item['product_name']}** | {item['direction_name']}")
                        st.caption(f"来自：{item['partner']} · {item['created_at']}")
                    with col2:
                        if st.button("审核", key=f"rv_{item['id']}"):
                            st.session_state["_reviewing"] = item["id"]
                            st.rerun()

                    if st.session_state.get("_reviewing") == item["id"]:
                        st.divider()
                        st.markdown("**伙伴创意：**")
                        st.info(item["idea"])
                        if item.get("copy"):
                            st.markdown("**朋友圈文案：**")
                            st.code(item["copy"])
                        if item.get("video_script"):
                            st.markdown("**短视频配文：**")
                            st.code(item["video_script"])
                        if item.get("script"):
                            with st.expander("📋 查看视频分镜脚本"):
                                st.markdown(item["script"])
                        # 审核意见输入
                        st.divider()
                        st.markdown("**📝 审核意见**")
                        review_comment = st.text_area(
                            "修改意见（退回时必填）",
                            placeholder="例如：请增加防偷拍功能的具体参数说明…",
                            key=f"review_comment_{item['id']}",
                        )
                        st.caption("填写后，伙伴端可查看到审核意见。通过时意见可选，退回时意见会传给伙伴参考修改。")
                        st.divider()
                        col_a, col_b, _ = st.columns([1, 1, 2])
                        with col_a:
                            if st.button("✅ 通过", type="primary",
                                         key=f"pass_{item['id']}"):
                                approve_content(item["id"], review_comment)
                                st.session_state.pop("_reviewing", None)
                                st.rerun()
                        with col_b:
                            if st.button("❌ 退回", key=f"rej_{item['id']}"):
                                reject_content(item["id"], review_comment)
                                st.session_state.pop("_reviewing", None)
                                st.rerun()
                            if st.button("❌ 退回", key=f"rej_{item['id']}"):
                                item["status"] = "已退回"
                                st.rerun()

    with tab2:
        approved = get_approved_contents()
        if not approved:
            st.info("暂无已通过的内容")
        else:
            for item in approved:
                st.success(f"✅ {item['product_name']} - {item['direction_name']} ({item['created_at']})")
                if item.get("review_comment"):
                    st.caption(f"审核备注：{item['review_comment']}")

    with tab3:
        all_records = get_all_contents()
        if not all_records:
            st.info("暂无记录")
        else:
            icons = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
            for item in all_records:
                ic = icons.get(item["status"], "📌")
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.text(f"{ic} {item['product_name']} | {item['direction_name']} "
                                f"| {item['status']} | {item['created_at']}")
                        if item.get("review_comment"):
                            st.caption(f"修改意见：{item['review_comment']}")
                    with col2:
                        if item["status"] == "approved":
                            videos = get_videos_for_content(item["id"])
                            for v in videos:
                                if Path(v["filepath"]).exists():
                                    with open(v["filepath"], "rb") as f:
                                        st.download_button(
                                            "📥 下载视频", f,
                                            file_name=v["filename"],
                                            use_container_width=True
                                        )


def _render_link_list():
    """渲染链接列表（被管理端页面调用）"""
    all_links = get_links()
    if not all_links:
        st.info("暂无物料链接，请在顶部添加")
        return

    filter_status = st.selectbox(
        "按状态筛选",
        ["全部", "待抓取", "已抓取", "已下载", "失效"],
        key="link_filter_main"
    )
    for lid, link in all_links.items():
        if filter_status != "全部" and link["status"] != filter_status:
            continue
        sicons = {"待抓取": "⏳", "已抓取": "📋", "已下载": "✅", "失效": "❌"}
        icon = sicons.get(link["status"], "❓")
        with st.container(border=True):
            cols = st.columns([4, 1, 1, 1])
            with cols[0]:
                st.markdown(f"**{link['title']}**")
                st.caption(f"{icon} {link['status']} | 标签：{'·'.join(link.get('tags', []))}")
            with cols[1]:
                st.link_button("🔗 打开", link["url"], use_container_width=True)
            with cols[2]:
                st.button("🔄 抓取", key=f"fetch_{lid}", use_container_width=True,
                          help="自动下载功能开发中，当前可手动下载后上传")
            with cols[3]:
                if st.button("🗑️ 删除", key=f"del_{lid}", use_container_width=True):
                    delete_link(lid)
                    st.rerun()


# ═══════════════════════════════════════════════════════════════
# 管理端页面
# ═══════════════════════════════════════════════════════════════
def _submit_content(product, direction, idea, result):
    """提交内容到数据库"""
    content_id = submit_content(
        product=product,
        direction=direction,
        idea=idea,
        copy=result.get("copy", ""),
        script=result.get("script", ""),
        video_script=result.get("video_copy", ""),
        image_prompts=result.get("image_prompts", []),
        image_paths=[p for p in result.get("images", []) if p],
    )
    vp = result.get("video_path")
    if vp and Path(vp).exists():
        save_video(content_id, vp)
    st.session_state["_last_content_id"] = content_id
    st.balloons()





def render_management_page(config):
    """知识库管理 — 品牌规则全局，物料按产品管理，必选物料直设"""
    st.title("⚙️ 知识库管理")

    # ═══ Tab 1: 物料管理（按产品筛选） ═══
    # ═══ Tab 2: 品牌规则（全局，不绑定产品） ═══
    tab1, tab2 = st.tabs(["📦 物料管理", "⚙️ 品牌规则（全局）"])

    # ══════════════════════════════════════════════════════════
    # Tab 1: 物料管理 — 按产品筛选
    # ══════════════════════════════════════════════════════════
    with tab1:
        prod_map = {p["name"]: p for p in config.get("products", [])}
        sel_name = st.selectbox("选择要管理的产品", list(prod_map.keys()), key="mgmt_prod")
        product = prod_map[sel_name]
        pid = product["id"]

        st.markdown(f"### {product['name']} — 知识库物料")
        st.caption("新增物料自动归属当前产品")

        # ── 必选物料（产品图片 + 产品模型） ──
        st.markdown("#### ⭐ 必选物料")
        st.caption("每个产品必须提供以下物料，AI 生成内容时会优先使用")

        # 查找已上传的必选物料
        all_mats = get_materials(pid)
        all_links = get_links(pid)

        def has_required(tag_keyword):
            for m in all_mats.values():
                if tag_keyword in " ".join(m.get("tags", [])):
                    return m.get("name", "")
            for l in all_links.values():
                if tag_keyword in " ".join(l.get("tags", [])):
                    return l.get("title", "")
            return None

        req_img = has_required("产品图片")
        req_model = has_required("产品模型")

        req_c1, req_c2 = st.columns(2)

        with req_c1:
            st.markdown("**🖼️ 产品图片（必选）**")
            if req_img:
                st.success(f"✅ 已上传：{req_img}")
                if st.button("🗑️ 清除", key="clear_req_img", use_container_width=True):
                    _remove_by_tag(pid, "产品图片")
                    st.rerun()
            else:
                st.warning("⚠️ 尚未上传")
                # 快捷上传
                ri = st.file_uploader("上传产品图片", type=["png", "jpg", "jpeg"],
                                       key="req_img_upload", label_visibility="collapsed")
                if ri is not None:
                    save_dir = Path(__file__).parent / "data" / "materials" / pid
                    save_dir.mkdir(parents=True, exist_ok=True)
                    fp = save_dir / ri.name
                    with open(fp, "wb") as f:
                        f.write(ri.getbuffer())
                    add_material(str(fp), pid, ri.name, ["产品图片", "必选"])
                    st.success("✅ 必选产品图片已上传！")
                    st.rerun()

        with req_c2:
            st.markdown("**🏗️ 产品模型（必选）**")
            if req_model:
                st.success(f"✅ 已上传：{req_model}")
                if st.button("🗑️ 清除", key="clear_req_model", use_container_width=True):
                    _remove_by_tag(pid, "产品模型")
                    st.rerun()
            else:
                st.warning("⚠️ 尚未上传")
                rm = st.file_uploader("上传产品模型", type=["png", "jpg", "jpeg", "pdf", "pptx", "obj", "stl", "glb"],
                                       key="req_model_upload", label_visibility="collapsed")
                if rm is not None:
                    save_dir = Path(__file__).parent / "data" / "materials" / pid
                    save_dir.mkdir(parents=True, exist_ok=True)
                    fp = save_dir / rm.name
                    with open(fp, "wb") as f:
                        f.write(rm.getbuffer())
                    add_material(str(fp), pid, rm.name, ["产品模型", "必选"])
                    st.success("✅ 必选产品模型已上传！")
                    st.rerun()

        st.divider()

        # ── 常规物料（链接 + 文件 合一） ──
        st.markdown("#### ➕ 新增常规物料")

        ticons = {"文档": "📄", "PPT": "📊", "图片": "🖼️", "视频": "🎬", "表格": "📋", "其他": "📁"}
        sicons = {"待抓取": "⏳", "已抓取": "📋", "已下载": "✅", "失效": "❌"}

        input_mode = st.radio("输入方式", ["🔗 链接", "📁 文件上传"], horizontal=True, key="mm_input_mode")

        if input_mode == "🔗 链接":
            url = st.text_input("物料链接", placeholder="https://partner.huawei.com/...", key="mm_link_url")
            link_title = st.text_input("物料标题（可选）", placeholder="留空自动提取", key="mm_link_title")
            link_tags = st.text_input("标签（逗号分隔）", placeholder="产品, 卖点, 资料", key="mm_link_tags")
            if st.button("✅ 添加链接", type="primary", use_container_width=True, key="mm_add_link"):
                if url.strip():
                    tags = [t.strip() for t in link_tags.split(",") if t.strip()]
                    add_link(url.strip(), pid, title=link_title.strip(), tags=tags)
                    st.success("✅ 链接已添加")
                    st.rerun()
                else:
                    st.warning("请输入链接地址")
        else:
            up_name = st.text_input("物料名称", placeholder="例如：DF10产品彩页_v3", key="mm_file_name")
            up_tags = st.text_input("标签（逗号分隔）", placeholder="产品, 卖点, 高清图", key="mm_file_tags")
            uploaded_file = st.file_uploader(
                "选择文件（PDF/PPTX/PNG/JPG/MP4 等）",
                type=["pdf", "pptx", "ppt", "docx", "png", "jpg", "jpeg", "mp4"],
                key="mm_file_upload"
            )
            if uploaded_file and up_name.strip():
                save_dir = Path(__file__).parent / "data" / "materials" / pid
                save_dir.mkdir(parents=True, exist_ok=True)
                fp = save_dir / uploaded_file.name
                with open(fp, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                tags = [t.strip() for t in up_tags.split(",") if t.strip()]
                add_material(str(fp), pid, up_name.strip(), tags)
                st.success(f"✅ 物料「{up_name.strip()}」上传成功！")
                st.rerun()

        st.divider()
        st.markdown("#### 📋 当前物料清单")

        all_items = []
        # 文件
        for m in all_mats.values():
            icon = ticons.get(m.get("type", ""), "📁")
            tag_str = " · ".join(m.get("tags", []))
            is_req = "必选" in m.get("tags", [])
            all_items.append({
                "icon": icon,
                "name": m.get("name", "未命名"),
                "detail": f"类型：{m.get('type', '')} | 大小：{m.get('size', 0)/1024:.0f}KB" + (f" | {tag_str}" if tag_str else ""),
                "must": is_req,
                "sort": 0 if is_req else 1,
            })
        # 链接
        for l in all_links.values():
            icon = sicons.get(l.get("status", ""), "🔗")
            tag_str = " · ".join(l.get("tags", []))
            is_req = "必选" in l.get("tags", [])
            all_items.append({
                "icon": icon,
                "name": l.get("title", "未命名"),
                "detail": f"状态：{l.get('status', '')}" + (f" | {tag_str}" if tag_str else ""),
                "must": is_req,
                "sort": 0 if is_req else 1,
                "link_id": l.get("id"),
            })

        all_items.sort(key=lambda x: (x["sort"], x["name"]))

        if all_items:
            for item in all_items:
                must_tag = "⭐ **必选** " if item["must"] else ""
                with st.container(border=True):
                    cols = st.columns([0.05, 0.6, 0.25, 0.1])
                    with cols[0]:
                        st.markdown(item["icon"])
                    with cols[1]:
                        st.markdown(f"{must_tag}**{item['name']}**")
                        st.caption(item["detail"])
                    with cols[2]:
                        pass
                    with cols[3]:
                        if item.get("link_id"):
                            if st.button("🗑️", key=f"d_mm_{item['link_id']}", use_container_width=True):
                                delete_link(item["link_id"])
                                st.rerun()
        else:
            st.info("暂无物料，请通过上方表单添加")

        # 物料统计
        st.divider()
        st.caption(f"📊 合计：{len(all_links)} 个链接 · {len(all_mats)} 个文件 · "
                   f"必选物料 {(1 if req_img else 0) + (1 if req_model else 0)}/2")

    # ══════════════════════════════════════════════════════════
    # Tab 2: 品牌规则 — 全局，不绑定产品
    # ══════════════════════════════════════════════════════════
    with tab2:
        st.markdown("### 品牌内容规则（全局生效）")
        st.caption("手动输入品牌规则，每条一行，AI 生成内容时会自动遵守")

        # 读取已有规则（展示为用户可编辑的文本）
        forbidden = config.get("rules", {}).get("forbidden_words", [])
        required = config.get("rules", {}).get("required_words", [])
        brand_phrases = config.get("rules", {}).get("brand_phrases", [])

        all_rules = []
        for w in forbidden:
            all_rules.append(f"❌ 禁用: {w}")
        for w in required:
            all_rules.append(f"✅ 必含: {w}")
        for w in brand_phrases:
            all_rules.append(f"📢 话术: {w}")

        rules_text = st.text_area(
            "品牌规则（每行一条）",
            value="\n".join(all_rules),
            placeholder="""❌ 禁用: 最
❌ 禁用: 第一
✅ 必含: 华为坤灵
📢 话术: 华为坤灵 %s
这样每行一条，用前缀区分类型""",
            height=250,
            key="brand_rules_text"
        )

        if st.button("💾 保存规则", type="primary", use_container_width=True, key="save_rules"):
            import yaml
            cfg_path = Path(__file__).parent / "config.yaml"
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)

            new_forbidden = []
            new_required = []
            new_phrases = []
            for line in rules_text.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                if "❌ 禁用:" in line or "禁用:" in line:
                    word = line.split(":", 1)[1].strip()
                    if word:
                        new_forbidden.append(word)
                elif "✅ 必含:" in line or "必含:" in line:
                    word = line.split(":", 1)[1].strip()
                    if word:
                        new_required.append(word)
                elif "📢 话术:" in line or "话术:" in line:
                    phrase = line.split(":", 1)[1].strip()
                    if phrase:
                        new_phrases.append(phrase)

            cfg["rules"]["forbidden_words"] = new_forbidden
            cfg["rules"]["required_words"] = new_required
            cfg["rules"]["brand_phrases"] = new_phrases

            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, allow_unicode=True, indent=2, sort_keys=False)
            st.success("✅ 品牌规则已保存")
            st.rerun()


def _remove_by_tag(product_id, tag_keyword):
    """按标签删除物料和链接"""
    # 删除物料文件
    mats = get_materials(product_id)
    for mid, m in mats.items():
        if tag_keyword in " ".join(m.get("tags", [])):
            fp = m.get("file_path", "")
            if fp and Path(fp).exists():
                Path(fp).unlink(missing_ok=True)
    # 从索引中移除（重新写入，跳过匹配项）
    from modules.knowledge_base import INDEX_FILE
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            idx = json.load(f)
        idx = {k: v for k, v in idx.items()
               if not (v.get("product_id") == product_id and tag_keyword in " ".join(v.get("tags", [])))}
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=2)
    # 删除链接
    links = get_links(product_id)
    for lid, l in links.items():
        if tag_keyword in " ".join(l.get("tags", [])):
            delete_link(lid)

# ═══════════════════════════════════════════════════════════════
# 侧边栏 + 页面路由
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:20px 0;">
        <h1 style="font-size:28px;margin:0;">📱</h1>
        <h2 style="font-size:16px;margin:5px 0 0;color:#cf0a2c;">
            华为伙伴营销<br>内容协作平台</h2>
        <p style="font-size:11px;color:#888;">v0.1 Demo</p>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    role = st.radio("选择身份",
                    ["🤝 伙伴端 - 创意生成",
                     "🔍 审核端 - 内容审核",
                     "⚙️ 管理端 - 知识库"],
                    key="role")

    st.divider()
    st.caption("当前产品模块")
    product_options = {p["name"]: p for p in products}
    sel_name = st.selectbox("选择产品", list(product_options.keys()), index=0)
    selected_product = product_options[sel_name]

# ─── 页面路由 ─────────────────────────────────────────────────
if "审核" in role:
    render_admin_page(config)
elif "管理" in role:
    render_management_page(config)
else:
    render_partner_page(selected_product, config)

st.divider()
st.caption("华为伙伴营销内容协作平台 · 仅供合作伙伴使用")
