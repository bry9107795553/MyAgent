#!/usr/bin/env python3
# =============================================================================
# 工具调用闭环回归测试
#
# 背景：工具实现层 / 注册表 / 网关三层都已完整，但闭环断在中间两环：
#   - 断点 A：没人把角色被授权的工具 schema 传给 gateway（tools 永远 None）
#   - 断点 B：没人消费 gateway 返回的 tool_calls（没有执行→回填→再请求循环）
#   此外还有一个隐藏根因：内置工具从未在运行时注册（core.tools 包未被任何
#   启动路径导入），导致 tool_registry 始终为空 —— 即使接上 A/B 也是空转。
#
# 本测试在进程内用假 LLM 客户端闭环验证，不依赖外部 mock llama-server。
#
# 验证项：
#   1. 内置工具已被注册（core.tools 包导入副作用）—— 否则闭环是空转
#   2. 断点 A：被授权角色（developer）的 LLM 调用确实带上了工具 schema
#   3. 断点 B：file_write 工具调用 → 真实落盘 → 结果回填 → 模型二次回答 → 返回最终文本
#   4. 最大轮次上限：模型死循环调工具时在第 5 轮强制结束，不卡死
#   5. 容错：参数非合法 JSON / 未知工具名 → 不崩，降级为普通回复
#   6. 未授权角色（coach，tools 全是虚构名）→ 不带 tools（行为与历史一致）
#   7. dev_full 七角色流水线在工具循环激活下照样跑通，零失败标记
#
# 用法： .venv-diag/Scripts/python.exe tests/regression_tool_loop.py
# =============================================================================
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

# 进入测试前清空相关环境变量，确保验证的是「默认值」而非「被设过的值」
for _k in ("SINGLE_GPU_MODE", "LLAMA_BASE_URL", "LLAMA_MODEL"):
    os.environ.pop(_k, None)

from types import SimpleNamespace

PASS = 0
FAIL = 0
NOTES = []
CLEANUP_FILES = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")
        NOTES.append(f"{name}: {detail}")


# ---------------------------------------------------------------------------
# 假 LLM 客户端（OpenAI 兼容）
# ---------------------------------------------------------------------------

