"""
记忆系统 — 4 级渐进式语义压缩 + 归档分离 + 角色通信

模块:
    store.py          — JSON 原子读写 + 崩溃恢复
    working_memory.py — 热层 L0: 滑动窗口 + 压缩触发
    archive.py        — 归档层: append-only 写入 + 检索
    compressor.py     — 压缩引擎: 评分 → 归档 → LLM压缩 → 实体提取
    session_memory.py — 温层 L1/L2: 跨会话持久化 + 语义检索
    knowledge_base.py — 冷层 L3: 三元组存储 + 实体索引 + 语义检索
    blackboard.py     — 共享黑板: 发布/订阅/访问控制 + 主控防火墙路由
    exporter.py       — 对话导出: 从归档提取对话并格式化为 Markdown 文档
"""
from core.memory.store import (
    read_json, write_json, append_jsonl, read_jsonl,
    dump_cache, load_cache, clear_cache,
    session_path, archive_path,
    generate_id, generate_session_id, today_str, now_iso,
    MEMORY_ROOT, SESSIONS_DIR, ARCHIVE_DIR, CACHE_DIR,
)
from core.memory.working_memory import (
    Message, SummaryL1, SummaryL2,
    WorkingMemory, WorkingMemoryRegistry, wm_registry,
)
from core.memory.compressor import (
    score_importance,
)
from core.memory.archive import (
    Archive, ArchiveRegistry, archive_registry,
)
from core.memory.compressor import (
    Compressor, compressor,
)
from core.memory.session_memory import (
    SessionMemory, SessionMemoryRegistry, sm_registry,
)
from core.memory.knowledge_base import (
    KnowledgeBase, knowledge_base,
)
from core.memory.blackboard import (
    Blackboard, BlackboardEntry, blackboard,
)
from core.memory.exporter import (
    ConversationExporter, exporter, desensitize,
)