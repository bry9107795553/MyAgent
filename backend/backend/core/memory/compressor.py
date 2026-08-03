"""
压缩引擎 (Compressor) — 渐进式语义压缩流水线

职责:
    1. 重要性评分: 每条消息入库时打分 (1=低 2=中 3=高)
    2. 归档: 压缩前将原文写入 archive (零损失)
    3. L1 压缩: 5-10 轮原文 → 1 段自然语言摘要 (LLM)
    4. L2 压缩: 5 段 L1 → 1 段 bullet points (LLM)
    5. 实体提取: 从压缩内容中提取知识三元组

工作流程:
    消息进入 L0
        │
        ├──→ 同时写入 archive (零损失归档)
        │
        ▼
    L0 满 (token > 4K 或 轮次 > 20)
        │
        ├──→ 1. 归档: 被压缩的原文 → archive
        ├──→ 2. 评分: 每条消息打重要性分数
        ├──→ 3. LLM 压缩: 生成 L1 摘要
        ├──→ 4. 实体提取: 提取三元组 → L3
        └──→ 5. 清理 L0: 保留最近 N 轮

使用方式:
    compressor = Compressor()
    await compressor.compress_l1(wm, archive)
"""
import json
from typing import Optional

from core.llm.gateway import llm_gateway
from core.memory.working_memory import (
    WorkingMemory, Message, SummaryL1, SummaryL2,
    MAX_L1_COUNT, MAX_L2_COUNT,
)
from core.memory.archive import Archive
from core.memory.store import generate_id, now_iso


# ===== 重要性评分规则 =====

IMPORTANCE_RULES = {
    # 高重要性 (3): 决策、偏好、错误、技术规格
    "high_keywords": [
        "用", "不用", "不要", "改成", "改为", "换成", "选", "确定",
        "偏好", "喜欢", "不喜欢", "讨厌",
        "报错", "错误", "失败", "bug", "error", "fail",
        "技术选型", "框架", "版本", "规格", "api", "接口",
    ],
    # 低重要性 (1): 确认、寒暄、填充
    "low_keywords": [
        "好的", "ok", "明白", "知道了", "收到", "嗯",
        "继续", "然后", "下一个",
    ],
}


def score_importance(role: str, content: str) -> int:
    """
    评分消息重要性

    :param role: "user" | "assistant" | "system"
    :param content: 消息内容
    :return: 1=低 2=中 3=高
    """
    content_lower = content.lower().strip()

    # 用户消息默认重要性偏高
    if role == "user":
        base_score = 2
    else:
        base_score = 1

    # 高重要性关键词匹配
    for kw in IMPORTANCE_RULES["high_keywords"]:
        if kw in content_lower:
            return 3

    # 低重要性关键词匹配
    for kw in IMPORTANCE_RULES["low_keywords"]:
        if content_lower == kw or content_lower.startswith(kw):
            return 1

    # 长度启发: 短回复可能是确认
    if role == "assistant" and len(content) < 10:
        return 1

    # 长度启发: 长回复通常含更多信息
    if len(content) > 200:
        return 3

    return base_score


# ===== L1 压缩 Prompt =====

L1_COMPRESS_PROMPT = """你是一个对话压缩器。请将以下对话压缩成一段连贯的摘要。

规则:
1. 保留所有重要性≥2 的内容（决策、偏好、技术细节、错误）
2. 去除叙述性废话（"好的"、"正在做"、"明白"等）
3. 保留具体的技术选型和参数（如"用 CSS Modules"不要缩成"用了样式方案"）
4. 输出一段自然语言，不要用 bullet points
5. 控制在 500 字以内

请严格输出以下 JSON 格式 (不要输出其他内容，不要 markdown 代码块):
{
  "summary": "压缩后的摘要文本",
  "key_decisions": ["决策1", "决策2"],
  "entities": ["实体1", "实体2"]
}

对话内容:
{messages}

重要性标注:
{scores}"""


