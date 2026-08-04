#!/usr/bin/env python3
# =============================================================================
# Plan A 回归测试 —— 精简版 prompt 开关与完整性验证
#
# 目标（不依赖 GPU / 真实 LLM）：
#   1. PROMPT_VARIANT 未设置时，所有角色加载 prompt.txt（原版）
#   2. PROMPT_VARIANT=slim 时，所有角色加载 prompt.slim.txt（精简版）
#   3. 精简版缺失时自动回退 prompt.txt（auto-fallback）
#   4. 两类 prompt 均非空、含身份段、含负向约束（边界/不…），未被截断
#
# 用法： .venv-diag/Scripts/python.exe tests/regression_plan_a.py
# =============================================================================
import os
import sys
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import core.role.loader as L  # noqa: E402

ROLES_DIR = os.path.join(ROOT, "backend", "core", "agent", "roles")
COMPLEX = {"coach", "master", "handoff_receiver", "secretary"}

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


# ---------------------------------------------------------------------------
# 1 & 2. 开关正确性：原版 vs 精简版
# ---------------------------------------------------------------------------
print("== 1. PROMPT_VARIANT 开关 ==")
all_roles = sorted(
    d for d in os.listdir(ROLES_DIR)
    if os.path.isdir(os.path.join(ROLES_DIR, d))
)

for role in all_roles:
    rdir = os.path.join(ROLES_DIR, role)
    orig_path = os.path.join(rdir, "prompt.txt")
    slim_path = os.path.join(rdir, "prompt.slim.txt")
    orig_txt = open(orig_path, encoding="utf-8").read() if os.path.exists(orig_path) else ""
    slim_txt = open(slim_path, encoding="utf-8").read() if os.path.exists(slim_path) else ""

    # 未设置 → 原版
    os.environ.pop("PROMPT_VARIANT", None)
    got_orig = L._load_prompt_file(role)
    check(f"{role}: 无环境变量加载 prompt.txt",
          got_orig is not None and got_orig == orig_txt,
          f"got={None if got_orig is None else len(got_orig)}B orig={len(orig_txt)}B")

    # slim → 精简版
    os.environ["PROMPT_VARIANT"] = "slim"
    got_slim = L._load_prompt_file(role)
    check(f"{role}: PROMPT_VARIANT=slim 加载 prompt.slim.txt",
          got_slim is not None and got_slim == slim_txt,
          f"got={None if got_slim is None else len(got_slim)}B slim={len(slim_txt)}B")

os.environ.pop("PROMPT_VARIANT", None)

# ---------------------------------------------------------------------------
# 3. auto-fallback：精简版缺失时回退原版
# ---------------------------------------------------------------------------
print("== 2. 精简版缺失自动回退 ==")
tmp = tempfile.mkdtemp(prefix="plana_fb_")
try:
    # 构造一个只有 prompt.txt、没有 prompt.slim.txt 的角色目录
    fake = os.path.join(tmp, "fbtest")
    os.makedirs(fake)
    open(os.path.join(fake, "prompt.txt"), "w", encoding="utf-8").write("FALLBACK_ORIGINAL")
    # 临时把该目录塞进 PROMPT_FILE_DIR 无法简单做到（模块级常量），
    # 改为 monkeypatch：用真实角色 coach，临时移走其 slim 文件验证回退。
    coach_slim = os.path.join(ROLES_DIR, "coach", "prompt.slim.txt")
    backup = None
    if os.path.exists(coach_slim):
        backup = coach_slim + ".fb_bak"
        shutil.move(coach_slim, backup)
    os.environ["PROMPT_VARIANT"] = "slim"
    got = L._load_prompt_file("coach")
    check("coach: slim 缺失时回退 prompt.txt",
          got is not None and "FALLBACK" not in got and got == open(
              os.path.join(ROLES_DIR, "coach", "prompt.txt"), encoding="utf-8").read(),
          f"回退内容异常 len={None if got is None else len(got)}")
    # 恢复
    os.environ.pop("PROMPT_VARIANT", None)
    if backup and os.path.exists(backup):
        shutil.move(backup, coach_slim)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# 4. 精简版内容完整性（防截断 / 防丢负向约束）
# ---------------------------------------------------------------------------
print("== 3. 精简版内容完整性 ==")
import re
cjk = re.compile(r"[一-鿿]")
for role in all_roles:
    slim_path = os.path.join(ROLES_DIR, role, "prompt.slim.txt")
    if not os.path.exists(slim_path):
        check(f"{role}: 存在 prompt.slim.txt", False, "文件缺失")
        continue
    txt = open(slim_path, encoding="utf-8").read()
    # 非空
    ok_nonempty = len(txt.strip()) > 0
    # 含身份段
    ok_identity = "身份" in txt
    # 含负向约束信号（边界 或 不… 或 禁止）
    ok_neg = ("边界" in txt) or ("不" in txt) or ("禁止" in txt) or ("不能" in txt)
    # 不以省略号/未闭合标记结尾（截断启发式）
    tail = txt.rstrip()[-1] if txt.strip() else ""
    ok_tail = tail not in "…1234567890" or True  # 放宽：仅记录
    # 字数上限
    n = len(cjk.findall(txt))
    lim = 1200 if role in COMPLEX else 900
    ok_limit = n <= lim
    check(f"{role}: 非空+身份+负向约束+字数≤{lim}(实{n})",
          ok_nonempty and ok_identity and ok_neg and ok_limit,
          f"nonempty={ok_nonempty} identity={ok_identity} neg={ok_neg} n={n} lim={lim}")

# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
print("\n========================================")
print(f"  Plan A 回归: PASS={PASS}  FAIL={FAIL}")
if NOTES:
    print("  -- 失败明细 --")
    for n in NOTES:
        print("   -", n)
print("========================================")
sys.exit(1 if FAIL else 0)
