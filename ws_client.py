#!/usr/bin/env python3
"""
WebSocket 端到端验证脚本（本地无 GPU 环境用）

用途：在 mock_llm.py（:8000 假推理端点）+ backend（uvicorn）都启动后，
      验证 WS 流式对话链路、工具调用闭环、记忆落盘、多 Agent 记忆隔离。

用法：
    python ws_client.py                      # 默认连 localhost:8088
    python ws_client.py --port 8080          # 指定后端端口
    python ws_client.py --skip-isolation     # 跳过第二个 Agent 隔离测试

依赖：websockets、httpx（已在 backend/requirements.txt 中）
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

try:
    import websockets
except ImportError:
    print("[FATAL] 缺少 websockets 依赖，请先 pip install -r backend/requirements.txt")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("[FATAL] 缺少 httpx 依赖，请先 pip install -r backend/requirements.txt")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent
AGENTS_DIR = PROJECT_ROOT / "data" / "agents"

# 统计
RESULTS = []


def record(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, ok, detail))
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}" + (f" — {detail}" if detail else ""))


def memory_path(agent_id: str) -> Path:
    return AGENTS_DIR / agent_id / "memory" / "chat_history.json"


def memory_len(agent_id: str) -> int:
    p = memory_path(agent_id)
    if not p.exists():
        return -1
    try:
        return len(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return -1


async def run_ws_round(base_ws: str, agent_id: str, message: str, timeout: float = 180.0):
    """跑一轮 WS 对话，返回 (帧类型计数, 拼接文本, meta列表, 错误)"""
    uri = f"{base_ws}/api/agents/{agent_id}/ws"
    frames = {}
    text_parts = []
    metas = []
    err = None

    try:
        async with websockets.connect(uri, max_size=None, open_timeout=15) as ws:
            await ws.send(json.dumps({"message": message}))
            started = time.time()
            while True:
                remain = timeout - (time.time() - started)
                if remain <= 0:
                    err = f"超时 {timeout}s 未收到 stream_end"
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remain)
                except asyncio.TimeoutError:
                    err = f"超时 {timeout}s 未收到 stream_end"
                    break

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    err = f"收到非 JSON 帧: {raw[:200]!r}"
                    break

                ftype = data.get("type", "<no-type>")
                frames[ftype] = frames.get(ftype, 0) + 1

                if ftype == "stream_token":
                    text_parts.append(data.get("content", ""))
                elif ftype == "stream_meta":
                    metas.append(data)
                elif ftype == "error":
                    err = f"服务端 error 帧: {data}"
                    break
                elif ftype == "stream_end":
                    break
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"

    return frames, "".join(text_parts), metas, err


async def ensure_agent(base_http: str, agent_id: str, name: str) -> bool:
    """确保测试用 Agent 存在（用于记忆隔离验证）"""
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.get(f"{base_http}/api/agents/{agent_id}")
        if r.status_code == 200:
            return True
        r = await cli.post(
            f"{base_http}/api/agents",
            json={
                "agent_id": agent_id,
                "name": name,
                "description": "WS 端到端验证专用临时 Agent",
                "template": "default",
                "system_prompt": "你是隔离测试助手。",
            },
        )
        if r.status_code in (200, 201):
            return True
        print(f"  [WARN] 创建 Agent {agent_id} 失败: {r.status_code} {r.text[:300]}")
        return False


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8088)
    ap.add_argument("--agent", default="general_assistant")
    ap.add_argument("--second-agent", default="ws_isolation_test")
    ap.add_argument("--skip-isolation", action="store_true")
    args = ap.parse_args()

    base_http = f"http://{args.host}:{args.port}"
    base_ws = f"ws://{args.host}:{args.port}"

    print("=" * 70)
    print(f"WebSocket 端到端验证  后端={base_http}  agent={args.agent}")
    print("=" * 70)

    # ---- 0. 健康检查 ----
    print("\n[0] 后端健康检查")
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.get(f"{base_http}/api/health")
            h = r.json()
        record("GET /api/health", r.status_code == 200, json.dumps(h, ensure_ascii=False))
        record("llm_available=true", bool(h.get("llm_available")),
               "假推理端点已被后端识别" if h.get("llm_available") else "LLM 网关未就绪，后续会 503")
    except Exception as e:  # noqa: BLE001
        record("GET /api/health", False, f"{type(e).__name__}: {e}")
        print("\n后端不可达，终止。")
        return 1

    # ---- 1. 普通流式对话 ----
    print("\n[1] 普通流式对话（不触发工具）")
    mem_before = memory_len(args.agent)
    frames, text, metas, err = await run_ws_round(
        base_ws, args.agent, "你好，用一句话介绍你自己"
    )
    record("WS 连接与收发", err is None, err or f"帧统计={frames}")
    record("收到 stream_start", frames.get("stream_start", 0) > 0)
    record("收到 stream_token 分块", frames.get("stream_token", 0) > 0,
           f"{frames.get('stream_token', 0)} 个 token 帧")
    record("收到 stream_end", frames.get("stream_end", 0) > 0)
    record("回复文本非空", len(text.strip()) > 0, f"前 80 字: {text.strip()[:80]}")
    if metas:
        record("收到 stream_meta", True, json.dumps(metas[0], ensure_ascii=False)[:200])

    await asyncio.sleep(1.0)
    mem_after = memory_len(args.agent)
    record("记忆已写入磁盘", mem_after > mem_before,
           f"chat_history.json 条数 {mem_before} -> {mem_after}")

    # ---- 2. 工具调用闭环 ----
    print("\n[2] 工具调用闭环（触发 file_write 落盘）")
    tool_out = PROJECT_ROOT / "data" / "projects" / "mock_tool_output.md"
    old_mtime = tool_out.stat().st_mtime if tool_out.exists() else 0
    frames2, text2, metas2, err2 = await run_ws_round(
        base_ws, args.agent, "帮我开发一个小工具，需要写文件到磁盘保存结果"
    )
    record("WS 工具轮次完成", err2 is None, err2 or f"帧统计={frames2}")
    record("回复文本非空", len(text2.strip()) > 0, f"长度 {len(text2)} 字")
    if metas2:
        m = metas2[0]
        record("dispatch_type/workgroup 元信息",
               bool(m.get("dispatch_type")),
               f"dispatch={m.get('dispatch_type')} workgroup={m.get('workgroup')} roles={m.get('roles_used')}")

    await asyncio.sleep(1.0)
    exists = tool_out.exists()
    new_mtime = tool_out.stat().st_mtime if exists else 0
    record("file_write 工具真实落盘", exists and new_mtime > old_mtime,
           f"{tool_out} 大小={tool_out.stat().st_size if exists else 0}B mtime变化={new_mtime > old_mtime}")

    # ---- 3. 历史接口 ----
    print("\n[3] 历史接口回读")
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.get(f"{base_http}/api/agents/{args.agent}/history")
        hist = r.json()
        n = len(hist.get("history", hist if isinstance(hist, list) else []))
        record("GET /{agent}/history", r.status_code == 200, f"返回 {n} 条")
    except Exception as e:  # noqa: BLE001
        record("GET /{agent}/history", False, f"{type(e).__name__}: {e}")

    # ---- 4. 多 Agent 记忆隔离 ----
    if not args.skip_isolation:
        print("\n[4] 角色切换 / 记忆隔离")
        ok = await ensure_agent(base_http, args.second_agent, "隔离测试助手")
        record("创建第二个 Agent", ok, args.second_agent)
        if ok:
            b_before = memory_len(args.second_agent)
            a_before = memory_len(args.agent)
            frames3, text3, _, err3 = await run_ws_round(
                base_ws, args.second_agent, "记住暗号：紫罗兰七号"
            )
            record("第二 Agent WS 对话", err3 is None, err3 or f"帧统计={frames3}")
            await asyncio.sleep(1.0)
            b_after = memory_len(args.second_agent)
            a_after = memory_len(args.agent)
            record("第二 Agent 记忆增长", b_after > b_before, f"{b_before} -> {b_after}")
            record("第一 Agent 记忆未被污染", a_after == a_before, f"{a_before} -> {a_after}")
            record("记忆文件物理隔离",
                   memory_path(args.agent) != memory_path(args.second_agent),
                   f"{memory_path(args.second_agent).relative_to(PROJECT_ROOT)}")

    # ---- 5. 异常协议：空消息 ----
    print("\n[5] 异常输入健壮性（空消息体）")
    uri = f"{base_ws}/api/agents/{args.agent}/ws"
    try:
        async with websockets.connect(uri, open_timeout=15) as ws:
            await ws.send(json.dumps({}))
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=20)
                record("空 message 未导致连接崩溃", True, f"服务端回应: {raw[:150]}")
            except asyncio.TimeoutError:
                record("空 message 未导致连接崩溃", True, "服务端静默忽略（连接保持）")
    except Exception as e:  # noqa: BLE001
        record("空 message 未导致连接崩溃", False, f"{type(e).__name__}: {e}")

    # ---- 汇总 ----
    print("\n" + "=" * 70)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"结果: {passed}/{total} 通过")
    fails = [(n, d) for n, ok, d in RESULTS if not ok]
    if fails:
        print("失败项：")
        for n, d in fails:
            print(f"  - {n}: {d}")
    print("=" * 70)
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
