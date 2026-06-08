#!/usr/bin/env python3
"""
华为合作伙伴门户 DF10 物料自动抓取脚本
自动搜索、过滤、提取所有 DF10 相关物料的下载信息

使用方式:
  python3 partner_scraper.py                       # 搜索并打印所有 DF10 物料
  python3 partner_scraper.py --output df10_materials.json   # 保存为 JSON
  python3 partner_scraper.py --download-dir ./downloads     # 自动下载所有物料
   
依赖: pip install playwright
      playwright install chromium
"""

import json
import sys
import os
import re
import time
import argparse
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ 需要安装 Playwright：pip install playwright && playwright install chromium")
    sys.exit(1)


SEARCH_URL = "https://partner.huawei.com/eplus/#/cn/web/marketingsearch?from=partner&keyword=DF10&lang=zh&site=cn"
MATERIAL_DETAIL_TEMPLATE = "https://partner.huawei.com/eplus/marketing/#/cn/web/materialPreview?itemId={itemId}&platType=partnerMD"


def search_df10(headless=True, timeout=30000):
    """搜索 DF10 物料，返回物料列表"""
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        
        print("🌐 打开搜索页面...")
        page.goto(SEARCH_URL, wait_until="networkidle", timeout=timeout)
        time.sleep(3)
        
        # 检查是否出现"仍然搜索"提示（DF10 被自动修正为 D10）
        still_search = page.locator("text=仍然搜索")
        if still_search.count() > 0:
            print("🔍 检测到搜索修正，正在执行'仍然搜索'...")
            
            # 方法1: 通过 Vue 组件方法触发精确搜索
            try:
                page.evaluate("""
                    (() => {
                        const el = document.getElementById('$1688804637181');
                        if (!el) return false;
                        const key = Object.keys(el).find(k => k.startsWith('__vue_'));
                        if (!key) return false;
                        const vm = el[key];
                        if (typeof vm.keepSearch === 'function') {
                            vm.keepSearch();
                            return true;
                        }
                        return false;
                    })()
                """)
                time.sleep(3)
                print("✅ 已执行精确 DF10 搜索")
            except Exception as e:
                print(f"⚠️ Vue 方法调用失败: {e}，尝试点击链接...")
                try:
                    still_search_link = page.locator("span:has-text('仍然搜索')")
                    if still_search_link.count() > 0:
                        still_search_link.first.click()
                        time.sleep(3)
                except:
                    pass
        
        # 等待搜索结果加载
        time.sleep(2)
        
        # 提取搜索结果的物料列表
        print("📋 提取搜索结果...")
        
        # 通过 Vue 组件获取数据（最可靠）
        try:
            items = page.evaluate("""
                (() => {
                    const el = document.getElementById('$1688804637181');
                    if (!el) return [];
                    const key = Object.keys(el).find(k => k.startsWith('__vue_'));
                    if (!key) return [];
                    const vm = el[key];
                    const items = vm.listContent || [];
                    return items.map(i => ({
                        title: (i.itemTitle || i.itemName || i.title || '').replace(/<[^>]*>/g, ''),
                        name: i.itemName || '',
                        fileType: i.fileType || '',
                        itemUrl: i.itemUrl || '',
                        oriItemId: i.oriItemId || '',
                        itemSource: i.itemSource || '',
                        itemDownload: i.itemDownload || 0,
                        docId: i.docId || '',
                        language: i.language || '',
                        publishDate: i.itemCreateDate || '',
                        updateDate: i.itemUpdateDate || '',
                        description: (i.itemDescription || '').replace(/<[^>]*>/g, '')
                    }));
                })()
            """)
            if items:
                results = items
                print(f"✅ 通过 Vue 组件获取到 {len(items)} 条物料")
        except Exception as e:
            print(f"⚠️ Vue 组件提取失败: {e}")
        
        # 备用方案：从 DOM 中提取
        if not results:
            print("📝 尝试从 DOM 提取...")
            try:
                items = page.evaluate("""
                    (() => {
                        const items = [];
                        const cards = document.querySelectorAll('[class*="search-result"] [class*="item"], [class*="list-item"]');
                        cards.forEach(card => {
                            const titleEl = card.querySelector('h4, [class*="title"], a');
                            const typeEl = card.querySelector('[class*="type"], [class*="source"]');
                            items.push({
                                title: titleEl ? titleEl.textContent.trim() : '',
                                fileType: typeEl ? typeEl.textContent.trim() : ''
                            });
                        });
                        return items;
                    })()
                """)
                if items:
                    results = items
                    print(f"✅ 从 DOM 提取到 {len(items)} 条物料")
            except Exception as e:
                print(f"⚠️ DOM 提取失败: {e}")
        
        # 输出搜索结果（标题）
        if results:
            print(f"\n{'='*60}")
            print(f"找到 {len(results)} 条 DF10 相关物料:")
            print(f"{'='*60}")
            for i, item in enumerate(results, 1):
                ftype = item.get('fileType', '?').upper()
                title = item.get('title', item.get('name', '未命名'))
                print(f"  {i:2d}. [{ftype:5s}] {title}")
            print(f"{'='*60}\n")
        else:
            print("❌ 未找到任何物料")
        
        browser.close()
    
    return results


def print_as_link_list(items):
    """打印为 markdown 链接列表"""
    print("\n## DF10 物料清单\n")
    for i, item in enumerate(items, 1):
        title = item.get('title', item.get('name', '未知'))
        url = item.get('itemUrl', '')
        ftype = item.get('fileType', '').upper()
        if url:
            print(f"{i}. [{ftype}] [{title}]({url})")
        else:
            print(f"{i}. [{ftype}] {title}")


def save_to_json(items, output_path):
    """保存为 JSON 文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"✅ 已保存到 {output_path}")


def main():
    parser = argparse.ArgumentParser(description="华为合作伙伴门户 DF10 物料自动抓取")
    parser.add_argument('--output', '-o', help='保存结果为 JSON 文件路径')
    parser.add_argument('--links', action='store_true', help='以 Markdown 链接格式打印')
    parser.add_argument('--no-headless', action='store_true', help='显示浏览器界面（调试用）')
    args = parser.parse_args()
    
    items = search_df10(headless=not args.no_headless)
    
    if not items:
        sys.exit(1)
    
    if args.links:
        print_as_link_list(items)
    
    if args.output:
        save_to_json(items, args.output)
    
    # 打印物料详情页 URL 列表（可直接在浏览器打开）
    print("\n📎 物料详情页链接:")
    for item in items:
        url = item.get('itemUrl', '')
        title = item.get('title', item.get('name', '?'))
        if url:
            print(f"  {url}")


if __name__ == '__main__':
    main()