def _msg(content, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


def _choice(message):
    return SimpleNamespace(message=message, finish_reason="stop")


def _resp(*messages):
    return SimpleNamespace(choices=[_choice(m) for m in messages])


def _tc(id, name, arguments):
    return SimpleNamespace(
        id=id, type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class _FakeCompletions:
    def __init__(self, script, recorder):
        self._script = list(script)
        self._recorder = recorder

    async def create(self, **kwargs):
        self._recorder.append(kwargs)
        if self._script:
            item = self._script.pop(0)
            return item(kwargs) if callable(item) else item
        return _resp(_msg("（默认回复）"))


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeModels:
    async def list(self):
        return SimpleNamespace(data=[SimpleNamespace(id="mock-model")])


class _FakeClient:
    def __init__(self, script, recorder):
        self.chat = _FakeChat(_FakeCompletions(script, recorder))
        self.models = _FakeModels()


def install_fake(script):
    """安装假客户端，返回 recorder（记录每次 chat.completions.create 的 kwargs）"""
    from core.llm.gateway import llm_gateway
    recorder = []
    fake = _FakeClient(script, recorder)
    llm_gateway._new_local_client = lambda base_url: fake
    llm_gateway._get_client = lambda base_url="": fake
    return recorder


# ---------------------------------------------------------------------------
# 1. 内置工具已注册（核心根因）
# ---------------------------------------------------------------------------
print("== 1. 内置工具注册 ==")

from core.role.loader import RoleLoader
from core.tools.base import tool_registry

loader = RoleLoader()
master = loader.load_all(session_id="regress_tool_loop")
roles = loader.roles

registered = tool_registry.list_all()
check("内置工具已注册（导入 core.tools 包副作用）",
      len(registered) >= 5, f"实际={registered}")
check("含 file_read / file_write / file_list / code_exec / web_search",
      {"file_read", "file_write", "file_list", "code_exec", "web_search"}.issubset(
          set(registered)),
      f"实际={registered}")

developer = roles["developer"]
dev_defs = tool_registry.get_tool_definitions(
    {"tools": {n: True for n in developer.tool_names}})
check("developer 拿到 4 个真实工具 schema（file_read/file_write/file_list/code_exec）",
      len(dev_defs) == 4
      and any(d["function"]["name"] == "file_write" for d in dev_defs),
      f"实际={[d['function']['name'] for d in dev_defs]}")


# ---------------------------------------------------------------------------
# 2. 断点 A + 3. 断点 B（完整闭环 + 真实落盘）
# ---------------------------------------------------------------------------
print("== 2/3. 断点 A/B：file_write 闭环落盘 ==")

from config.settings import settings

demo_rel = "demo_tool_test_out.txt"
demo_abs = os.path.join(settings.project_root, demo_rel)
CLEANUP_FILES.append(demo_abs)

rec = install_fake([
    # 第一轮：带工具 schema，模型要求写文件
    lambda kw: _resp(_msg(
        "我来创建文件。",
        [_tc("call_1", "file_write",
             json.dumps({"path": demo_rel, "content": "hello world from tool loop"}))])),
    # 第二轮：拿到工具结果后给出最终回复
    lambda kw: _resp(_msg("文件已成功写入。")),
])

out = asyncio.run(developer.execute(f"请写一个 {demo_rel} 文件，内容是 hello world"))

check("断点 A：developer 的 LLM 调用带上了工具 schema",
      bool(rec) and isinstance(rec[0].get("tools"), list) and len(rec[0]["tools"]) >= 4,
      f"tools={rec[0].get('tools') if rec else None}")
check("断点 B：发生了工具执行轮（共 2 次 LLM 调用）",
      len(rec) == 2, f"调用次数={len(rec)}")
check("file_write 真实落盘",
      os.path.exists(demo_abs)
      and "hello world from tool loop" in open(demo_abs, encoding="utf-8").read(),
      f"文件存在={os.path.exists(demo_abs)}")
check("最终返回的是第二轮文本（非工具调用轮）",
      out.strip() == "文件已成功写入。", f"实际={out!r}")


# ---------------------------------------------------------------------------
# 4. 最大轮次上限（防死循环占死 GPU）
# ---------------------------------------------------------------------------
print("== 4. 最大轮次上限 ==")

# 故意让模型每轮都要求调 file_read，验证第 5 轮强制结束
rec2 = install_fake([
    lambda kw: _resp(_msg("", [_tc(f"c{i}", "file_read",
        json.dumps({"path": "README.md"}))])) for i in range(20)
])
loop_out = asyncio.run(developer.execute("一直读 README"))
check("达到上限后强制结束（不无限循环）", len(rec2) == 5, f"调用次数={len(rec2)}")
check("无异常抛出 / 正常返回", isinstance(loop_out, str), f"返回={loop_out!r}")


# ---------------------------------------------------------------------------
# 5. 容错：参数非合法 JSON / 未知工具名
# ---------------------------------------------------------------------------
print("== 5. 容错 ==")

rec3 = install_fake([
    lambda kw: _resp(_msg("写文件", [_tc("call_x", "file_write", "{这不是合法json")])),
    lambda kw: _resp(_msg("已处理。")),
])
bad_json_file = os.path.join(settings.project_root, "demo_bad_json.txt")
CLEANUP_FILES.append(bad_json_file)
out3 = asyncio.run(developer.execute("写个文件（参数故意给错）"))
check("参数非合法 JSON → 不崩，降级为普通回复",
      out3.strip() == "已处理。", f"实际={out3!r}")
check("参数解析失败时不会误写文件",
      not os.path.exists(bad_json_file), f"误写文件={os.path.exists(bad_json_file)}")

rec4 = install_fake([
    lambda kw: _resp(_msg("调不存在的工具", [_tc("call_y", "nonexistent_tool", "{}")])),
    lambda kw: _resp(_msg("已处理。")),
])
out4 = asyncio.run(developer.execute("调一个不存在的工具"))
check("未知工具名 → 不崩，降级为普通回复",
      out4.strip() == "已处理。", f"实际={out4!r}")


# ---------------------------------------------------------------------------
# 6. 未授权角色不带 tools（与历史行为一致）
# ---------------------------------------------------------------------------
print("== 6. 未授权角色 ==")

coach = roles["coach"]
rec5 = install_fake([lambda kw: _resp(_msg("教练回复。"))])
out5 = asyncio.run(coach.execute("帮我做个需求分析"))
check("coach 的 tools 全是虚构名 → LLM 调用不带 tools（历史一致）",
      bool(rec5) and rec5[0].get("tools") is None,
      f"tools={rec5[0].get('tools') if rec5 else None}")
check("未授权角色正常返回文本", out5.strip() == "教练回复。", f"实际={out5!r}")


# ---------------------------------------------------------------------------
# 7. dev_full 流水线在工具循环激活下照样跑通
# ---------------------------------------------------------------------------
print("== 7. dev_full 流水线无回归 ==")

# 避免秘书后台 summary 任务在本次事件循环内产生噪声
from core.agent.orchestrator import secretary
secretary.should_summarize = lambda *a, **k: False

rec6 = install_fake([lambda kw: _resp(_msg("步骤完成。"))])


async def run_dev_full():
    from core.llm.gateway import llm_gateway
    await llm_gateway.init()
    check("gateway 连上（假）推理", llm_gateway.available, f"mode={llm_gateway.mode}")
    return await master.dispatch("开发一个带增删改查的待办事项 Web 应用")


result = asyncio.run(run_dev_full())
wg = result.get("workgroup")
content = result.get("content", "")
failed_marks = content.count("[执行失败]") + content.count("执行失败，已重试耗尽")
print(f"       roles_used = {result.get('roles_used')}")
print(f"       输出长度 = {len(content)}  失败标记 = {failed_marks}")
check("命中 dev_full 工作组", wg == "dev_full", f"实际={wg}")
check("流水线零失败/零降级步骤", failed_marks == 0, f"失败标记 x{failed_marks}")
check("流水线产出非空", len(content) > 200, f"len={len(content)}")
# developer 在流水线中确实带上了工具 schema（闭环对管线角色也生效）
dev_calls = [c for c in rec6 if isinstance(c.get("tools"), list) and c["tools"]]
check("dev_full 中 developer 的 LLM 调用带上了工具 schema（断点 A 在管线内也生效）",
      bool(dev_calls), f"带工具的调用数={len(dev_calls)}")


# ---------------------------------------------------------------------------
print("\n========================================")
print(f"  工具调用闭环回归: PASS={PASS}  FAIL={FAIL}")
if NOTES:
    print("  -- 失败明细 --")
    for n in NOTES:
        print("   -", n)
print("========================================")

# 清理测试落盘文件
for f in CLEANUP_FILES:
    try:
        if os.path.exists(f):
            os.remove(f)
    except Exception:
        pass

sys.exit(1 if FAIL else 0)
