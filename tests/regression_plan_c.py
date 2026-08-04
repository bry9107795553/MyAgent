#!/usr/bin/env python3
# =============================================================================
# Plan C 回归测试 —— 记忆系统补齐（效用评分 + 知识 TTL + 评估员接线）
#
# 目标（不依赖 GPU / 真实 LLM）：
#   C-1 经验效用评分：
#     - 老数据缺新字段 → 默认 active，正常注入（零迁移）
#     - vote(+1)→1, vote(-2)→probation, 再 vote(-2)→-3 archived
#     - get_injection 过滤 archived
#     - _evict_if_full 池满淘汰最低分
#     - get_utility_report 按分降序
#   C-2 知识 TTL：
#     - _compute_staleness：permanent=0，超期技术事实≥1，未到期<1
#     - search 新鲜度加权：过期三元组排名下降
#     - assembly_context 过期加 "⚠ 可能已过期" 前缀
#     - sweep_expired 只降权不删除
#     - 老三元组（无 knowledge_type）不崩溃
#   C-4 接线：_apply_experience_eval_hook 仅在 members 含评估员时追加步骤
# =============================================================================
import os
import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import core.agent.orchestrator as O  # noqa: E402
from core.memory.knowledge_base import KnowledgeBase  # noqa: E402
import core.role.master as M  # noqa: E402

PASS = 0
FAIL = 0
NOTES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")
        if detail:
            NOTES.append(f"{name}: {detail}")


def iso_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


print("== C-1 经验效用评分 ==")
tmp = tempfile.mkdtemp(prefix="planc_exp_")
try:
    em = O.ExperienceManager(storage_dir=tmp)

    # 老数据兼容性：直接塞一条缺新字段的 dict，应能加载为 active
    old = O.ExperienceRecord(
        task_type="git_push", keywords=["推代码", "上传"], context="c",
        constraints=["a"], successful_approach=["x"], failed_attempts=["y"],
    )
    assert old.status == "active" and old.utility_score == 0.0

    em.record("deploy", ["部署"], "ctx", ["env"], ["step1"], ["bad1"])
    rec = em.find("帮我部署一下")[0]
    check("record 后 utility_score 默认 0", rec.utility_score == 0.0,
          f"got {rec.utility_score}")

    # vote +1 → 1.0 active
    em.vote("deploy", +1, "成功")
    check("vote +1 → utility 1.0 active",
          em.get_utility_report()[0]["utility_score"] == 1.0 and
          em.get_utility_report()[0]["status"] == "active")

    # vote -2 → -1 probation（降权，但仍注入）
    em.vote("deploy", -2, "误导")
    r = em.get_utility_report()[0]
    check("vote -2 → utility -1 probation",
          r["utility_score"] == -1.0 and r["status"] == "probation",
          f"{r}")

    # vote -2 → -3 archived（出局，不再注入）
    em.vote("deploy", -2, "再次误导")
    r = em.get_utility_report()[0]
    check("vote -2 → utility -3 archived",
          r["utility_score"] == -3.0 and r["status"] == "archived",
          f"{r}")

    inj = em.get_injection("帮我部署一下")
    check("archived 经验不注入", "deploy" not in inj and inj == "",
          f"injection={inj[:40]}")

    # _evict_if_full：同 task_type 塞 16 条 → 淘汰最低分至 15 条
    em2 = O.ExperienceManager(storage_dir=tempfile.mkdtemp(prefix="planc_ev_"))
    for i in range(16):
        em2.record("bulk", [f"k{i}"], "c", ["x"], [f"step{i}"], [])
    em2._evict_if_full("bulk", capacity=15)
    active = [e for e in em2._experiences if e.task_type == "bulk" and e.status != "archived"]
    archived = [e for e in em2._experiences if e.task_type == "bulk" and e.status == "archived"]
    check("_evict_if_full 池满淘汰到 15 条 active + 1 archived",
          len(active) == 15 and len(archived) == 1,
          f"active={len(active)} archived={len(archived)}")

    # get_utility_report 降序
    rep = em2.get_utility_report()
    scores = [x["utility_score"] for x in rep if x["task_type"] == "bulk"]
    check("get_utility_report 按 utility 降序", scores == sorted(scores, reverse=True),
          f"{scores}")
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

print("== C-2 知识 TTL ==")
kb = KnowledgeBase()
# 用合成三元组覆盖真实数据做隔离测试
kb._data["triples"] = [
    {"id": "t1", "subject": "用户", "relation": "偏好", "object": "中文回复",
     "source_role": "x", "confidence": 0.9, "created_at": iso_ago(400),
     "updated_at": iso_ago(400), "occurrences": 1,
     "knowledge_type": "permanent", "expires_at": "", "staleness": 0.0},
    {"id": "t2", "subject": "项目", "relation": "使用", "object": "React18",
     "source_role": "x", "confidence": 0.8, "created_at": iso_ago(200),
     "updated_at": iso_ago(200), "occurrences": 1,
     "knowledge_type": "technical", "expires_at": "", "staleness": 0.0},
    {"id": "t3", "subject": "依赖", "relation": "有", "object": "CVE-2025",
     "source_role": "x", "confidence": 0.7, "created_at": iso_ago(120),
     "updated_at": iso_ago(120), "occurrences": 1,
     "knowledge_type": "security", "expires_at": "", "staleness": 0.0},
    # 老三元组（无 knowledge_type/expires_at）—— 不崩溃，按 technical 兜底
    {"id": "t4", "subject": "旧事实", "relation": "是", "object": "X",
     "source_role": "x", "confidence": 0.6, "created_at": iso_ago(500),
     "updated_at": iso_ago(500), "occurrences": 1},
]

