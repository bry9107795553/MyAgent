"""
mock_llm.py — 假推理端点（本地无 GPU 验证专用）
================================================================================
用途
    在**没有 AMD GPU / 没有 llama.cpp** 的机器上，把 MyAgent 后端完整跑通。
    它冒充 llama-server 的 OpenAI 兼容接口，让 backend 的 LLMGateway 认为
    "本地推理已就绪"，从而消除 `503 LLM 推理引擎未就绪`，
    使路由 / 角色调度 / 工具闭环 / WebSocket 流式 / 记忆落盘全链路可被验证。

    ⚠ 它**不做任何真实推理**。回复是模板拼装的。
    真实部署（Radeon Cloud）时请勿启动本文件 —— 用 setup_amd_cloud.sh
    起 ROCm 版 llama-server 占用同一个 :8000 端口即可，后端零改动。

实现的契约（与 backend/config/settings.py 对齐）
    GET  /v1/models              → 返回含 Qwen2.5-14B-Instruct 的模型列表
    POST /v1/chat/completions    → stream=false 整段返回 / stream=true SSE 分块
    GET  /health                 → 容器健康检查用（非 OpenAI 协议，额外提供）

    api_key 一律忽略（后端传 "EMPTY"）。

工具调用（function calling）模拟
    后端 RoleBase._run_tool_loop() 依赖模型主动返回 tool_calls 才能验证工具闭环。
    本 mock 的策略：
        1. messages 中已存在 role="tool" 的消息 → 说明工具已执行完
           → 返回一段"总结型"文本，结束循环（避免死循环打满 MAX_TOOL_ITERATIONS）
        2. 否则，若请求带了 tools 且用户文本命中触发词（写文件/file_write/落盘...）
           → 返回一个 file_write 的 tool_call，让后端真的去写磁盘
        3. 其余情况 → 返回普通文本

    触发词可通过环境变量 MOCK_TOOL_TRIGGER 覆盖（逗号分隔）。

启动
    python mock_llm.py                 # 默认 0.0.0.0:8000
    MOCK_LLM_PORT=8000 python mock_llm.py
纯标准库实现，无第三方依赖。
"""
import json
import os
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ===== 配置 =====

MODEL_NAME = os.getenv("MOCK_LLM_MODEL", "Qwen2.5-14B-Instruct")
HOST = os.getenv("MOCK_LLM_HOST", "0.0.0.0")
PORT = int(os.getenv("MOCK_LLM_PORT", "8000"))

# 命中这些词且模型被授权 file_write 时，返回 tool_call（用于端到端验证工具闭环）
DEFAULT_TRIGGERS = "写文件,写入文件,file_write,落盘,生成文件,创建文件,保存到文件"
TOOL_TRIGGERS = [
    t.strip()
    for t in os.getenv("MOCK_TOOL_TRIGGER", DEFAULT_TRIGGERS).split(",")
    if t.strip()
]

# 流式分块大小（字符）——模拟逐 token 推送
STREAM_CHUNK_SIZE = int(os.getenv("MOCK_STREAM_CHUNK", "6"))


# ===== 回复生成 =====

def _last_user_text(messages: list) -> str:
    """取最后一条 user 消息的文本"""
    for m in reversed(messages or []):
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, list):
                # 兼容多模态数组格式
                return " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict)
                )
            return content or ""
    return ""


def _role_hint(messages: list) -> str:
    """从 system prompt 里粗略提取角色名，让 mock 回复带上角色标识，便于肉眼核对调度链路"""
    for m in messages or []:
        if m.get("role") != "system":
            continue
        text = m.get("content") or ""
        match = re.search(r"你是[「『\"]?([^」』\"\n，。—]{2,12})", text)
        if match:
            return match.group(1).strip()
    return "本地模型"


def _has_tool_result(messages: list) -> bool:
    """messages 中是否已有工具执行结果（role=tool）"""
    return any(m.get("role") == "tool" for m in messages or [])


def _authorized_tools(tools) -> set:
    """从请求的 tools 数组里取出被授权的函数名集合"""
    names = set()
    for t in tools or []:
        fn = (t or {}).get("function") or {}
        if fn.get("name"):
            names.add(fn["name"])
    return names


def _should_call_tool(messages: list, tools) -> bool:
    """判断本轮是否应该返回 tool_call"""
    if _has_tool_result(messages):
        return False
    if "file_write" not in _authorized_tools(tools):
        return False
    # 触发词在整个对话里找（任务包由主控拼装，用户原文会被包在 task 里）
    haystack = " ".join(
        str(m.get("content") or "") for m in messages or []
        if m.get("role") in ("user", "system")
    )
    return any(trigger in haystack for trigger in TOOL_TRIGGERS)