# ===== L2 稠密压缩 Prompt =====

L2_COMPRESS_PROMPT = """你是一个信息浓缩器。请将以下多段摘要提炼为关键要点。

规则:
1. 只保留事实，去除所有叙述
2. 每个要点一行，格式：• 主题: 关键信息
3. 合并重复信息
4. 控制在 300 字以内

请严格输出以下 JSON 格式:
{
  "bullets": ["• 主题: 关键信息", "• 主题: 关键信息"]
}

摘要内容:
{summaries}"""


# ===== 实体提取 Prompt =====

ENTITY_EXTRACT_PROMPT = """从以下内容中提取实体-关系三元组。

格式：每行一个三元组 (主体, 关系, 客体)
只提取明确的事实，不要推断。
实体名使用规范化的简称。

请严格输出以下 JSON 格式:
{
  "triples": [
    {"subject": "主体", "relation": "关系", "object": "客体"}
  ]
}

内容:
{text}"""


# ===== 压缩引擎 =====

class Compressor:
    """压缩引擎 — 编排渐进式语义压缩流水线"""

    def __init__(self):
        self._available = False

    async def init(self):
        """检查 LLM 是否可用"""
        self._available = llm_gateway.available
        if not self._available:
            print("[Compressor] LLM 未就绪，压缩功能暂不可用")

    @property
    def available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------ #
    # 压缩流水线入口
    # ------------------------------------------------------------------ #

    async def compress(self, wm: WorkingMemory, archive: Archive) -> dict:
        """
        压缩流水线入口 — 检测触发条件，逐步执行

        :param wm: 工作记忆实例
        :param archive: 归档实例
        :return: {"compressed": bool, "l1_count": int, "l2_count": int}
        """
        check = wm.should_compress()
        result = {"compressed": False, "l1_count": len(wm.get_l1_summaries()), "l2_count": len(wm.get_l2_summaries())}

        if not check["should_compress"]:
            return result

        if not self._available:
            print(f"[Compressor] 跳过压缩: LLM 不可用")
            return result

        # Step 1: 归档 + L1 压缩
        l1 = await self.compress_l1(wm, archive)
        if l1:
            result["compressed"] = True
            result["l1_count"] = len(wm.get_l1_summaries())

        # Step 2: 检查是否需要 L2 压缩
        if wm.should_compress_l2():
            l2 = await self.compress_l2(wm)
            if l2:
                result["l2_count"] = len(wm.get_l2_summaries())

        return result

    # ------------------------------------------------------------------ #
    # L1 压缩 (原文 → 摘要)
    # ------------------------------------------------------------------ #

    async def compress_l1(self, wm: WorkingMemory, archive: Archive) -> Optional[SummaryL1]:
        """
        将 L0 中待压缩的消息段压缩为 L1 摘要

        流程: 归档 → 评分 → LLM 压缩 → 实体提取 → 清理 L0

        :param wm: 工作记忆实例
        :param archive: 归档实例
        :return: L1 摘要对象，失败返回 None
        """
        messages = wm.get_all_messages()
        if not messages:
            return None

        # 1. 归档: 先写入 archive (零损失)
        archive.append_batch(wm.session_id, messages)
        print(f"[Compressor] 已归档 {len(messages)} 条消息 → {wm.role}")

        # 2. 评分: 每条消息标注重要性
        scored = []
        for m in messages:
            score = score_importance(m.role, m.content)
            scored.append(f"[重要性={score}] {m.role}: {m.content[:200]}")

        # 3. 构造 LLM 消息
        messages_text = "\n".join(
            f"[{m.role}] {m.content}" for m in messages
        )
        scores_text = "\n".join(scored)

        prompt = L1_COMPRESS_PROMPT.format(
            messages=messages_text,
            scores=scores_text,
        )

        # 4. 调用 LLM 压缩
        try:
            result = await llm_gateway.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "请压缩以上对话"},
                ],
                temperature=0.3,
                max_tokens=1024,
            )
            raw = result["content"]
        except Exception as e:
            print(f"[Compressor] L1 压缩失败: {llm_gateway.available} - {e}")
            return None

        # 5. 解析 LLM 输出
        parsed = self._extract_json(raw)
        if not parsed:
            print(f"[Compressor] L1 压缩输出无法解析: {raw[:200]}")
            return None

        # 6. 创建 L1 摘要
        l1 = SummaryL1(
            id=generate_id("l1"),
            summary=parsed.get("summary", ""),
            turn_range=(messages[0].turn, messages[-1].turn),
            key_decisions=parsed.get("key_decisions", []),
            entities=parsed.get("entities", []),
            timestamp=now_iso(),
        )
        wm.add_l1(l1)

        # 7. 清理 L0 (保留最近 5 轮)
        wm.trim_l0(keep_turns=5)

        print(f"[Compressor] L1 压缩完成: {wm.role} "
              f"turns={l1.turn_range}, "
              f"decisions={len(l1.key_decisions)}, "
              f"entities={len(l1.entities)}")
        return l1

    # ------------------------------------------------------------------ #
    # L2 稠密压缩 (摘要 → 要点)
    # ------------------------------------------------------------------ #

    async def compress_l2(self, wm: WorkingMemory) -> Optional[SummaryL2]:
        """
        将多段 L1 摘要聚合为 L2 稠密要点

        :param wm: 工作记忆实例
        :return: L2 摘要对象，失败返回 None
        """
        l1_summaries = wm.get_l1_summaries()
        if len(l1_summaries) < MAX_L1_COUNT:
            return None

        # 取最近 MAX_L1_COUNT 段 L1 摘要
        recent = l1_summaries[-MAX_L1_COUNT:]

        summaries_text = "\n\n---\n\n".join(
            f"[回合 {s.turn_range[0]}-{s.turn_range[1]}] {s.summary}"
            for s in recent
        )

        prompt = L2_COMPRESS_PROMPT.format(summaries=summaries_text)

        try:
            result = await llm_gateway.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "请提炼关键要点"},
                ],
                temperature=0.2,
                max_tokens=512,
            )
            raw = result["content"]
        except Exception as e:
            print(f"[Compressor] L2 压缩失败: {e}")
            return None

        parsed = self._extract_json(raw)
        if not parsed:
            return None

        l2 = SummaryL2(
            id=generate_id("l2"),
            bullets=parsed.get("bullets", []),
            source_l1_ids=[s.id for s in recent],
            timestamp=now_iso(),
        )
        wm.add_l2(l2)

        print(f"[Compressor] L2 压缩完成: {wm.role} "
              f"bullets={len(l2.bullets)}")
        return l2

    # ------------------------------------------------------------------ #
    # 实体提取
    # ------------------------------------------------------------------ #

    async def extract_entities(self, text: str) -> list[dict]:
        """
        从文本中提取实体-关系三元组

        :param text: 待提取文本
        :return: [{"subject": str, "relation": str, "object": str}, ...]
        """
        if not self._available:
            return []

        prompt = ENTITY_EXTRACT_PROMPT.format(text=text)

        try:
            result = await llm_gateway.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "请提取实体关系"},
                ],
                temperature=0.1,
                max_tokens=512,
            )
            raw = result["content"]
        except Exception as e:
            print(f"[Compressor] 实体提取失败: {e}")
            return []

        parsed = self._extract_json(raw)
        return parsed.get("triples", []) if parsed else []

    # ------------------------------------------------------------------ #
    # 工具方法
    # ------------------------------------------------------------------ #

    def _extract_json(self, text: str) -> Optional[dict]:
        """从 LLM 输出中提取 JSON (容错处理)"""
        text = text.strip()

        # 去除 markdown 代码块
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取第一个 JSON 对象
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return None


# 全局压缩引擎单例
compressor = Compressor()