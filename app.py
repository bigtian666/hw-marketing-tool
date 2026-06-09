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

    with bottom_col1:
        user_input = st.text_input(
            "💬 描述你的创意",
            placeholder="例如：突出防偷拍检测，酒店出差场景…",
            label_visibility="collapsed",
            key="chat_input",
            value=st.session_state.get("_revise_idea", ""),
        )

    with bottom_col2:
        # 方向下拉
        dir_options = {d["name"]: d for d in directions}
        dir_names = list(dir_options.keys())
        default_dir = dir_names[0] if dir_names else "自定义"
        sel_dir_name = st.selectbox("方向", dir_names, label_visibility="collapsed", key="chat_dir")
        current_direction = dir_options[sel_dir_name]

    with bottom_col3:
        # 输出形式多选下拉
        sel_types = st.multiselect(
            "输出", all_output_types,
            default=["文案+配图"],
            label_visibility="collapsed",
            key="chat_output_types",
        )

    # 发送按钮
    send_clicked = st.button("🚀 发送", type="primary", use_container_width=True)

    # ─── 处理发送 ───
    if send_clicked and user_input.strip() and sel_types:
        # 清除输入框中的修改草稿
        st.session_state._revise_idea = ""

        # 构建上下文（最近 N 轮的历史）
        history_context = ""
        recent = st.session_state.chat_messages[-6:]  # 最近3轮对话
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
                if "文案+配图" in sel_types or "脚本" in sel_types:
                    result["copy"] = generate_copy(
                        product, current_direction,
                        user_input.strip(), materials_context, history_context,
                    )
                if "脚本" in sel_types or "短视频" in sel_types:
                    result["script"] = generate_video_script(
                        product, current_direction,
                        user_input.strip(), materials_context, history_context,
                    )
                if "短视频" in sel_types and "文案+配图" not in sel_types:
                    result["video_copy"] = generate_copy(
                        product, current_direction,
                        user_input.strip(), materials_context, history_context,
                    )
                elif "短视频" in sel_types:
                    result["video_copy"] = result.get("copy", "")
                if "文案+配图" in sel_types:
                    images, prompts = generate_images(
                        product, user_input.strip(), result.get("copy", ""), count=1
                    )
                    result["images"] = images
                    result["image_prompts"] = prompts
                if "短视频" in sel_types:
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

    # ─── 提交辅助函数（已内联到按钮中） ───

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
    """知识库管理 — 精简版：每个产品独立子库，上传链接+文件合一，品牌规则可编辑"""
    st.title("⚙️ 知识库管理")
    st.caption("每个产品拥有独立的知识子库，管理品牌规则和必选物料")

    prod_map = {p["name"]: p for p in config.get("products", [])}
    sel_name = st.selectbox("选择要管理的产品", list(prod_map.keys()), key="mgmt_prod")
    product = prod_map[sel_name]
    pid = product["id"]

    # 两个主标签页
    tab1, tab2 = st.tabs(["📦 物料管理", "⚙️ 品牌规则"])

    # ═══ Tab 1: 物料管理（上传链接 + 上传文件 合一） ═══
    with tab1:
        st.markdown(f"### {product['name']} — 知识库物料")
        st.caption("新增物料时自动归属于当前产品")

        # 必选物料提示
        ticons = {"文档": "📄", "PPT": "📊", "图片": "🖼️", "视频": "🎬", "表格": "📋", "其他": "📁"}
        sicons = {"待抓取": "⏳", "已抓取": "📋", "已下载": "✅", "失效": "❌"}

        # 现有的物料概览
        links = get_links(pid)
        materials = get_materials(pid)

        col_sum1, col_sum2, col_sum3 = st.columns(3)
        with col_sum1:
            st.metric("📎 物料链接", len(links))
        with col_sum2:
            st.metric("📁 本地文件", len(materials))
        with col_sum3:
            st.metric("📌 必选物料", sum(1 for m in materials.values() if "必选" in m.get("tags", [])))

        st.divider()
        st.markdown("#### ➕ 新增物料")

        # 合一表单：链接 或 文件
        input_mode = st.radio("输入方式", ["🔗 链接", "📁 文件上传"], horizontal=True, key="input_mode")

        if input_mode == "🔗 链接":
            url = st.text_input("物料链接", placeholder="https://partner.huawei.com/eplus/marketing/...", key="new_link_url")
            link_title = st.text_input("物料标题（可选）", placeholder="留空自动从URL提取", key="new_link_title")
            link_tags = st.text_input("标签（逗号分隔）", placeholder="产品, 卖点, 资料", key="new_link_tags")
            must_have = st.checkbox("标记为必选物料", key="link_must")
            if st.button("✅ 添加链接", type="primary", use_container_width=True, key="add_link_btn"):
                if url.strip():
                    tags = [t.strip() for t in link_tags.split(",") if t.strip()]
                    if must_have:
                        tags.append("必选")
                    add_link(url.strip(), pid, title=link_title.strip(), tags=tags)
                    st.success("✅ 链接已添加，系统将在后台自动处理")
                    st.rerun()
                else:
                    st.warning("请输入链接地址")

        else:
            up_name = st.text_input("物料名称", placeholder="例如：DF10产品彩页_v3", key="up_file_name")
            up_tags = st.text_input("标签（逗号分隔）", placeholder="产品, 卖点, 高清图", key="up_file_tags")
            must_have_file = st.checkbox("标记为必选物料", key="file_must")
            uploaded_file = st.file_uploader(
                "选择文件（PDF/PPTX/PNG/JPG/MP4 等）",
                type=["pdf", "pptx", "ppt", "docx", "png", "jpg", "jpeg", "mp4"],
                key="mgmt_upload"
            )
            if uploaded_file and up_name.strip():
                save_dir = Path(__file__).parent / "data" / "materials" / pid
                save_dir.mkdir(parents=True, exist_ok=True)
                fp = save_dir / uploaded_file.name
                with open(fp, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                tags = [t.strip() for t in up_tags.split(",") if t.strip()]
                if must_have_file:
                    tags.append("必选")
                add_material(str(fp), pid, up_name.strip(), tags)
                st.success(f"✅ 物料「{up_name.strip()}」上传成功！")
                st.balloons()
                st.rerun()

        st.divider()
        st.markdown("#### 📋 当前物料列表")

        # 合并显示链接和文件
        all_items = []

        # 排序：必选 > 其他
        def sort_key(item):
            tags = item.get("tags", [])
            return (0 if "必选" in tags else 1, item.get("name", item.get("title", "")))

        for m in materials.values():
            icon = ticons.get(m.get("type", ""), "📁")
            tag_str = " · ".join(m.get("tags", []))
            must_badge = "⭐ " if "必选" in m.get("tags", []) else ""
            all_items.append({
                "icon": icon,
                "name": m.get("name", "未命名"),
                "detail": f"类型：{m.get('type', '')} | 大小：{m.get('size', 0)/1024:.0f}KB" + (f" | 标签：{tag_str}" if tag_str else ""),
                "must": "必选" in m.get("tags", []),
                "type": "file",
            })

        for l in links.values():
            icon = sicons.get(l.get("status", ""), "🔗")
            tag_str = " · ".join(l.get("tags", []))
            must_badge = "⭐ " if "必选" in l.get("tags", []) else ""
            all_items.append({
                "icon": icon,
                "name": l.get("title", "未命名"),
                "detail": f"状态：{l.get('status', '')}" + (f" | 标签：{tag_str}" if tag_str else ""),
                "must": "必选" in l.get("tags", []),
                "type": "link",
                "link_id": l.get("id"),
            })

        all_items.sort(key=lambda x: (0 if x["must"] else 1, x["name"]))

        if all_items:
            for item in all_items:
                must_tag = "⭐ **必选** " if item["must"] else ""
                with st.container(border=True):
                    cols = st.columns([0.05, 0.65, 0.2, 0.1])
                    with cols[0]:
                        st.markdown(item["icon"])
                    with cols[1]:
                        st.markdown(f"{must_tag}**{item['name']}**")
                        st.caption(item["detail"])
                    with cols[2]:
                        if item.get("link_id"):
                            if st.button("🗑️ 删除", key=f"del_link_{item['link_id']}", use_container_width=True):
                                delete_link(item["link_id"])
                                st.rerun()
        else:
            st.info("暂无物料，请通过上方表单添加链接或上传文件")

    # ═══ Tab 2: 品牌规则 ═══
    with tab2:
        st.markdown("### 品牌内容规则")
        st.caption("手动添加一条一条的语言规则，AI 生成内容时会自动遵守")

        # 显示已有规则
        forbidden = config.get("rules", {}).get("forbidden_words", [])
        required = config.get("rules", {}).get("required_words", [])
        brand_phrases = config.get("rules", {}).get("brand_phrases", [])

        # 规则列表
        rule_col1, rule_col2 = st.columns(2)
        with rule_col1:
            st.markdown("**❌ 禁止使用词**")
            if forbidden:
                for w in forbidden:
                    st.markdown(f"- ~~{w}~~ (禁用)")
            else:
                st.caption("暂无")

        with rule_col2:
            st.markdown("**✅ 必须包含词**")
            if required:
                for w in required:
                    st.markdown(f"- **{w}** (必含)")
            else:
                st.caption("暂无")

        st.divider()

        # 手动添加规则
        st.markdown("#### ➕ 添加新规则")
        rule_type = st.selectbox("规则类型", ["禁止词（禁用）", "必含词（必须出现）", "品牌话术"], key="rule_type")
        rule_text = st.text_input("规则内容", placeholder="例如：最、第一、行业领先…", key="rule_text")

        if st.button("✅ 添加规则", type="primary", use_container_width=True, key="add_rule"):
            if rule_text.strip():
                new_word = rule_text.strip()
                from modules.knowledge_base import load_config
                import yaml
                cfg_path = Path(__file__).parent / "config.yaml"
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)

                if "禁止" in rule_type:
                    if new_word not in cfg["rules"]["forbidden_words"]:
                        cfg["rules"]["forbidden_words"].append(new_word)
                        st.success(f"✅ 已添加禁止词「{new_word}」")
                elif "必含" in rule_type:
                    if new_word not in cfg["rules"]["required_words"]:
                        cfg["rules"]["required_words"].append(new_word)
                        st.success(f"✅ 已添加必含词「{new_word}」")
                else:
                    if new_word not in cfg["rules"]["brand_phrases"]:
                        cfg["rules"]["brand_phrases"].append(new_word)
                        st.success(f"✅ 已添加品牌话术「{new_word}」")

                with open(cfg_path, "w", encoding="utf-8") as f:
                    yaml.dump(cfg, f, allow_unicode=True, indent=2, sort_keys=False)
                st.rerun()
            else:
                st.warning("请输入规则内容")

        st.divider()

        # 品牌信息概览
        brand = config.get("brand", {})
        st.markdown("#### ℹ️ 品牌信息")
        st.markdown(f"- **品牌名：** {brand.get('name', '')}")
        st.markdown(f"- **Slogan：** {brand.get('slogan', '')}")
        tone_str = "、".join(brand.get("tone", []))
        if tone_str:
            st.markdown(f"- **语气风格：** {tone_str}")
        st.caption("修改品牌信息需编辑 config.yaml 文件")

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
