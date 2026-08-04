#!/usr/bin/env python3
# =============================================================================
# 单 GPU 模式回归测试
#
# 背景：交付环境是 Radeon Cloud 单卡实例（Radeon PRO W7900 / 48GB），
#       只会起 1 个 llama-server (:8000)。历史上 single_gpu_mode 默认 False，
#       导致 gpu_affinity=gpu1/gpu2 的 11 个角色会去连 8001/8002 ——
#       部署阶段完全正常，跑到多角色流水线中途才 Connection refused。
#       本测试把「默认即单卡」这件事钉死。
#
# 验证项：
#   1. 不设任何环境变量时，settings.single_gpu_mode 默认为 True
#   2. 单卡模式下 resolve_inference_url() 对 gpu0/gpu1/gpu2/未知 一律回落到
#      llama_base_url，且随 LLAMA_BASE_URL 变动（不硬编码 8000）
#   3. 全部 18 个角色实例的实际推理端点都是同一个，无一指向 8001/8002
#   4. dev_full 九步流水线端到端跑通（mock 推理），全程零 8001/8002 连接
#      —— 用 gateway 客户端工厂埋点抓取所有被请求过的 base_url
#   5. 标注 model=vision / 非 text 的角色不会把该值当作模型名发给 llama-server
#      （gateway 恒定使用 settings.llama_model，不会产生 400 unknown model）
#   6. 多 GPU 能力仍然保留：SINGLE_GPU_MODE=false 时 gpu1→8001 / gpu2→8002
#
# 前置：mock llama-server 监听 127.0.0.1:8000（仅此一个端口，故意不起 8001/8002，
#       任何越界路由都会立刻表现为连接失败）
#
# 用法： .venv-diag/Scripts/python.exe tests/regression_single_gpu.py
# =============================================================================
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

# 关键：进入测试前清空相关环境变量，确保验证的是「默认值」而不是「被设过的值」
for _k in ("SINGLE_GPU_MODE", "LLAMA_BASE_URL", "LLAMA_MODEL"):
    os.environ.pop(_k, None)

PASS = 0
FAIL = 0
NOTES: list[str] = []


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
# 1. 默认值：不设环境变量即单卡
# ---------------------------------------------------------------------------
print("== 1. 默认即单卡 ==")

from config.settings import Settings, settings, MULTI_GPU_ENDPOINTS  # noqa: E402

fresh = Settings(_env_file=None)
check("Settings 默认 single_gpu_mode=True（无需任何环境变量）",
      fresh.single_gpu_mode is True,
      f"实际={fresh.single_gpu_mode}")
check("全局单例 settings.single_gpu_mode=True",
      settings.single_gpu_mode is True,
      f"实际={settings.single_gpu_mode}")

# ---------------------------------------------------------------------------
# 2. 路由解析：单卡模式无视亲和性
# ---------------------------------------------------------------------------
print("== 2. resolve_inference_url 单卡回落 ==")

for aff in ("gpu0", "gpu1", "gpu2", "gpu7", ""):
    url = settings.resolve_inference_url(aff)
    check(f"affinity={aff or '(空)'} → {url}",
          url == settings.llama_base_url,
          f"期望 {settings.llama_base_url}")

# 不硬编码 8000：改 base_url 后路由必须跟随
moved = Settings(_env_file=None, llama_base_url="http://127.0.0.1:8123/v1")
check("改 LLAMA_BASE_URL 后单卡路由跟随（未硬编码 8000）",
      moved.resolve_inference_url("gpu2") == "http://127.0.0.1:8123/v1",
      f"实际={moved.resolve_inference_url('gpu2')}")

# ---------------------------------------------------------------------------
# 3. 全部角色实例端点一致
# ---------------------------------------------------------------------------
print("== 3. 角色实例端点 ==")

from core.role.loader import RoleLoader  # noqa: E402

loader = RoleLoader()
master = loader.load_all(session_id="regress_single_gpu")
roles = loader.roles

check("role_pool 角色全部加载", len(roles) == 18, f"实际={len(roles)}")

bad = {rid: r._get_gpu_url() for rid, r in roles.items()
       if r._get_gpu_url() != settings.llama_base_url}
check(f"全部 {len(roles)} 个角色都指向 {settings.llama_base_url}",
      not bad, f"越界角色={bad}")

# 单独点名原本亲和 gpu1 / gpu2 的角色（这些正是历史上会炸的）
GPU1_ROLES = ["knowledge_retriever", "scheduler", "translator", "visual_analyzer"]
GPU2_ROLES = ["quality_checker", "inspector", "tester", "deployer",
              "cleaner", "hr_manager", "experience_evaluator"]
for rid in GPU1_ROLES + GPU2_ROLES:
    r = roles.get(rid)
    url = r._get_gpu_url() if r else None
    check(f"{rid}(亲和 {r.gpu_affinity if r else '?'}) 不再走 8001/8002",
          url == settings.llama_base_url,
          f"实际={url}")

