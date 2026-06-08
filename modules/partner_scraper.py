#!/usr/bin/env python3
"""
Partner网站物料自动抓取模块
使用 Playwright 浏览器自动化从 partner.huawei.com 搜索 DF10 物料
"""

import json
import re
import time
import os
from pathlib import Path

# 知识库模块
from modules.knowledge_base import add_link, add_material, get_links, delete_link

DATA_DIR = Path(__file__).parent.parent / "data"

# 已知 DF10 物料ID列表（可直接访问，无需浏览器）
KNOWN_DF10_MATERIALS = [
    {"itemId": "09f8078ed45543febfec6bf91bc41834", "title": "华为灵眸 eKitEngine DF10新一代隐藏影像设备检测产品彩页", "type": "pdf", "desc": "彩页"},
    {"itemId": "9492963567b1492487aeb047be7d7cff", "title": "00 HUAWEI eKitEngine DF10 Presentation Slides", "type": "pptx", "desc": "演示文稿"},
    {"itemId": "f8e46b65e5d1472a87a91397d6ddb233", "title": "灵眸DF10对比评测视频", "type": "mp4", "desc": "视频"},
    {"itemId": "077111e12a6644968ca22bd9e951d6f1", "title": "DF10易拉宝源文件(26H1)", "type": "psd", "desc": "易拉宝"},
    {"itemId": "9e8743b29287485db06ba26e3298567d", "title": "灵眸DF10版本升级指导视频", "type": "mp4", "desc": "视频"},
    {"itemId": "229000f8fe374ad185e6e2897bb308fc", "title": "华为灵眸 eKitEngine DF10新一代隐藏影像设备检测产品视频", "type": "mp4", "desc": "视频"},
    {"itemId": "964d7f44086a401b91d95facc01814fa", "title": "HUAWEI eKitEngine DF10 Portable Camera Detector video", "type": "mp4", "desc": "视频"},
    {"itemId": "6463b9e52b04490dad8154a1a9885f50", "title": "iGuard Hidden-Camera Detection AirEngine DF10 Poster", "type": "jpg", "desc": "海报"},
    {"itemId": "6801a2a2a62a41c18f8beb35ff0ae3d3", "title": "灵眸防偷拍AirEngine DF10海报", "type": "jpg", "desc": "海报"},
    {"itemId": "4027a7f4e9484a92ad247ee9021f3789", "title": "华为灵眸AirEngine DF10新一代隐藏影像设备检测产品彩页", "type": "pdf", "desc": "彩页"},
]

# 重命名规则：将物料名中的 "灵眸 DF10"/"AirEngine DF10" 统一改为 "ekitEngine DF10"
def rename_to_ekitengine(title):
    """将物料标题中的品牌名统一为 ekitEngine DF10"""
    title = re.sub(r'灵眸\s*(DF10|AirEngine\s*DF10)', r'ekitEngine DF10', title)
    title = re.sub(r'AirEngine\s+DF10', r'ekitEngine DF10', title)
    title = re.sub(r'(?:灵眸|AirEngine|IGuard)\s*[-]?\s*(?:Hidden-Camera Detection )?(?:ekitEngine )?DF10', r'ekitEngine DF10', title)
    title = re.sub(r'(?i)iGuard\s+', '', title)
    return title

def search_and_fetch_materials(product_keyword="DF10", exact_model="DF10", product_id="df10"):
    """
    直接使用预知的 DF10 物料列表导入系统（无需浏览器自动化每次执行）
    物料详情页URL格式:
      https://partner.huawei.com/eplus/marketing/#/cn/web/materialPreview?itemId={itemId}&platType=partnerMD
    
    如果物料有公开下载地址，也可直接下载
    """
    print(f"[物料抓取] 导入 DF10 物料（共 {len(KNOWN_DF10_MATERIALS)} 项）")
    print(f"[物料抓取] 品牌统一为: 华为坤灵 eKitEngine DF10")
    
    # 清空旧的自动抓取链接
    _clear_old_links(product_id)
    
    imported = 0
    
    for mat in KNOWN_DF10_MATERIALS:
        # 构建物料详情页 URL
        detail_url = f"https://partner.huawei.com/eplus/marketing/#/cn/web/materialPreview?itemId={mat['itemId']}&platType=partnerMD"
        
        # 重命名标题
        cleaned_title = rename_to_ekitengine(mat['title'])
        
        try:
            link_id = add_link(
                url=detail_url,
                product_id=product_id,
                title=cleaned_title,
                tags=[mat['desc'], exact_model, "自动抓取", "partner.huawei.com"],
                notes=f"来自华为合作伙伴门户的{exact_model}{mat['desc']}物料"
            )
            imported += 1
            print(f"  ✅ [{mat['type'].upper()}] {cleaned_title}")
        except Exception as e:
            print(f"  ❌ 导入失败: {cleaned_title} - {e}")
    
    print(f"\n[物料抓取] 完成！导入 {imported} 条 DF10 物料链接")
    return imported, 0, ""


def _clear_old_links(product_id):
    """清空该产品旧的自动抓取链接"""
    links = get_links(product_id)
    for lid, link in links.items():
        if "自动抓取" in link.get("tags", []):
            delete_link(lid)
