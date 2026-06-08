"""华为伙伴营销内容协作平台 - 模块包"""

from modules.knowledge_base import (
    get_materials, add_material, add_link,
    get_links, delete_link, add_links_batch, unified_search,
    get_knowledge_stats, load_config, update_link
)
from modules.content_gen import (
    generate_copy, generate_video_script, generate_images,
    generate_video, check_compliance
)
from modules.llm_api import call_llm
from modules.partner_scraper import search_and_fetch_materials
