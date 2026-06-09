"""
数据库模块 - SQLite 存储审核记录 + 视频文件管理
- 伙伴提交的内容 + 审核意见
- 视频文件存储（审核通过后才开放下载）
"""

import sqlite3
import json
import time
import os
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "app.db"
VIDEO_DIR = DATA_DIR / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)


def _get_conn():
    """获取数据库连接"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库表"""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contents (
            id TEXT PRIMARY KEY,
            partner TEXT NOT NULL DEFAULT '合作伙伴',
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            direction_id TEXT,
            direction_name TEXT,
            idea TEXT NOT NULL,
            copy TEXT,
            script TEXT,
            video_script TEXT,
            image_prompts TEXT,
            image_paths TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            review_comment TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            content_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            filesize INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (content_id) REFERENCES contents(id)
        );
    """)
    conn.commit()
    conn.close()


def submit_content(product, direction, idea, copy="", script="", video_script="",
                   image_prompts=None, image_paths=None):
    """伙伴提交内容到审核"""
    conn = _get_conn()
    import uuid
    content_id = f"ct_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    conn.execute("""
        INSERT INTO contents (id, partner, product_id, product_name, direction_id,
                              direction_name, idea, copy, script, video_script,
                              image_prompts, image_paths, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        content_id,
        "合作伙伴",
        product.get("id", ""),
        product.get("name", ""),
        direction.get("id", "") if direction else "",
        direction.get("name", "") if direction else idea[:20],
        idea,
        copy,
        script,
        video_script,
        json.dumps(image_prompts or [], ensure_ascii=False),
        json.dumps(image_paths or [], ensure_ascii=False),
        "pending",
        now,
    ))
    conn.commit()
    conn.close()
    return content_id


def save_video(content_id, filepath, description=""):
    """保存视频文件记录"""
    conn = _get_conn()
    import uuid
    video_id = f"vd_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    filename = Path(filepath).name
    filesize = os.path.getsize(filepath) if os.path.exists(filepath) else 0

    conn.execute("""
        INSERT INTO videos (id, content_id, filename, filepath, filesize,
                            description, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (video_id, content_id, filename, filepath, filesize, description, "pending", now))
    conn.commit()
    conn.close()
    return video_id


def get_pending_contents():
    """获取待审核内容列表"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM contents WHERE status = 'pending' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_approved_contents():
    """获取已通过的内容"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM contents WHERE status = 'approved' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_rejected_contents():
    """获取已退回的内容"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM contents WHERE status = 'rejected' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_all_contents():
    """获取所有内容"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM contents ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_content_by_id(content_id):
    """获取单个内容详情"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM contents WHERE id = ?", (content_id,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def approve_content(content_id, review_comment=""):
    """审核通过"""
    conn = _get_conn()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE contents SET status = 'approved', review_comment = ?, updated_at = ? WHERE id = ?",
        (review_comment, now, content_id)
    )
    # 同时更新关联视频状态为可下载
    conn.execute(
        "UPDATE videos SET status = 'approved' WHERE content_id = ?", (content_id,)
    )
    conn.commit()
    conn.close()


def reject_content(content_id, review_comment):
    """审核退回，必须提供修改意见"""
    conn = _get_conn()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE contents SET status = 'rejected', review_comment = ?, updated_at = ? WHERE id = ?",
        (review_comment, now, content_id)
    )
    conn.commit()
    conn.close()


def get_videos_for_content(content_id):
    """获取某个内容关联的视频"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM videos WHERE content_id = ? ORDER BY created_at DESC",
        (content_id,)
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_downloadable_videos():
    """获取所有可通过的视频（供伙伴下载）"""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT v.*, c.product_name, c.direction_name, c.idea
        FROM videos v
        JOIN contents c ON v.content_id = c.id
        WHERE v.status = 'approved' AND c.status = 'approved'
        ORDER BY v.created_at DESC
    """).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row):
    """sqlite3.Row → dict"""
    return dict(row) if row else {}


# 启动时初始化
init_db()