def _build_tool_call(messages: list) -> dict:
    """构造一个 file_write 的 tool_call（写到 data/projects/ 下，路径在项目根内）"""
    user_text = _last_user_text(messages)
    args = {
        "path": os.getenv("MOCK_TOOL_PATH", "data/projects/mock_tool_output.md"),
        "content": (
            "# Mock 工具调用产物\n\n"
            f"- 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- 触发消息: {user_text[:200]}\n"
            "- 来源: mock_llm.py 模拟的 file_write function call\n"
            "\n该文件的存在证明「模型 → tool_calls → 工具注册表 → 磁盘」闭环通畅。\n"
        ),
    }
    return {
        "id": f"call_{uuid.uuid4().hex[:16]}",
        "type": "function",
        "function": {
            "name": "file_write",
            "arguments": json.dumps(args, ensure_ascii=False),
        },
    }


def _build_text_reply(messages: list) -> str:
    """构造一段普通文本回复"""
    role = _role_hint(messages)
    user_text = _last_user_text(messages).strip()
    if _has_tool_result(messages):
        return (
            f"[{role} · mock] 工具已执行完毕，结果已回填。\n"
            "文件写入成功，闭环验证通过。本条回复由 mock_llm.py 生成，不含真实推理。"
        )
    snippet = user_text[:120].replace("\n", " ")
    return (
        f"[{role} · mock] 已收到任务：{snippet}\n"
        "这是假推理端点返回的占位回复，用于验证路由、调度、流式与记忆链路。\n"
        "真实部署时本端点会被 ROCm 版 llama-server 替换，届时此处为真实模型输出。"
    )


# ===== HTTP 处理 =====

class MockLLMHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "mock-llama-server/1.0"

    # ---- 工具方法 ----

    def _send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        # SSE 长度未知 → 必须用分块传输，否则 HTTP/1.1 客户端会一直等
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

    def _write_chunk(self, text: str):
        """按 HTTP chunked 编码写一段数据"""
        data = text.encode("utf-8")
        self.wfile.write(f"{len(data):X}\r\n".encode("ascii"))
        self.wfile.write(data)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def _end_chunks(self):
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def log_message(self, fmt, *args):
        print(f"[mock-llm] {self.address_string()} {fmt % args}")

    # ---- 路由 ----

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("/v1/models", "/models"):
            self._send_json({
                "object": "list",
                "data": [{
                    "id": MODEL_NAME,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "llama-cpp-mock",
                }],
            })
        elif path in ("/health", "/v1/health", ""):
            self._send_json({"status": "ok", "model": MODEL_NAME, "mock": True})
        else:
            self._send_json({"error": {"message": f"Not Found: {self.path}"}}, 404)

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json({"error": {"message": "invalid JSON body"}}, 400)
            return

        if path in ("/v1/chat/completions", "/chat/completions"):
            self._handle_chat(payload)
        elif path in ("/v1/completions", "/completions"):
            # 少数客户端会打 legacy completions，给个兜底
            self._handle_chat(payload)
        else:
            self._send_json({"error": {"message": f"Not Found: {self.path}"}}, 404)

    # ---- chat/completions ----

    def _handle_chat(self, payload: dict):
        messages = payload.get("messages") or []
        tools = payload.get("tools")
        stream = bool(payload.get("stream"))
        model = payload.get("model") or MODEL_NAME

        want_tool = _should_call_tool(messages, tools)

        if stream:
            # 流式路径不模拟 tool_calls（后端 chat_stream 也不传 tools）
            self._stream_reply(_build_text_reply(messages), model)
            return

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())

        if want_tool:
            tool_call = _build_tool_call(messages)
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [tool_call],
            }
            finish_reason = "tool_calls"
            print(f"[mock-llm] → 返回 tool_call: {tool_call['function']['name']}")
        else:
            message = {"role": "assistant", "content": _build_text_reply(messages)}
            finish_reason = "stop"

        self._send_json({
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "message": message,
                "logprobs": None,
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": sum(len(str(m.get("content") or "")) for m in messages) // 4,
                "completion_tokens": 64,
                "total_tokens": 128,
            },
        })

    def _stream_reply(self, text: str, model: str):
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())

        def frame(delta: dict, finish=None):
            return "data: " + json.dumps({
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": delta,
                    "logprobs": None,
                    "finish_reason": finish,
                }],
            }, ensure_ascii=False) + "\n\n"

        try:
            self._send_sse_headers()
            # 首帧带 role
            self._write_chunk(frame({"role": "assistant", "content": ""}))
            for i in range(0, len(text), STREAM_CHUNK_SIZE):
                self._write_chunk(frame({"content": text[i:i + STREAM_CHUNK_SIZE]}))
            self._write_chunk(frame({}, finish="stop"))
            self._write_chunk("data: [DONE]\n\n")
            self._end_chunks()
        except (BrokenPipeError, ConnectionResetError):
            print("[mock-llm] 客户端提前断开流式连接")


def main():
    server = ThreadingHTTPServer((HOST, PORT), MockLLMHandler)
    server.daemon_threads = True
    print("=" * 62)
    print("  mock_llm — 假推理端点 (无 GPU 本地验证专用)")
    print(f"  监听:   http://{HOST}:{PORT}/v1")
    print(f"  模型名: {MODEL_NAME}")
    print(f"  工具触发词: {TOOL_TRIGGERS}")
    print("  ⚠ 不做真实推理；真实部署请改用 ROCm 版 llama-server")
    print("=" * 62)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[mock-llm] 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
