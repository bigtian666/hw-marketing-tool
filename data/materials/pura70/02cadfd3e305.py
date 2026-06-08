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

from modules.knowledge_base import (
    get_materials, search_materials, add_material, load_config
)
from modules.content_gen import (
    generate_copy, generate_video_script, generate_images,
    generate_video, check_compliance
)

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
    "compliance_issues": [],
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
    st.title("🎬 创建你的营销内容")
    st.caption(f"当前产品：**{product['name']}**")

    # 第一步：选择营销方向
    st.markdown("### 📋 第一步：选择营销方向")
    directions = product.get("directions", [])

    cols = st.columns(len(directions))
    selected_direction = None
    for i, d in enumerate(directions):
        with cols[i]:
            icons = {
                "product_showcase": "🛍️",
                "activity": "🎉",
                "scene_story": "🎬",
                "user_case": "💬",
            }
            icon = icons.get(d["id"], "📌")
            is_selected = st.session_state.get("_sel_dir") == d["id"]
            btn_type = "primary" if is_selected else "secondary"
            if st.button(f"{icon}\n{d['name']}", use_container_width=True,
                         key=f"dir_{d['id']}", type=btn_type):
                st.session_state["_sel_dir"] = d["id"]
                st.session_state.generated_content = None
                st.session_state.generated_images = None
                st.session_state.submitted = False
                st.rerun()

    selected_direction_id = st.session_state.get("_sel_dir")
    current_direction = None
    if selected_direction_id:
        for d in directions:
            if d["id"] == selected_direction_id:
                current_direction = d
                break

    if current_direction:
        st.info(f"📌 已选方向：**{current_direction['name']}** | "
                f"支持输出：{'、'.join(current_direction['output_types'])}")

    # 第二步：伙伴输入创意
    st.markdown("### 💡 第二步：发挥你的创意")
    st.markdown("写下你的想法，越具体生成的內容越符合预期 👇")

    partner_idea = st.text_area(
        "你的创意想法",
        placeholder=(
            "例：我想突出Pura70在暗光下的表现，用'夜探老北京胡同'这个场景，\n"
            "展现夜景拍摄能力，配上'发现黑夜中的美'这个主题……"
        ),
        height=150, key="idea_input",
        value=st.session_state.partner_idea
    )
    st.session_state.partner_idea = partner_idea

    if not selected_direction_id:
        st.warning("👆 请先选择一个营销方向")
        return
    if not partner_idea.strip():
        st.warning("✍️ 请输入你的创意想法")
        return

    # 第三步：选择输出形式
    st.markdown("### 🎯 第三步：选择输出形式")
    output_types = current_direction["output_types"]
    output_cols = st.columns(len(output_types))
    selected_types = []
    for i, ot in enumerate(output_types):
        with output_cols[i]:
            icons_map = {"文案+配图": "📝", "短视频": "🎬", "脚本": "📋"}
            icon = icons_map.get(ot, "📌")
            default_val = (ot == "文案+配图")
            if st.checkbox(f"{icon} {ot}", key=f"ot_{ot}", value=default_val):
                selected_types.append(ot)

    if not selected_types:
        st.warning("请至少选择一种输出形式")
        return

    # 知识库素材预览
    st.markdown("### 📎 参考素材（系统自动匹配）")
    matched_materials = search_materials(
        current_direction.get("name", ""), product.get("id")
    )
    if matched_materials:
        type_icons = {"文档": "📄", "PPT": "📊", "图片": "🖼️",
                      "视频": "🎬", "表格": "📋", "其他": "📁"}
        for mat in matched_materials[:5]:
            icon = type_icons.get(mat["type"], "📁")
            st.caption(f"{icon} {mat['name']} ({mat['type']})")
    else:
        st.caption("ℹ️ 当前产品暂无素材入库，请联系管理员上传物料")

    # 生成按钮
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        generate_btn = st.button("🚀 生成内容", use_container_width=True, type="primary")

    if generate_btn:
        with st.spinner("正在生成内容，请稍候..."):
            materials_context = ""
            if matched_materials:
                materials_context = "、".join([m["name"] for m in matched_materials[:3]])

            result = {}
            if "文案+配图" in selected_types or "脚本" in selected_types:
                result["copy"] = generate_copy(product, current_direction,
                                                partner_idea, materials_context)
            if "脚本" in selected_types or "短视频" in selected_types:
                result["script"] = generate_video_script(
                    product, current_direction, partner_idea, materials_context)
            if "文案+配图" in selected_types:
                images, prompts = generate_images(
                    product, partner_idea, result.get("copy", ""), count=1)
                result["images"] = images
                result["image_prompts"] = prompts
            if "短视频" in selected_types:
                result["video_path"] = generate_video(
                    product, partner_idea, result.get("images", []))

            all_text = result.get("copy", "") + " " + result.get("script", "")
            st.session_state.generated_content = result
            st.session_state.compliance_issues = check_compliance(all_text, product)
            st.session_state.submitted = False
            st.rerun()

    # ─── 显示生成结果 ─────────────────────────────────
    if st.session_state.generated_content:
        result = st.session_state.generated_content
        issues = st.session_state.get("compliance_issues", [])

        st.markdown("---")
        st.markdown("## ✅ 生成结果预览")

        if issues:
            st.error("⚠️ 合规检查发现问题，请修正后重新生成：")
            for iss in issues:
                st.warning(f"- {iss}")
        else:
            st.success("✅ 内容已通过合规检查")

        if result.get("copy"):
            st.markdown("### 📝 朋友圈文案")
            st.markdown(f"""
            <div style="background:#f8f9fa;padding:20px;border-radius:10px;border:1px solid #e0e0e0;">
                <pre style="white-space:pre-wrap;font-family:inherit;margin:0;">{result['copy']}</pre>
            </div>
            """, unsafe_allow_html=True)
            if st.button("📋 复制到剪贴板", key="cpy"):
                st.toast("文案已就绪！", icon="✅")

        if result.get("script"):
            st.markdown("### 🎬 视频分镜脚本")
            st.markdown(f"""
            <div style="background:#f8f9fa;padding:20px;border-radius:10px;border:1px solid #e0e0e0;">
                <pre style="white-space:pre-wrap;font-family:inherit;margin:0;">{result['script']}</pre>
            </div>
            """, unsafe_allow_html=True)

        if result.get("images"):
            st.markdown("### 🖼️ 配图")
            for i, img in enumerate(result["images"]):
                if img and Path(img).exists():
                    cap = ""
                    if result.get("image_prompts") and i < len(result["image_prompts"]):
                        cap = result["image_prompts"][i]
                    st.image(img, caption=cap)
                elif result.get("image_prompts") and i < len(result["image_prompts"]):
                    st.info(f"🖼️ 配图创意：{result['image_prompts'][i]}")
                    st.caption("（图片生成服务连接中，正式部署后自动渲染）")

        if result.get("video_path"):
            st.markdown("### 🎬 短视频")
            vp = result["video_path"]
            if Path(vp).exists():
                with open(vp, "rb") as f:
                    st.download_button("📥 下载视频", f, file_name="marketing_video.mp4")
            else:
                st.info("🎬 视频生成中，正式部署后将直接输出可下载的 mp4")

        # 迭代修改区
        st.markdown("---")
        st.markdown("### 🔄 不满意？继续打磨！")
        st.markdown("调整上面的创意想法，重新生成即可。可以反复迭代直到满意 ✨")

        # 提交审核
        if not issues:
            st.markdown("---")
            col_a, col_b = st.columns([1, 1])
            with col_a:
                if not st.session_state.submitted:
                    if st.button("✋ 满意了，提交审核", type="primary",
                                 use_container_width=True):
                        review_item = {
                            "id": f"review_{int(time.time())}",
                            "partner": "演示伙伴",
                            "product": product["name"],
                            "direction": current_direction["name"],
                            "idea": partner_idea,
                            "content": result,
                            "status": "待审核",
                            "created_at": time.strftime("%Y-%m-%d %H:%M"),
                        }
                        st.session_state.review_queue.append(review_item)
                        st.session_state.submitted = True
                        st.rerun()
            with col_b:
                if not st.session_state.submitted:
                    if st.button("🔄 继续修改", use_container_width=True):
                        st.session_state.submitted = False
                        st.rerun()
            if st.session_state.submitted:
                st.success("🎉 **已提交审核！** 等待华为市场部审核通过后即可使用。")
                st.balloons()
        else:
            st.warning("⚠️ 请先解决合规问题后再提交审核")