s1 = kb._compute_staleness(kb._data["triples"][0])   # permanent
s2 = kb._compute_staleness(kb._data["triples"][1])   # technical 200天 > 6月
s3 = kb._compute_staleness(kb._data["triples"][2])   # security 120天 > 3月
s4 = kb._compute_staleness(kb._data["triples"][3])   # 老三元组兜底
check("permanent staleness = 0", s1 == 0.0, f"{s1}")
check("过期 technical staleness ≥ 1", s2 >= 1.0, f"{s2}")
check("过期 security staleness ≥ 1", s3 >= 1.0, f"{s3}")
check("老三元组(无 knowledge_type) 不崩溃", isinstance(s4, float), f"{s4}")

# search 新鲜度加权：放两个同关键词、不同新鲜度的三元组，过期者应排后
kb._data["triples"] = [
    {"id": "fresh", "subject": "框架", "relation": "是", "object": "新",
     "source_role": "x", "confidence": 0.8, "created_at": iso_ago(10),
     "updated_at": iso_ago(10), "occurrences": 1,
     "knowledge_type": "technical", "expires_at": "", "staleness": 0.0},
    {"id": "stale", "subject": "框架", "relation": "是", "object": "旧",
     "source_role": "x", "confidence": 0.8, "created_at": iso_ago(300),
     "updated_at": iso_ago(300), "occurrences": 1,
     "knowledge_type": "technical", "expires_at": "", "staleness": 0.0},
]
res = kb.search("框架 是", top_k=10)
top_id = res[0]["id"] if res else None
check("search 新鲜度加权：新鲜三元组排前", top_id == "fresh", f"top={top_id}")

# assembly_context 过期前缀
ctx = kb.assembly_context("框架 是", top_k=10)
content = ctx[0]["content"] if ctx else ""
check("assembly_context 过期三元组带 ⚠ 前缀", "⚠ 可能已过期" in content,
      f"content={content[:60]}")

# sweep_expired 只降权不删除（指向临时文件，避免污染真实 knowledge.json）
kb._path = Path(tempfile.mkdtemp(prefix="planc_kb_")) / "knowledge.json"
kb._data["triples"] = [
    {"id": "stale2", "subject": "库", "relation": "版本", "object": "旧",
     "source_role": "x", "confidence": 1.0, "created_at": iso_ago(300),
     "updated_at": iso_ago(300), "occurrences": 1,
     "knowledge_type": "technical", "expires_at": "", "staleness": 0.0},
]
n = kb.sweep_expired()
rec = kb._data["triples"][0]
check("sweep_expired 降权不删除", n == 1 and len(kb._data["triples"]) == 1
      and rec["confidence"] < 1.0, f"n={n} conf={rec['confidence']}")

# get_freshness_report
kb._data["triples"] = [
    {"id": "p", "subject": "用户", "relation": "偏好", "object": "中文",
     "source_role": "x", "confidence": 0.9, "created_at": iso_ago(400),
     "updated_at": iso_ago(400), "occurrences": 1,
     "knowledge_type": "permanent", "expires_at": "", "staleness": 0.0},
]
rep = kb.get_freshness_report()
check("get_freshness_report 返回状态", rep and rep[0]["status"] == "fresh",
      f"{rep}")

print("== C-4 experience_evaluator 接线 ==")
wg_off = {"id": "dev_full", "members": ["coach", "developer"],
          "pipeline": [{"step": 1, "role": "coach"}]}
out_off = M.MasterRole._apply_experience_eval_hook(None, wg_off, "dev_full")
check("members 无评估员 → 不追加", out_off[-1]["role"] != "experience_evaluator",
      f"last={out_off[-1].get('role')}")

wg_on = {"id": "dev_full",
         "members": ["coach", "developer", "experience_evaluator"],
         "pipeline": [{"step": 1, "role": "coach"}, {"step": 2, "role": "developer"}]}
out_on = M.MasterRole._apply_experience_eval_hook(None, wg_on, "dev_full")
check("members 含评估员 → 末尾追加评估员步骤",
      out_on[-1]["role"] == "experience_evaluator" and len(out_on) == 3,
      f"last={out_on[-1].get('role')} len={len(out_on)}")

# 非 dev 工作组不追加
wg_other = {"id": "research", "members": ["experience_evaluator"],
            "pipeline": [{"step": 1, "role": "knowledge_retriever"}]}
out_other = M.MasterRole._apply_experience_eval_hook(None, wg_other, "research")
check("非 dev 工作组 → 不追加", out_other[-1]["role"] != "experience_evaluator",
      f"last={out_other[-1].get('role')}")

print("\n========================================")
print(f"  Plan C 回归: PASS={PASS}  FAIL={FAIL}")
if NOTES:
    print("  -- 失败明细 --")
    for n in NOTES:
        print("   -", n)
print("========================================")
sys.exit(1 if FAIL else 0)
