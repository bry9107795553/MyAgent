"""
存储层 — JSON 文件原子读写、崩溃恢复、JSONL 追加

核心保证:
    1. 原子写入: 写临时文件 → os.replace 原子重命名，保证一致性
    2. JSONL 追加: append-only 模式，不覆盖已有数据
    3. 崩溃恢复: 每 30 秒将工作内存转储到 cache/，重启可恢复
    4. 零外部依赖: 仅用 Python 标准库 + json

目录结构:
    data/memory/
    ├── sessions/       # 压缩管线 (温层)
    ├── archive/        # 原始归档 (零损失)
    ├── cache/          # 崩溃恢复
    ├── knowledge.json  # 知识图谱
    └── blackboard.json # 共享黑板
"""
import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional


# ===== 路径常量 =====

MEMORY_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "memory"
SESSIONS_DIR = MEMORY_ROOT / "sessions"
ARCHIVE_DIR = MEMORY_ROOT / "archive"
CACHE_DIR = MEMORY_ROOT / "cache"


def _ensure_dirs():
    """确保所有存储目录存在"""
    for d in [SESSIONS_DIR, ARCHIVE_DIR, CACHE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# 模块导入时自动创建目录
_ensure_dirs()


# ===== 原子 JSON 读写 =====

def read_json(path: Path) -> dict:
    """读取 JSON 文件，文件不存在返回空字典"""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict):
    """原子写入 JSON 文件 (临时文件 → rename)"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f".tmp.{uuid.uuid4().hex[:6]}")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)  # 原子操作
    except Exception:
        # 清理临时文件
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


# ===== JSONL 追加读写 =====

def append_jsonl(path: Path, entry: dict):
    """追加一行 JSON 到 JSONL 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    """读取 JSONL 文件全部内容，跳过损坏行"""
    if not path.exists():
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def read_jsonl_range(
    path: Path,
    offset: int = 0,
    limit: Optional[int] = None,
) -> list[dict]:
    """读取 JSONL 文件的指定范围 (偏移 + 条数)"""
    all_entries = read_jsonl(path)
    if offset >= len(all_entries):
        return []
    end = offset + limit if limit is not None else len(all_entries)
    return all_entries[offset:end]


# ===== 崩溃恢复 =====

def dump_cache(role: str, data: dict):
    """将工作内存转储到 cache/ 目录 (崩溃恢复)"""
    path = CACHE_DIR / f"{role}.json"
    write_json(path, {
        "role": role,
        "dumped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "data": data,
    })


def load_cache(role: str) -> Optional[dict]:
    """从 cache/ 恢复工作内存 (崩溃后重启调用)"""
    path = CACHE_DIR / f"{role}.json"
    if not path.exists():
        return None
    try:
        cached = read_json(path)
        print(f"[Store] 从缓存恢复: {role}, 时间: {cached.get('dumped_at', '未知')}")
        return cached.get("data")
    except Exception as e:
        print(f"[Store] 缓存恢复失败: {role} - {e}")
        return None


def clear_cache(role: str):
    """清除指定角色的缓存"""
    path = CACHE_DIR / f"{role}.json"
    path.unlink(missing_ok=True)


# ===== 会话文件管理 =====

def session_path(role: str) -> Path:
    """获取角色的会话文件路径 (温层 L1/L2)"""
    return SESSIONS_DIR / f"{role}.json"


def archive_path(role: str, date_str: str, session_id: str) -> Path:
    """获取归档文件路径 (按角色/日期/会话)"""
    return ARCHIVE_DIR / role / f"{date_str}_{session_id}.jsonl"


# ===== 工具函数 =====

def generate_id(prefix: str = "m") -> str:
    """生成唯一 ID，格式: {prefix}_{timestamp}_{random}"""
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


def generate_session_id() -> str:
    """生成会话 ID"""
    return f"sess_{uuid.uuid4().hex[:8]}"


def today_str() -> str:
    """返回今天的日期字符串 (YYYY-MM-DD)"""
    return time.strftime("%Y-%m-%d")


def now_iso() -> str:
    """返回当前 ISO 8601 时间戳"""
    return time.strftime("%Y-%m-%dT%H:%M:%S")