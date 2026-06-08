#!/usr/bin/env python3
"""
华为合作伙伴门户 DF10 物料全自动抓取

功能:
  1. 自动打开 partner.huawei.com 搜索 DF10
  2. 自动点击"仍然搜索：DF10"触发精确搜索
  3. 提取所有 DF10 物料（标题、URL、类型）
  4. 自动打开每个物料详情页，提取真实下载地址
  5. 保存结果到 JSON 和系统知识库

使用:
  pip install playwright
  playwright install chromium
  
  python3 auto_scrape_df10.py            # 搜索并打印
  python3 auto_scrape_df10.py --download # 搜索并下载所有物料
  python3 auto_scrape_df10.py --headless # 无头模式（服务器运行）
"""

import json
import sys
import os
import re
import time
import argparse
import requests
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ 请安装 Playwright: pip install playwright && playwright install chromium")
    sys.exit(1)

SEARCH_URL = "https://partner.huawei.com/eplus/#/cn/web/marketingsearch?from=partner&keyword=DF10&lang=zh&site=cn"
MATERIAL_PREVIEW_TPL = "https://partner.huawei.com/eplus/marketing/#/cn/web/materialPreview?itemId={itemId}&platType=partnerMD"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def auto_scrape_df10(headless=True, download=False, download_dir="./df10_downloads", timeout=60000):
    """完整自动化流程"""
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=[
            '--no-sandbox', '--disable-setuid-sandbox'
        ])
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
        )
        page = context.new_page()

        # ===== 步骤1：打开搜索页面 =====
        log("🌐 打开华为合作伙伴门户 DF10 搜索页...")
        page.goto(SEARCH_URL, wait_until="networkidle", timeout=timeout)
        time.sleep(3)

        # ===== 步骤2：点击"仍然搜索：DF10" =====
        log("🔍 检查搜索修正提示...")
        still_visible = page.locator("text=仍然搜索").first
        if still_visible.is_visible(timeout=5000):
            log("📌 检测到自动修正提示，正在执行精确搜索...")
            
            # 方法A：通过 Vue 组件触发 keepSearch
            success = page.evaluate("""
                (() => {
                    const el = document.getElementById('$1688804637181');
                    if (!el) return false;
                    const key = Object.keys(el).find(k => k.startsWith('__vue_'));
                    if (!key) return false;
                    const vm = el[key];
                    if (typeof vm.keepSearch === 'function') {
                        vm.keepSearch();
                        return 'vue_keepSearch';
                    }
                    return false;
                })()
            """)
            
            if success:
                log(f"✅ Vue keepSearch 调用成功: {success}")
            else:
                # 方法B：直接点击 span
                log("⚠️ 尝试点击 span 元素...")
                span = page.locator("span:has-text('仍然搜索')").first
                if span.is_visible():
                    span.click()
                    log("✅ 点击仍然搜索 span")
            
            time.sleep(3)
            log("✅ 精确搜索完成")

        # ===== 步骤3：提取结果 =====
        log("📋 提取 DF10 物料数据...")
        time.sleep(2)

        items = page.evaluate("""
            (() => {
                const el = document.getElementById('$1688804637181');
                if (!el) return [];
                const key = Object.keys(el).find(k => k.startsWith('__vue_'));
                if (!key) return [];
                const vm = el[key];
                const items = vm.listContent || [];
                
                // 获取总数
                const total = (vm.page && vm.page.total) || items.length;
                
                return {
                    total: total,
                    items: items.map(i => ({
                        title: (i.itemTitle || i.itemName || i.title || '').replace(/<[^>]*>/g, ''),
                        name: i.itemName || '',
                        fileType: i.fileType || '',
                        itemUrl: i.itemUrl || '',
                        oriItemId: i.oriItemId || '',
                        itemSource: i.itemSource || '',
                        downloadCount: i.itemDownload || 0,
                        previewCount: i.itemPreview || 0,
                        docId: i.docId || '',
                        language: i.language || '',
                        publishDate: i.itemCreateDate || '',
                        updateDate: i.itemUpdateDate || '',
                        description: (i.itemDescription || '').replace(/<[^>]*>/g, ''),
                        sourceType: i.sourceType || ''
                    }))
                };
            })()
        """)
        
        if items and items.get('items'):
            results = items['items']
            total = items.get('total', len(results))
            log(f"✅ 成功提取 {len(results)} 条 DF10 物料（总计约 {total} 条）")
        else:
            log("❌ 未能提取到物料数据")
            page.screenshot(path="error_screenshot.png")
            browser.close()
            return []

        # ===== 步骤4：打印结果 =====
        log("=" * 60)
        log(f"DF10 物料清单（共 {len(results)} 项）")
        log("=" * 60)
        for i, item in enumerate(results, 1):
            ftype = item.get('fileType', '?').upper()
            title = item.get('title', item.get('name', '未命名'))
            log(f"  {i:2d}. [{ftype:5s}] {title}")
        log("=" * 60)

        # ===== 步骤5：可选 - 打开每个详情页获取下载链接 =====
        if download:
            download_dir = Path(download_dir)
            download_dir.mkdir(parents=True, exist_ok=True)
            log(f"📥 开始下载物料到 {download_dir}...")
            
            for item in results:
                ori_item_id = item.get('oriItemId', '')
                title = item.get('title', 'unknown')
                file_type = item.get('fileType', '')
                
                if not ori_item_id:
                    continue
                
                detail_url = MATERIAL_PREVIEW_TPL.format(itemId=ori_item_id)
                log(f"  打开详情页: {title[:40]}...")
                
                try:
                    new_page = context.new_page()
                    new_page.goto(detail_url, wait_until="networkidle", timeout=30000)
                    time.sleep(3)
                    
                    # 查找下载链接或直接下载按钮
                    download_links = new_page.evaluate("""
                        (() => {
                            const links = [];
                            document.querySelectorAll('a[href*="download"], a[href*="Material"], a[href$=".pdf"], a[href$=".pptx"], a[href$=".mp4"], a[href$=".jpg"], a[href$=".psd"]')
                                .forEach(a => {
                                    links.push(a.href);
                                });
                            return links;
                        })()
                    """)
                    
                    if download_links and len(download_links) > 0:
                        dl_url = download_links[0]
                        safe_name = re.sub(r'[^\w\u4e00-\u9fff]', '_', title)[:60]
                        ext = file_type or 'bin'
                        file_path = download_dir / f"{safe_name}.{ext}"
                        
                        try:
                            resp = requests.get(dl_url, timeout=30, headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                            })
                            if resp.status_code == 200:
                                file_path.write_bytes(resp.content)
                                log(f"    ✅ 已下载: {file_path.name} ({len(resp.content)/1024:.0f} KB)")
                        except Exception as e:
                            log(f"    ⚠️ 下载失败: {e}")
                    
                    new_page.close()
                except Exception as e:
                    log(f"    ⚠️ 打开详情页失败: {e}")
        
        browser.close()
    
    # ===== 步骤6：保存结果 =====
    save_path = Path("df10_materials.json")
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log(f"💾 结果已保存到 {save_path}")
    
    return results


def print_as_links(items):
    """打印为可直接点击的 Markdown 链接"""
    print("\n## DF10 物料链接\n")
    for i, item in enumerate(items, 1):
        title = item.get('title', '?')
        url = item.get('itemUrl', '')
        ftype = item.get('fileType', '').upper()
        if url:
            print(f"{i}. [{ftype}] [{title}]({url})")
        else:
            print(f"{i}. [{ftype}] {title}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="华为合作伙伴门户 DF10 物料自动抓取")
    parser.add_argument('--headless', action='store_true', help='无头模式')
    parser.add_argument('--download', action='store_true', help='下载物料文件')
    parser.add_argument('--download-dir', default='./df10_downloads', help='下载目录')
    parser.add_argument('--links', action='store_true', help='以 Markdown 链接格式输出')
    args = parser.parse_args()
    
    items = auto_scrape_df10(
        headless=not args.headless if not args.headless else True,
        download=args.download,
        download_dir=args.download_dir
    )
    
    if args.links:
        print_as_links(items)
    
    if not items:
        sys.exit(1)