# ═══════════════════════════════════════════════════════════════
# 审核端页面
# ═══════════════════════════════════════════════════════════════
def render_admin_page(config):
    st.title("🔍 内容审核中心")
    st.caption("审核合作伙伴提交的营销内容")

    queue = st.session_state.review_queue
    pending = [it for it in queue if it["status"] == "待审核"]

    tab1, tab2, tab3 = st.tabs(["📋 待审核", "✅ 已通过", "📦 全部记录"])

    with tab1:
        if not pending:
            st.info("暂无待审核内容 🎉")
        else:
            for item in pending:
                with st.container(border=True):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(f"**{item['product']}** | {item['direction']}")
                        st.caption(f"来自：{item['partner']} · {item['created_at']}")
                    with col2:
                        if st.button("审核", key=f"rv_{item['id']}"):
                            st.session_state["_reviewing"] = item["id"]
                            st.rerun()

                    if st.session_state.get("_reviewing") == item["id"]:
                        st.divider()
                        st.markdown("**伙伴创意：**")
                        st.info(item["idea"])
                        if item["content"].get("copy"):
                            st.markdown("**朋友圈文案：**")
                            st.code(item["content"]["copy"])
                        if item["content"].get("script"):
                            with st.expander("查看视频脚本"):
                                st.markdown(item["content"]["script"])
                        st.divider()
                        col_a, col_b, _ = st.columns([1, 1, 2])
                        with col_a:
                            if st.button("✅ 通过", type="primary",
                                         key=f"pass_{item['id']}"):
                                item["status"] = "已通过"
                                st.rerun()
                        with col_b:
                            if st.button("❌ 退回", key=f"rej_{item['id']}"):
                                item["status"] = "已退回"
                                st.rerun()

    with tab2:
        approved = [it for it in queue if it["status"] == "已通过"]
        if not approved:
            st.info("暂无已通过的内容")
        else:
            for item in approved:
                st.success(f"✅ {item['product']} - {item['direction']} "
                           f"({item['created_at']})")

    with tab3:
        icons = {"待审核": "⏳", "已通过": "✅", "已退回": "❌"}
        for item in queue:
            ic = icons.get(item["status"], "📌")
            st.text(f"{ic} {item['product']} | {item['direction']} "
                    f"| {item['status']} | {item['created_at']}")


