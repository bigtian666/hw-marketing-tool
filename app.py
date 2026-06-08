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
    get_materials, add_material, add_link,
    get_links, delete_link, add_links_batch, unified_search,
    get_knowledge_stats, load_config
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
            "例：我想突出ekitEngine DF10防偷拍检测功能，用'出差住酒店安全检测'这个场景，\n"
            "展现一键检测隐藏摄像头的便捷，配上'安心出行，隐私无忧'这个主题……"
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
    matched_materials = unified_search(
        current_direction.get("name", ""), product.get("id")
    )
    if matched_materials:
        type_icons = {"文档": "📄", "PPT": "📊", "图片": "🖼️",
                      "视频": "🎬", "表格": "📋", "其他": "📁"}
        for mat in matched_materials[:5]:
            if mat.get("_type") == "link":
                st.caption(f"🔗 {mat.get('title', '未命名')}  (链接)")
            else:
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
                names = []
                for m in matched_materials[:3]:
                    names.append(m.get("name", m.get("title", "未命名")))
                materials_context = "、".join(names)

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
def render_management_page(config):
    st.title("⚙️ 知识库管理")
    st.caption("管理华为伙伴营销物料，支持链接和文件两种方式")

    # 产品映射
    prod_map = {p["name"]: p["id"] for p in products}

    # 知识库概览
    stats = get_knowledge_stats()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📎 物料链接", stats["total_links"])
    with col2:
        st.metric("📁 本地文件", stats["total_files"])
    with col3:
        st.metric("⏳ 待抓取", stats["status_summary"]["待抓取"])
    with col4:
        st.metric("✅ 已下载", stats["status_summary"]["已下载"])

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔗 链接管理（推荐）",
        "🔍 搜索导入物料",
        "📤 上传文件",
        "📚 全部素材",
        "⚙️ 品牌规则"
    ])

    # ═══ Tab 1: 链接管理 ═══
    with tab1:
        link_product = st.selectbox("归属产品", list(prod_map.keys()), key="link_prod")

        st.markdown("#### ➕ 添加单个链接")
        col_a, col_b = st.columns([3, 1])
        with col_a:
            single_url = st.text_input(
                "物料链接",
                placeholder="https://partner.huawei.com/eplus/marketing/#/cn/web/materialPreview?...",
                key="single_url_input"
            )
        with col_b:
            if st.button("添加", type="primary", key="add_single", use_container_width=True):
                pid = prod_map[link_product]
                add_link(single_url, pid, tags=["手动添加"], notes="")
                st.success("✅ 已添加！")

        st.divider()

        st.markdown("#### 📋 批量添加链接")
        urls_text = st.text_area(
            "每行一个URL，批量导入", height=120,
            placeholder=(
                "https://partner.huawei.com/eplus/marketing/#/cn/...\n"
                "https://partner.huawei.com/eplus/marketing/#/cn/..."
            ),
            key="batch_urls"
        )
        default_tags = st.text_input("默认标签（逗号分隔）", placeholder="产品, 卖点", key="batch_tags")
        if st.button("批量导入", type="primary", use_container_width=True, key="batch_add"):
            if urls_text.strip():
                tags = [t.strip() for t in default_tags.split(",") if t.strip()]
                added = add_links_batch(urls_text, prod_map[link_product], tags)
                st.success(f"✅ 成功添加 {len(added)} 个链接！")

        st.divider()

        st.markdown("#### 📑 已添加的链接")
        _render_link_list()

    # ═══ Tab 2: 搜索导入物料（推荐！） ═══
    with tab2:
        st.markdown("### 🔍 从 partner 网站搜索产品，批量导入物料")
        st.info("""
        **操作步骤：**
        1. 在下面输入要搜索的产品关键词
        2. 登录 [华为合作伙伴网站](https://partner.huawei.com/eplus/marketing)，在「营销物料」模块搜索该产品
        3. 在搜索结果中，**右键逐个打开物料详情页到新标签页**，复制地址栏URL
        4. 把所有URL粘贴到下方输入框，一键导入
        """)

        col_s1, col_s2 = st.columns([1, 2])
        with col_s1:
            search_keyword = st.text_input(
                "搜索关键词",
                placeholder="例如：Pura70、MatePad、问界",
                key="search_keyword"
            )
        with col_s2:
            search_note = st.text_input(
                "搜索结果说明（选填）",
                placeholder="例如：登录partner网站后搜索到15个物料",
                key="search_note"
            )

        st.markdown("#### 📋 粘贴搜索结果中的物料链接")
        st.caption("从搜索结果页逐个打开物料详情，复制URL到这里，每行一个")

        search_prod = st.selectbox("归属产品", list(prod_map.keys()), key="search_prod")
        search_tags = st.text_input(
            "统一标签（自动给这批物料打标签，逗号分隔）",
            placeholder=f"例如：{search_keyword}, 营销物料" if search_keyword else "产品, 营销物料",
            key="search_tags"
        )

        search_urls = st.text_area(
            "物料链接列表（每行一个）",
            height=200,
            placeholder=(
                "https://partner.huawei.com/eplus/marketing/#/cn/web/materialPreview?itemId=xxx1&platType=partnerMD\n"
                "https://partner.huawei.com/eplus/marketing/#/cn/web/materialPreview?itemId=xxx2&platType=partnerMD\n"
                "https://partner.huawei.com/eplus/marketing/#/cn/web/materialPreview?itemId=xxx3&platType=partnerMD"
            ),
            key="search_urls_input"
        )

        col_b1, col_b2, col_b3 = st.columns([1, 2, 1])
        with col_b2:
            if st.button("🚀 一键导入搜索结果", type="primary", use_container_width=True, key="search_import"):
                if search_urls.strip():
                    tags = ["搜索导入"]
                    if search_keyword:
                        tags.append(search_keyword)
                    if search_tags.strip():
                        tags += [t.strip() for t in search_tags.split(",") if t.strip()]
                    added = add_links_batch(search_urls, prod_map[search_prod], tags)
                    st.success(f"✅ 成功导入 {len(added)} 个物料链接！")
                    st.info(f"💡 关联搜索词：{search_keyword or '未指定'} | 说明：{search_note or '无'}")
                    if search_note:
                        # 把说明记到链接上
                        pass

        if search_keyword:
            st.divider()
            label = f"📊 当前知识库已有素材（{search_keyword}）"
            with st.expander(label, expanded=True):
                matched = unified_search(search_keyword, prod_map[search_prod] if search_prod else None)
                if matched:
                    st.caption(f"找到 {len(matched)} 项相关素材")
                    for m in matched:
                        icon = "🔗" if m.get("_type") == "link" else "📁"
                        st.text(f"{icon} {m.get('title', m.get('name', '未命名'))}")
                else:
                    st.caption("暂无相关素材，导入后这里就会显示")

    # ═══ Tab 3: 上传文件 ═══
    with tab3:
        st.markdown("### 上传营销物料文件")
        st.caption("从 partner 网站下载后上传，或上传本地文件")
        up_prod = st.selectbox("归属产品", list(prod_map.keys()), key="up_prod")
        mat_name = st.text_input("物料名称", placeholder="例如：Pura70产品彩页_v3", key="up_name")
        mat_tags = st.text_input("标签（逗号分隔）", placeholder="产品, 卖点, 高清图", key="up_tags")
        uploaded_file = st.file_uploader(
            "选择文件（PDF/PPTX/PNG/JPG/MP4 等）",
            type=["pdf", "pptx", "ppt", "docx", "png", "jpg", "jpeg", "mp4"],
            key="up_file"
        )
        if uploaded_file and mat_name:
            pid = prod_map[up_prod]
            save_dir = Path(__file__).parent / "data" / "materials" / pid
            save_dir.mkdir(parents=True, exist_ok=True)
            fp = save_dir / uploaded_file.name
            with open(fp, "wb") as f:
                f.write(uploaded_file.getbuffer())
            tags = [t.strip() for t in mat_tags.split(",") if t.strip()]
            add_material(str(fp), pid, mat_name, tags)
            st.success(f"✅ 物料「{mat_name}」上传成功！")
            st.balloons()

    # ═══ Tab 4: 全部素材 ═══
    with tab4:
        st.markdown("### 全部知识库素材")
        all_materials = get_materials()
        all_links = get_links()
        total = len(all_materials) + len(all_links)
        st.caption(f"共 {total} 项素材（{len(all_links)} 链接 + {len(all_materials)} 文件）")

        kw = st.text_input("🔍 搜索素材", placeholder="输入关键词筛选...", key="mat_search")
        if kw:
            results = unified_search(kw)
            st.caption(f"搜索「{kw}」找到 {len(results)} 项")
            for m in results:
                icon = "🔗" if m.get("_type") == "link" else "📁"
                with st.container(border=True):
                    st.markdown(f"{icon} **{m.get('title', m.get('name', '未命名'))}**")
                    st.caption(f"产品：{m.get('product_id', '')} | 类型：{m.get('_type', m.get('type', ''))}")
        else:
            if all_materials:
                st.markdown("#### 📁 本地文件")
                ticons = {"文档": "📄", "PPT": "📊", "图片": "🖼️", "视频": "🎬", "表格": "📋", "其他": "📁"}
                for mat in all_materials.values():
                    icon = ticons.get(mat["type"], "📁")
                    with st.container(border=True):
                        st.markdown(f"{icon} **{mat['name']}**")
                        st.caption(f"类型：{mat['type']} | 产品：{mat['product_id']} | 大小：{mat['size']/1024:.0f}KB")
                        if mat.get("tags"):
                            st.caption(f"标签：{' · '.join(mat['tags'])}")

            if all_links:
                st.markdown("#### 🔗 物料链接")
                sicons = {"待抓取": "⏳", "已抓取": "📋", "已下载": "✅", "失效": "❌"}
                for link in all_links.values():
                    icon = sicons.get(link["status"], "❓")
                    with st.container(border=True):
                        st.markdown(f"{icon} **{link['title']}**")
                        st.caption(f"状态：{link['status']} | 产品：{link.get('product_id', '')}")

            if not all_materials and not all_links:
                st.info("暂无任何素材")

    # ═══ Tab 5: 品牌规则 ═══
    with tab5:
        brand = config.get("brand", {})
        st.markdown(f"**品牌名：** {brand.get('name', '')}")
        st.markdown(f"**Slogan：** {brand.get('slogan', '')}")
        st.markdown(f"**品牌话术倾向：** {'、'.join(brand.get('tone', []))}")
        st.markdown("**❌ 禁区词：**")
        for w in config.get("rules", {}).get("forbidden_words", []):
            st.markdown(f"- {w}")
        st.markdown("**✅ 必含词：**")
        for w in config.get("rules", {}).get("required_words", []):
            st.markdown(f"- {w}")
        st.caption("修改配置需编辑 config.yaml 文件")

    # ═══ Tab 2: 上传文件 ═══
    with tab2:
        st.markdown("### 上传营销物料文件")
        st.caption("从 partner 网站下载后上传，或上传本地文件")
        up_prod = st.selectbox("归属产品", list(prod_map.keys()), key="up_prod")
        mat_name = st.text_input("物料名称", placeholder="例如：Pura70产品彩页_v3", key="up_name")
        mat_tags = st.text_input("标签（逗号分隔）", placeholder="产品, 卖点, 高清图", key="up_tags")
        uploaded_file = st.file_uploader(
            "选择文件（PDF/PPTX/PNG/JPG/MP4 等）",
            type=["pdf", "pptx", "ppt", "docx", "png", "jpg", "jpeg", "mp4"],
            key="up_file"
        )
        if uploaded_file and mat_name:
            pid = prod_map[up_prod]
            save_dir = Path(__file__).parent / "data" / "materials" / pid
            save_dir.mkdir(parents=True, exist_ok=True)
            fp = save_dir / uploaded_file.name
            with open(fp, "wb") as f:
                f.write(uploaded_file.getbuffer())
            tags = [t.strip() for t in mat_tags.split(",") if t.strip()]
            add_material(str(fp), pid, mat_name, tags)
            st.success(f"✅ 物料「{mat_name}」上传成功！")
            st.balloons()

    # ═══ Tab 3: 全部素材 ═══
    with tab3:
        st.markdown("### 全部知识库素材")
        all_materials = get_materials()
        all_links = get_links()
        total = len(all_materials) + len(all_links)
        st.caption(f"共 {total} 项素材（{len(all_links)} 链接 + {len(all_materials)} 文件）")

        if all_materials:
            st.markdown("#### 📁 本地文件")
            ticons = {"文档": "📄", "PPT": "📊", "图片": "🖼️",
                      "视频": "🎬", "表格": "📋", "其他": "📁"}
            for mat in all_materials.values():
                icon = ticons.get(mat["type"], "📁")
                with st.container(border=True):
                    st.markdown(f"{icon} **{mat['name']}**")
                    st.caption(f"类型：{mat['type']} | 产品：{mat['product_id']} | 大小：{mat['size']/1024:.0f}KB")
                    if mat.get("tags"):
                        st.caption(f"标签：{' · '.join(mat['tags'])}")

        if all_links:
            st.markdown("#### 🔗 物料链接")
            sicons = {"待抓取": "⏳", "已抓取": "📋", "已下载": "✅", "失效": "❌"}
            for link in all_links.values():
                icon = sicons.get(link["status"], "❓")
                with st.container(border=True):
                    st.markdown(f"{icon} **{link['title']}**")
                    st.caption(f"状态：{link['status']} | 产品：{link.get('product_id', '')}")

        if not all_materials and not all_links:
            st.info("暂无任何素材，请先添加链接或上传文件")

    # ═══ Tab 4: 品牌规则 ═══
    with tab4:
        brand = config.get("brand", {})
        st.markdown(f"**品牌名：** {brand.get('name', '')}")
        st.markdown(f"**Slogan：** {brand.get('slogan', '')}")
        st.markdown(f"**品牌话术倾向：** {'、'.join(brand.get('tone', []))}")
        st.markdown("**❌ 禁区词：**")
        for w in config.get("rules", {}).get("forbidden_words", []):
            st.markdown(f"- {w}")
        st.markdown("**✅ 必含词：**")
        for w in config.get("rules", {}).get("required_words", []):
            st.markdown(f"- {w}")
        st.caption("修改配置需编辑 config.yaml 文件")


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
