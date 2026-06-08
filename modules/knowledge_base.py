"""
知识库模块 v2 - 链接管理型
支持：
  - 维护 partner 物料链接
  - 自动抓取页面标题和附件
  - 手动/自动下载附件到本地
  - 按产品/标签组织
"""

import json
import os
import re
import time
from pathlib import Path
import yaml
import hashlib

DATA_DIR = Path(__file__).parent.parent / "data"
LINKS_FILE = DATA_DIR / "knowledge_index" / "links.json"
INDEX_FILE = DATA_DIR / "knowledge_index" / "index.json"
MATERIALS_DIR = DATA_DIR / "materials"


def load_config():
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ════════════════════════════════════════════════════════════
# 链接管理
# ════════════════════════════════════════════════════════════

def get_links(product_id=None):
    """获取所有物料链接"""
    LINKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LINKS_FILE.exists():
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            links = json.load(f)
    else:
        links = {}

    if product_id:
        return {k: v for k, v in links.items() if v.get("product_id") == product_id}
    return links


def add_link(url, product_id, title="", tags=None, notes=""):
    """添加一个 partner 物料链接"""
    LINKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LINKS_FILE.exists():
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            links = json.load(f)
    else:
        links = {}

    link_id = hashlib.md5(url.encode()).hexdigest()[:12]

    links[link_id] = {
        "id": link_id,
        "url": url,
        "product_id": product_id,
        "title": title or _extract_title_from_url(url),
        "tags": tags or [],
        "notes": notes,
        "status": "待抓取",  # 待抓取 | 已抓取 | 已下载 | 失效
        "files": [],
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M"),
    }

    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, indent=2)
    return link_id


def update_link(link_id, **kwargs):
    """更新链接信息"""
    links = get_links()
    if link_id in links:
        links[link_id].update(kwargs)
        links[link_id]["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
        with open(LINKS_FILE, "w", encoding="utf-8") as f:
            json.dump(links, f, ensure_ascii=False, indent=2)
        return True
    return False


def delete_link(link_id):
    """删除链接"""
    links = get_links()
    if link_id in links:
        del links[link_id]
        with open(LINKS_FILE, "w", encoding="utf-8") as f:
            json.dump(links, f, ensure_ascii=False, indent=2)
        return True
    return False


def add_links_batch(urls_text, product_id, default_tags=None):
    """批量添加链接（每行一个URL）"""
    added = []
    for line in urls_text.strip().split("\n"):
        url = line.strip()
        if url and url.startswith("http"):
            link_id = add_link(url, product_id, tags=default_tags or [])
            added.append(link_id)
    return added


def _extract_title_from_url(url):
    """从URL中提取可能的标题"""
    match = re.search(r"itemId=([^&]+)", url)
    if match:
        return f"物料_{match.group(1)[:8]}"
    return "未命名物料"


# ════════════════════════════════════════════════════════════
# 本地文件管理（已有功能增强）
# ════════════════════════════════════════════════════════════

def get_materials(product_id=None):
    """获取已下载的物料文件"""
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {}

    if product_id:
        return {k: v for k, v in index.items() if v.get("product_id") == product_id}
    return index


def add_material(file_path, product_id, material_name, tags=None, source_link_id=None):
    """添加本地物料文件到知识库"""
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()[:12]

    ext = Path(file_path).suffix.lower()
    material_type = {
        ".pdf": "文档", ".pptx": "PPT", ".ppt": "PPT",
        ".docx": "文档", ".doc": "文档", ".xlsx": "表格",
        ".png": "图片", ".jpg": "图片", ".jpeg": "图片",
        ".mp4": "视频", ".mov": "视频", ".avi": "视频",
    }.get(ext, "其他")

    dest_dir = MATERIALS_DIR / product_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{file_hash}{ext}"
    import shutil
    shutil.copy2(file_path, dest_path)

    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {}

    index[file_hash] = {
        "id": file_hash,
        "name": material_name,
        "product_id": product_id,
        "type": material_type,
        "ext": ext,
        "path": str(dest_path),
        "tags": tags or [],
        "size": os.path.getsize(dest_path),
        "source_link": source_link_id or "",
    }

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    return file_hash


# ════════════════════════════════════════════════════════════
# 统一搜索（链接 + 本地文件）
# ════════════════════════════════════════════════════════════

def unified_search(query, product_id=None):
    """同时搜索链接和本地物料"""
    query = query.lower()
    results = []

    # 搜索本地文件
    for mid, mat in get_materials(product_id).items():
        if query in mat.get("name", "").lower():
            results.append({**mat, "_type": "file"})
        elif any(query in t.lower() for t in mat.get("tags", [])):
            results.append({**mat, "_type": "file"})

    # 搜索链接
    for lid, link in get_links(product_id).items():
        if query in link.get("title", "").lower():
            results.append({**link, "_type": "link"})
        elif query in link.get("notes", "").lower():
            results.append({**link, "_type": "link"})
        elif any(query in t.lower() for t in link.get("tags", [])):
            results.append({**link, "_type": "link"})

    return results


def get_relevant_materials(product_id, direction_id, max_count=5):
    """根据营销方向匹配合适素材（链接+本地文件）"""
    direction_tags = {
        "product_showcase": ["产品", "卖点", "展示", "功能", "介绍"],
        "activity": ["活动", "促销", "节日", "海报", "推广"],
        "scene_story": ["场景", "故事", "用户", "使用", "案例"],
        "user_case": ["案例", "客户", "评价", "口碑", "证言"],
    }
    tags = direction_tags.get(direction_id, [])
    scored = []

    # 本地文件
    for mat in get_materials(product_id).values():
        score = sum(3 for t in tags if t in mat.get("tags", []))
        score += sum(2 for t in tags if t in mat.get("name", ""))
        scored.append((score, {**mat, "_type": "file"}))

    # 链接
    for link in get_links(product_id).values():
        score = sum(2 for t in tags if t in link.get("tags", []))
        score += sum(1 for t in tags if t in link.get("title", ""))
        scored.append((score, {**link, "_type": "link"}))

    scored.sort(key=lambda x: -x[0])
    return [s[1] for s in scored[:max_count]]


# ════════════════════════════════════════════════════════════
# 导出/导入知识库
# ════════════════════════════════════════════════════════════

def export_knowledge_base():
    """导出完整知识库（用于备份或迁移）"""
    return {
        "links": get_links(),
        "materials": get_materials(),
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_knowledge_stats():
    """获取知识库统计"""
    links = get_links()
    materials = get_materials()
    return {
        "total_links": len(links),
        "total_files": len(materials),
        "by_product": {},
        "status_summary": {
            "待抓取": sum(1 for l in links.values() if l["status"] == "待抓取"),
            "已抓取": sum(1 for l in links.values() if l["status"] == "已抓取"),
            "已下载": sum(1 for l in links.values() if l["status"] == "已下载"),
        },
    }