# ═══════════════════════════════════════════════════════════════
# 管理端页面
# ═══════════════════════════════════════════════════════════════
def render_management_page(config):
    st.title("⚙️ 知识库管理")
    st.caption("上传和管理营销物料")

    tab1, tab2 = st.tabs(["📤 上传物料", "📚 物料列表"])

    with tab1:
        st.markdown("### 上传营销物料")
        product_options = {p["name"]: p["id"] for p in products}
        sel_product = st.selectbox("选择所属产品", list(product_options.keys()))
        mat_name = st.text_input("物料名称", placeholder="例如：Pura70产品彩页_v3")
        mat_tags = st.text_input("标签（逗号分隔）",
                                 placeholder="产品, 卖点, 高清图")

        uploaded_file = st.file_uploader(
            "选择文件（PDF/PPTX/PNG/JPG/MP4 等）",
            type=["pdf", "pptx", "ppt", "docx", "png", "jpg", "jpeg", "mp4"]
        )

        if uploaded_file and mat_name:
            product_id = product_options[sel_product]
            save_dir = Path(__file__).parent / "data" / "materials" / product_id
            save_dir.mkdir(parents=True, exist_ok=True)
            file_path = save_dir / uploaded_file.name
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            tags = [t.strip() for t in mat_tags.split(",") if t.strip()]
            add_material(str(file_path), product_id, mat_name, tags)
            st.success(f"✅ 物料「{mat_name}」上传成功！")
            st.balloons()

    with tab2:
        st.markdown("### 物料列表")
        all_materials = get_materials()
        if all_materials:
            type_icons = {"文档": "📄", "PPT": "📊", "图片": "🖼️",
                          "视频": "🎬", "表格": "📋", "其他": "📁"}
            for mid, mat in all_materials.items():
                with st.container(border=True):
                    icon = type_icons.get(mat["type"], "📁")
                    st.markdown(f"{icon} **{mat['name']}**")
                    st.caption(f"类型：{mat['type']} | "
                               f"产品：{mat['product_id']} | "
                               f"大小：{mat['size']/1024:.0f}KB")
                    if mat.get("tags"):
                        st.caption(f"标签：{' · '.join(mat['tags'])}")
        else:
            st.info("暂无物料，请先上传")

    with st.expander("⚙️ 品牌规则配置"):
        brand = config.get("brand", {})
        st.markdown(f"- 品牌名：{brand.get('name', '')}")
        st.markdown(f"- Slogan：{brand.get('slogan', '')}")
        st.markdown("**禁区词：**")
        for w in config.get("rules", {}).get("forbidden_words", []):
            st.markdown(f"- ❌ {w}")
        st.markdown("**必含词：**")
        for w in config.get("rules", {}).get("required_words", []):
            st.markdown(f"- ✅ {w}")
        st.caption("（修改配置需编辑 config.yaml 文件）")


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