# ---------------------------------------------------------------------------
# 4. 非 text 模型角色不会把 model 字段当模型名发出去
# ---------------------------------------------------------------------------
print("== 4. vision / 非 text 角色的模型名 ==")

from core.llm.gateway import llm_gateway  # noqa: E402

nontext = {rid: r.model_type for rid, r in roles.items()
           if getattr(r, "model_type", "text") != "text"}
print(f"       非 text 角色: {nontext or '无'}")
check("gateway 模型名恒为 settings.llama_model（不会用角色的 model 字段）",
      llm_gateway._get_model_name("") == settings.llama_model
      and llm_gateway._get_model_name("http://localhost:8001/v1") == settings.llama_model,
      f"实际={llm_gateway._get_model_name('')}")
check("因此 model=vision 的角色不会触发 400 unknown model",
      all(v in ("vision", "text") for v in nontext.values()) or not nontext,
      f"非 text 角色={nontext}")

# ---------------------------------------------------------------------------
# 5. dev_full 端到端 + 端点埋点
# ---------------------------------------------------------------------------
print("== 5. dev_full 九步流水线（mock 推理） ==")

# 埋点：记录 gateway 实际创建过的所有本机客户端 base_url
SEEN_URLS: list[str] = []
_orig_new_client = llm_gateway._new_local_client


def _spy_new_client(base_url: str):
    SEEN_URLS.append(base_url)
    return _orig_new_client(base_url)


llm_gateway._new_local_client = _spy_new_client  # type: ignore[method-assign]

_orig_get_client = llm_gateway._get_client


def _spy_get_client(base_url: str = ""):
    SEEN_URLS.append(base_url or settings.llama_base_url)
    return _orig_get_client(base_url)


llm_gateway._get_client = _spy_get_client  # type: ignore[method-assign]


async def run_pipeline():
    await llm_gateway.init()
    check("gateway 连上 mock llama-server", llm_gateway.available,
          f"mode={llm_gateway.mode}")
    return await master.dispatch("开发一个带增删改查的待办事项 Web 应用")


result = asyncio.run(run_pipeline())

wg = result.get("workgroup")
content = result.get("content", "")
check("命中 dev_full 工作组", wg == "dev_full", f"实际={wg}")

# 步骤统计。注意要同时数两种失败标记：
#   "[执行失败]"          —— 步骤级失败
#   "执行失败，已重试耗尽"  —— _degrade() 的降级文案
# 只数前者会漏判：角色连不上时管线仍会「成功」返回，失败被降级文案吞掉，
# 这正是「部署没报错、演示中途才发现半个团队没干活」的表现形式。
step_marks = content.count("步骤") or content.count("Step")
failed_marks = content.count("[执行失败]") + content.count("执行失败，已重试耗尽")
print(f"       roles_used = {result.get('roles_used')}")
print(f"       输出长度 = {len(content)}  步骤标记 = {step_marks}  失败标记 = {failed_marks}")
check("流水线零失败/零降级步骤", failed_marks == 0, f"失败或降级标记 x{failed_marks}")
check("流水线产出非空", len(content) > 200, f"len={len(content)}")

offenders = sorted({u for u in SEEN_URLS if ":8001" in u or ":8002" in u})
print(f"       本轮实际访问过的端点: {sorted(set(SEEN_URLS))}")
check("全程零 8001/8002 连接", not offenders, f"越界端点={offenders}")

# ---------------------------------------------------------------------------
# 6. 多 GPU 能力保留（显式关闭单卡后应恢复三卡分流）
# ---------------------------------------------------------------------------
print("== 6. 多 GPU 能力仍然保留 ==")

multi = Settings(_env_file=None, single_gpu_mode=False)
check("SINGLE_GPU_MODE=false → gpu0 走 8000",
      multi.resolve_inference_url("gpu0") == MULTI_GPU_ENDPOINTS["gpu0"],
      f"实际={multi.resolve_inference_url('gpu0')}")
check("SINGLE_GPU_MODE=false → gpu1 走 8001",
      multi.resolve_inference_url("gpu1") == MULTI_GPU_ENDPOINTS["gpu1"],
      f"实际={multi.resolve_inference_url('gpu1')}")
check("SINGLE_GPU_MODE=false → gpu2 走 8002",
      multi.resolve_inference_url("gpu2") == MULTI_GPU_ENDPOINTS["gpu2"],
      f"实际={multi.resolve_inference_url('gpu2')}")

os.environ["SINGLE_GPU_MODE"] = "false"
env_multi = Settings(_env_file=None)
check("环境变量 SINGLE_GPU_MODE=false 可关闭单卡模式",
      env_multi.single_gpu_mode is False,
      f"实际={env_multi.single_gpu_mode}")
os.environ.pop("SINGLE_GPU_MODE", None)

# ---------------------------------------------------------------------------
print("\n========================================")
print(f"  单 GPU 模式回归: PASS={PASS}  FAIL={FAIL}")
if NOTES:
    print("  -- 失败明细 --")
    for n in NOTES:
        print("   -", n)
print("========================================")
sys.exit(1 if FAIL else 0)
