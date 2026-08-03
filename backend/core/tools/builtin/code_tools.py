"""
代码执行工具 — 执行 Python 代码
- CodeExecTool: 使用 subprocess 执行 Python 代码 (有超时限制)

安全说明:
    - 代码在独立子进程中执行，通过超时机制防止死循环
    - 执行结果包含 stdout / stderr / return_code
    - 默认超时 10 秒，最大不超过 30 秒
"""
import sys
import asyncio
import tempfile
from pathlib import Path
from typing import Optional

from core.tools.base import BaseTool


class CodeExecTool(BaseTool):
    """Python 代码执行工具"""

    # 默认超时时间 (秒)
    DEFAULT_TIMEOUT = 10
    # 最大超时时间 (秒) — 防止 LLM 传入过大值
    MAX_TIMEOUT = 30
    # 最大输出长度 (字符) — 防止输出过长导致上下文溢出
    MAX_OUTPUT_LENGTH = 10000

    @property
    def name(self) -> str:
        return "code_exec"

    @property
    def description(self) -> str:
        return (
            "执行一段 Python 代码并返回输出结果。"
            "适用于数学计算、数据处理、快速验证等场景。"
            f"代码在独立子进程中运行，默认超时 {self.DEFAULT_TIMEOUT} 秒。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的 Python 代码",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"执行超时时间 (秒)，默认 {self.DEFAULT_TIMEOUT}，最大 {self.MAX_TIMEOUT}",
                    "default": self.DEFAULT_TIMEOUT,
                },
            },
            "required": ["code"],
        }

    async def execute(
        self,
        code: str,
        timeout: Optional[int] = None,
    ) -> dict:
        """执行 Python 代码

        :param code: Python 代码字符串
        :param timeout: 超时时间 (秒)
        :return: {"success": bool, "stdout": str, "stderr": str, "return_code": int}
        """
        # 限制超时时间
        exec_timeout = min(timeout or self.DEFAULT_TIMEOUT, self.MAX_TIMEOUT)

        # 将代码写入临时文件后执行 (避免 -c 模式的转义问题)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(code)
            tmp_path = Path(tmp.name)

        try:
            # 使用当前 Python 解释器执行
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(tmp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=exec_timeout,
                )
            except asyncio.TimeoutError:
                # 超时则终止子进程
                process.kill()
                await process.wait()
                return {
                    "success": False,
                    "error": f"代码执行超时 (超过 {exec_timeout} 秒)",
                    "stdout": "",
                    "stderr": "",
                    "return_code": -1,
                }

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            return_code = process.returncode

            # 截断过长的输出
            truncated = False
            if len(stdout) > self.MAX_OUTPUT_LENGTH:
                stdout = stdout[: self.MAX_OUTPUT_LENGTH] + "\n... [输出已截断]"
                truncated = True
            if len(stderr) > self.MAX_OUTPUT_LENGTH:
                stderr = stderr[: self.MAX_OUTPUT_LENGTH] + "\n... [错误输出已截断]"
                truncated = True

            return {
                "success": return_code == 0,
                "stdout": stdout,
                "stderr": stderr,
                "return_code": return_code,
                "truncated": truncated,
            }

        except Exception as e:
            return {"success": False, "error": f"代码执行失败: {e}"}
        finally:
            # 清理临时文件
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
