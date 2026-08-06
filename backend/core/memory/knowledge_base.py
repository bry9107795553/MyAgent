"""
知识图谱 (Knowledge Base) — 冷层 L3 三元组存储与检索

职责:
    1. 三元组存储: 实体-关系三元组持久化 (knowledge.json)
    2. 语义检索: 关键词搜索 + 实体匹配，返回 top-K 三元组
    3. 实体管理: 实体索引、去重、合并
    4. 置信度管理: 多次提取同一事实时提升置信度
    5. 跨会话持久: 永久存活，不受会话生命周期影响

数据结构:
    KnowledgeTriple = {
        subject: str,      # 主体实体
        relation: str,     # 关系
        object: str,       # 客体实体
        source_role: str,  # 来源角色
        confidence: float, # 置信度 (0-1)
        created_at: str,   # 创建时间
        updated_at: str,   # 最后更新时间
        occurrences: int,  # 被提取的次数
    }

存储位置:
    data/memory/knowledge.json

检索策略:
    - 关键词匹配: 在 subject + relation + object 中搜索
    - 实体匹配: 按实体名称查找所有关联三元组
    - 置信度加权: 多次出现的事实排名更高
    - 后续可升级为向量语义检索 (embedding)
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from core.memory.store import (
    MEMORY_ROOT, read_json, write_json,
    generate_id, now_iso,
)


# 知识图谱文件路径
KNOWLEDGE_PATH = MEMORY_ROOT / "knowledge.json"


# ===== 方案 C-2: 知识保质期 (TTL) 辅助 =====
_KNOWLEDGE_TTL_MONTHS = {
    "technical": 6,    # 技术事实：6 个月
    "security": 3,     # 安全情报：3 个月
    "platform": 2,     # 平台/环境：2 个月
    "permanent": None, # 用户偏好等：不过期
}
_TTL_DECAY = {  # 过期时置信度折扣（只降权不删除）
    "technical": 0.5,
    "security": 0.3,
    "platform": 0.3,
    "permanent": 1.0,
}


def _iso_to_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _compute_expires_at(created_at: str, knowledge_type: str) -> Optional[str]:
    """由 created_at + TTL 计算 expires_at（permanent 返回 None）。"""
    months = _KNOWLEDGE_TTL_MONTHS.get(knowledge_type, 6)
    if months is None:
        return None
    dt = _iso_to_dt(created_at)
    if not dt:
        return None
    return (dt + timedelta(days=months * 30)).isoformat()


class KnowledgeBase:
    """冷层 L3 管理器 — 三元组存储与语义检索 (共享，非角色隔离)"""

    def __init__(self):
        self._path = KNOWLEDGE_PATH
        self._data: dict = self._load()

    # ------------------------------------------------------------------ #
    # 数据加载/保存
    # ------------------------------------------------------------------ #

    def _load(self) -> dict:
        """从磁盘加载知识图谱"""
        raw = read_json(self._path)
        if not raw:
            return {
                "version": "1.0",
                "triples": [],
                "entities": {},        # entity_name -> {type, aliases, triple_ids}
                "stats": {
                    "total_triples": 0,
                    "total_entities": 0,
                    "last_updated": "",
                },
            }
        raw.setdefault("triples", [])
        raw.setdefault("entities", {})
        raw.setdefault("stats", {
            "total_triples": len(raw["triples"]),
            "total_entities": len(raw.get("entities", {})),
            "last_updated": raw.get("stats", {}).get("last_updated", ""),
        })
        return raw

    def _save(self):
        """持久化到磁盘"""
        self._data["stats"]["total_triples"] = len(self._data["triples"])
        self._data["stats"]["total_entities"] = len(self._data["entities"])
        self._data["stats"]["last_updated"] = now_iso()
        write_json(self._path, self._data)

    # ------------------------------------------------------------------ #
    # 三元组写入
    # ------------------------------------------------------------------ #

    def add_triple(
        self,
        subject: str,
        relation: str,
        object: str,
        source_role: str = "compressor",
        confidence: float = 0.5,
        knowledge_type: str = "technical",
    ) -> dict:
        """
        添加一条知识三元组 (自动去重合并)

        :param subject: 主体实体
        :param relation: 关系
        :param object: 客体实体
        :param source_role: 来源角色
        :param confidence: 初始置信度
        :param knowledge_type: 知识类型 technical/security/platform/permanent（决定 TTL）
        :return: 创建或更新的三元组
        """
        # 规范化实体名
        subject = self._normalize(subject)
        relation = self._normalize(relation)
        object = self._normalize(object)

        # 检查是否已存在 (去重)
        existing = self._find_existing(subject, relation, object)
        if existing:
            # 提升置信度 (多次提取 → 更可信)
            existing["occurrences"] = existing.get("occurrences", 1) + 1
            existing["confidence"] = min(
                1.0,
                existing["confidence"] + 0.1 * confidence,
            )
            existing["updated_at"] = now_iso()
            self._update_entity_index(subject, relation, object, existing["id"])
            self._save()
            return existing

        # 创建新三元组
        created = now_iso()
        triple = {
            "id": generate_id("triple"),
            "subject": subject,
            "relation": relation,
            "object": object,
            "source_role": source_role,
            "confidence": confidence,
            "created_at": created,
            "updated_at": created,
            "occurrences": 1,
            # ===== 方案 C-2 新增 3 键（老三元组无此键，由 _compute_staleness 兜底）=====
            "knowledge_type": knowledge_type,
            "expires_at": _compute_expires_at(created, knowledge_type) or "",
            "staleness": 0.0,
        }
        self._data["triples"].append(triple)

        # 更新实体索引
        self._update_entity_index(subject, relation, object, triple["id"])

        self._save()
        return triple

    def add_triples_batch(
        self,
        triples: list[dict],
        source_role: str = "compressor",
    ) -> int:
        """
        批量添加三元组 (压缩后调用)

        :param triples: [{"subject": str, "relation": str, "object": str}, ...]
        :param source_role: 来源角色
        :return: 成功添加/更新的数量
        """
        count = 0
        for t in triples:
            self.add_triple(
                subject=t.get("subject", ""),
                relation=t.get("relation", ""),
                object=t.get("object", ""),
                source_role=source_role,
                confidence=0.5,
            )
            count += 1
        return count

    # ------------------------------------------------------------------ #
    # 检索
    # ------------------------------------------------------------------ #

    def search(
        self,
        query: str,
        top_k: int = 10,
        min_confidence: float = 0.0,
    ) -> list[dict]:
        """
        混合检索：关键词 + 向量语义（如可用）

        :param query: 搜索词
        :param top_k: 返回条数
        :param min_confidence: 最低置信度
        :return: 匹配的三元组列表 (按相关性排序)
        """
        # 先试向量检索（如模型可用）
        vec_results = self._vector_search(query, top_k) if self._embed_model else []
        # 再跑关键词检索
        kw_results = self._keyword_search(query, top_k, min_confidence)
        # 合并去重
        return self._fuse_results(kw_results, vec_results, top_k)

    def _keyword_search(self, query: str, top_k: int, min_confidence: float) -> list[dict]:
        """原有关键词检索"""
        keywords = set(query.lower().split())
        scored = []
        for triple in self._data["triples"]:
            if triple["confidence"] < min_confidence:
                continue
            text = (
                triple["subject"] + " " +
                triple["relation"] + " " +
                triple["object"]
            ).lower()
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                freshness = max(0.0, 1.0 - self._compute_staleness(triple))
                weighted_score = score * triple["confidence"] * (1 + 0.1 * triple.get("occurrences", 1)) * freshness
                scored.append((weighted_score, triple))
        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:top_k]]

    # --- 向量检索（可选增强） ---

    @property
    def _embed_model(self):
        """懒加载嵌入模型 — 首次调用时才加载，避免启动时卡住"""
        if hasattr(self, '_cached_embed'):
            return self._cached_embed
        self._cached_embed = None
        try:
            from sentence_transformers import SentenceTransformer
            self._cached_embed = SentenceTransformer('all-MiniLM-L6-v2')
            print("[KB] ✅ 向量嵌入模型已加载 (all-MiniLM-L6-v2, 22MB)")
        except ImportError:
            print("[KB] ℹ 向量检索未启用 — 安装 sentence-transformers 可获得语义搜索")
        except Exception as e:
            print(f"[KB] ⚠ 向量模型加载失败: {e}")
        return self._cached_embed

    def _vector_search(self, query: str, top_k: int) -> list[dict]:
        """基于嵌入向量的语义搜索"""
        model = self._embed_model
        if not model or len(self._data["triples"]) == 0:
            return []
        import numpy as np
        # 构建文档文本
        docs = [
            t["subject"] + " " + t["relation"] + " " + t["object"]
            for t in self._data["triples"]
        ]
        # 编码
        q_vec = model.encode([query], normalize_embeddings=True)[0]
        d_vecs = model.encode(docs, normalize_embeddings=True)
        # 余弦相似度
        sims = np.dot(d_vecs, q_vec)
        # 取 top-k
        idxs = np.argsort(sims)[::-1][:top_k * 2]
        results = []
        for i in idxs:
            if sims[i] < 0.3:
                continue
            t = self._data["triples"][i]
            freshness = max(0.0, 1.0 - self._compute_staleness(t))
            score = float(sims[i]) * t["confidence"] * freshness
            results.append((score, t))
        results.sort(key=lambda x: -x[0])
        return [r for _, r in results[:top_k]]

    @staticmethod
    def _fuse_results(kw: list[dict], vec: list[dict], top_k: int) -> list[dict]:
        """RRF 融合关键词和向量结果"""
        seen = set()
        fused = []
        for t in kw:
            key = (t["subject"], t["relation"], t["object"])
            if key not in seen:
                seen.add(key)
                fused.append(t)
        for t in vec:
            key = (t["subject"], t["relation"], t["object"])
            if key not in seen:
                seen.add(key)
                fused.append(t)
        return fused[:top_k]

    def search_by_entity(self, entity_name: str) -> dict:
        """
        按实体名称查找所有关联三元组

        :param entity_name: 实体名称
        :return: {
            "entity": str,
            "as_subject": [...],  # 作为主体的三元组
            "as_object": [...],   # 作为客体的三元组
            "related_entities": [str],  # 关联实体
        }
        """
        entity_name = self._normalize(entity_name)
        entity_info = self._data["entities"].get(entity_name, {})

        as_subject = []
        as_object = []
        related = set()

        for tid in entity_info.get("triple_ids", []):
            triple = self._get_triple_by_id(tid)
            if not triple:
                continue
            if triple["subject"] == entity_name:
                as_subject.append(triple)
                related.add(triple["object"])
            if triple["object"] == entity_name:
                as_object.append(triple)
                related.add(triple["subject"])

        return {
            "entity": entity_name,
            "aliases": entity_info.get("aliases", []),
            "as_subject": as_subject,
            "as_object": as_object,
            "related_entities": list(related),
            "total_relations": len(as_subject) + len(as_object),
        }

    def get_entity(self, entity_name: str) -> Optional[dict]:
        """获取实体详情"""
        entity_name = self._normalize(entity_name)
        info = self._data["entities"].get(entity_name)
        if not info:
            return None
        return {
            "name": entity_name,
            "aliases": info.get("aliases", []),
            "relation_count": len(info.get("triple_ids", [])),
        }

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def get_all_triples(self) -> list[dict]:
        """获取所有三元组"""
        return self._data["triples"]

    def get_recent_triples(self, n: int = 20) -> list[dict]:
        """获取最近的三元组"""
        return sorted(
            self._data["triples"],
            key=lambda t: t.get("created_at", ""),
            reverse=True,
        )[:n]

    def get_by_role(self, source_role: str) -> list[dict]:
        """按来源角色过滤三元组"""
        return [t for t in self._data["triples"] if t.get("source_role") == source_role]

    def get_stats(self) -> dict:
        """获取知识图谱统计"""
        return self._data["stats"]

    def get_entity_count(self) -> int:
        """获取实体总数"""
        return len(self._data["entities"])

    def get_triple_count(self) -> int:
        """获取三元组总数"""
        return len(self._data["triples"])

    # ------------------------------------------------------------------ #
    # 上下文组装
    # ------------------------------------------------------------------ #

    def assembly_context(self, task_hint: str = "", top_k: int = 5) -> list[dict]:
        """
        按需组装 L3 知识上下文，供 LLM 使用

        :param task_hint: 任务提示，用于语义搜索
        :param top_k: 最大返回三元组数
        :return: 消息列表 (OpenAI 格式)
        """
        if not task_hint:
            return []

        triples = self.search(task_hint, top_k=top_k, min_confidence=0.3)

        if not triples:
            return []

        # 格式化为自然语言注入上下文
        facts = []
        for t in triples:
            # 方案 C-2: 过期三元组加"⚠ 可能已过期"前缀
            prefix = "⚠ 可能已过期：" if self._compute_staleness(t) >= 1.0 else ""
            facts.append(f"{prefix}• {t['subject']} {t['relation']} {t['object']}")

        return [{
            "role": "system",
            "content": f"[已知事实 (跨会话)]\n" + "\n".join(facts),
        }]

    # ------------------------------------------------------------------ #
    # 方案 C-2: 知识保质期 (TTL) — 全部为新增方法
    # ------------------------------------------------------------------ #

    def _compute_staleness(self, triple: dict) -> float:
        """
        计算 staleness (0.0=新鲜, ≥1.0=完全过期)。
        老三元组无 knowledge_type/expires_at 时按 technical 兜底并以 created_at 回算。
        """
        ktype = triple.get("knowledge_type", "technical")
        if ktype == "permanent":
            return 0.0

        created = triple.get("created_at")
        expires = triple.get("expires_at")
        if not expires and created:
            expires = _compute_expires_at(created, ktype)

        now = datetime.now(timezone.utc)
        cdt = _iso_to_dt(created) if created else None
        exp_dt = _iso_to_dt(expires) if expires else None

        if cdt and exp_dt:
            total = (exp_dt - cdt).days or 1
            elapsed = (now - cdt).days
            return max(0.0, elapsed / total)
        if cdt:
            months = _KNOWLEDGE_TTL_MONTHS.get(ktype, 6) or 6
            return max(0.0, (now - cdt).days / (months * 30))
        return 0.0

    def sweep_expired(self) -> int:
        """
        清扫过期三元组：过期只**降权**不删除，置信度按类型折扣并刷新 updated_at。
        需显式调用（不会自动执行）。
        :return: 被降权的三元组数量
        """
        changed = 0
        for t in self._data["triples"]:
            if self._compute_staleness(t) >= 1.0:
                ktype = t.get("knowledge_type", "technical")
                decay = _TTL_DECAY.get(ktype, 0.5)
                t["confidence"] = round(t["confidence"] * decay, 4)
                t["updated_at"] = now_iso()
                changed += 1
        if changed:
            self._save()
        return changed

    def get_freshness_report(self) -> list[dict]:
        """供演示面板展示的知识新鲜度报表。"""
        report = []
        for t in self._data["triples"]:
            s = self._compute_staleness(t)
            status = "fresh" if s < 0.8 else ("expiring" if s < 1.0 else "expired")
            report.append({
                "subject": t.get("subject"),
                "relation": t.get("relation"),
                "object": t.get("object"),
                "knowledge_type": t.get("knowledge_type", "technical"),
                "staleness": round(s, 3),
                "status": status,
            })
        return report

    # ------------------------------------------------------------------ #
    # 维护
    # ------------------------------------------------------------------ #

    def remove_low_confidence(self, threshold: float = 0.2):
        """
        移除低置信度三元组 (清洁)

        :param threshold: 置信度阈值
        """
        before = len(self._data["triples"])
        self._data["triples"] = [
            t for t in self._data["triples"]
            if t["confidence"] >= threshold
        ]
        removed = before - len(self._data["triples"])

        # 重建实体索引
        self._rebuild_entity_index()
        self._save()

        print(f"[KnowledgeBase] 清理低置信度三元组: 移除 {removed} 条")

    def deduplicate_strict(self):
        """严格去重: 合并完全相同的三元组 (subject, relation, object 均相同)"""
        seen = {}
        merged = []

        for t in self._data["triples"]:
            key = (t["subject"], t["relation"], t["object"])
            if key in seen:
                # 合并: 取最高置信度，累加出现次数
                existing = seen[key]
                existing["confidence"] = max(existing["confidence"], t["confidence"])
                existing["occurrences"] = existing.get("occurrences", 1) + t.get("occurrences", 1)
                existing["updated_at"] = now_iso()
            else:
                seen[key] = t
                merged.append(t)

        before = len(self._data["triples"])
        self._data["triples"] = merged
        merged_count = before - len(merged)

        self._rebuild_entity_index()
        self._save()

        print(f"[KnowledgeBase] 严格去重: 合并 {merged_count} 条")

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    def _find_existing(self, subject: str, relation: str, object: str) -> Optional[dict]:
        """查找已存在的三元组"""
        for t in self._data["triples"]:
            if t["subject"] == subject and t["relation"] == relation and t["object"] == object:
                return t
        return None

    def _get_triple_by_id(self, triple_id: str) -> Optional[dict]:
        """按 ID 获取三元组"""
        for t in self._data["triples"]:
            if t["id"] == triple_id:
                return t
        return None

    def _update_entity_index(self, subject: str, relation: str, object: str, triple_id: str):
        """更新实体索引"""
        for entity in [subject, object]:
            if entity not in self._data["entities"]:
                self._data["entities"][entity] = {
                    "aliases": [],
                    "triple_ids": [],
                }
            if triple_id not in self._data["entities"][entity]["triple_ids"]:
                self._data["entities"][entity]["triple_ids"].append(triple_id)

    def _rebuild_entity_index(self):
        """重建实体索引 (去重/清理后)"""
        self._data["entities"] = {}
        for t in self._data["triples"]:
            for entity in [t["subject"], t["object"]]:
                if entity not in self._data["entities"]:
                    self._data["entities"][entity] = {
                        "aliases": [],
                        "triple_ids": [],
                    }
                if t["id"] not in self._data["entities"][entity]["triple_ids"]:
                    self._data["entities"][entity]["triple_ids"].append(t["id"])

    @staticmethod
    def _normalize(text: str) -> str:
        """规范化实体名: 去除多余空格和标点"""
        return re.sub(r"\s+", " ", text.strip())


# 全局知识图谱单例 (共享，所有角色共用)
knowledge_base = KnowledgeBase()