"""開發教練引導式多 Agent 協調器 (含秘書機制)"""
from __future__ import annotations

import asyncio
import json, os, re
from typing import Any, Dict, Optional

from .workflow_state import WorkflowPhase, WorkflowState
from .secretary import secretary, Secretary


class DevCoachOrchestrator:
    """
    開發教練引導式多 Agent 協調器

    整合了秘書機制（Secretary），實現:
        - 每輪對話後自動記錄 (否定檢測 + 失敗檢測)
        - 每 5 輪自動生成增量摘要
        - 連續失敗/否定達到閾值時觸發糾錯注入
    """

    def __init__(self, agent_manager, llm=None, config=None):
        self.agent_manager = agent_manager
        self.llm = llm
        self.config = config
        self._states: Dict[str, WorkflowState] = {}
        self._state_dir = (
            config.resolve(config.paths.data_dir)
            if config and hasattr(config, "paths")
            else "data"
        )

        # 秘書初始化 (延遲到首次 handle_message 時按 session_id 初始化)
        self._secretary_initialized: Dict[str, bool] = {}

    # ------------------------------------------------------------------ #
    # 狀態持久化
    # ------------------------------------------------------------------ #

    def _get_state_file(self, session_id):
        return os.path.join(self._state_dir, "sessions", f"workflow_{session_id}.json")

    def _load_state(self, session_id) -> WorkflowState:
        fn = self._get_state_file(session_id)
        if os.path.exists(fn):
            try:
                with open(fn, encoding="utf-8") as f:
                    return WorkflowState.from_dict(json.load(f))
            except Exception:
                pass
        return WorkflowState(session_id=session_id)

    def _save_state(self, state: WorkflowState):
        os.makedirs(
            os.path.dirname(self._get_state_file(state.session_id)), exist_ok=True
        )
        with open(self._get_state_file(state.session_id), "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)

    def get_state(self, session_id) -> WorkflowState:
        if session_id not in self._states:
            self._states[session_id] = self._load_state(session_id)
        return self._states[session_id]

    def _update_state(self, state: WorkflowState):
        self._states[state.session_id] = state
        self._save_state(state)

    # ------------------------------------------------------------------ #
    # 秘書集成
    # ------------------------------------------------------------------ #

    def _ensure_secretary(self, session_id: str):
        """確保秘書已為此 session 初始化"""
        if session_id not in self._secretary_initialized:
            # 構建 LLM 調用包裝器
            async def _llm_wrapper(messages):
                if self.llm:
                    try:
                        # 嘗試非流式調用
                        return self.llm.complete(messages[-1]["content"])
                    except Exception:
                        try:
                            return self.llm.chat(messages)
                        except Exception:
                            pass
                return ""

            secretary.init(
                session_id,
                llm_call=_llm_wrapper,
                state_dir=self._state_dir,
            )
            self._secretary_initialized[session_id] = True
            print(f"[Orchestrator] 秘書已就緒 | 會話: {session_id}")

    # ------------------------------------------------------------------ #
    # 消息處理 (含秘書記錄)
    # ------------------------------------------------------------------ #

    def handle_message(
        self, user_input: str, session_id: str = "default"
    ) -> Dict[str, Any]:
        """
        處理用戶消息

        流程:
            1. 初始化秘書 (首次)
            2. 檢查秘書糾錯注入
            3. 根據工作流階段處理
            4. 秘書記錄本輪對話
        """
        # 1. 確保秘書就緒
        self._ensure_secretary(session_id)

        # 2. 檢查糾錯注入
        correction = secretary.check_correction()
        if correction:
            # 將糾錯提示注入用戶消息前綴
            user_input = correction + "\n\n---\n用戶消息: " + user_input

        # 3. 獲取工作流狀態
        state = self.get_state(session_id)

        # 4. 根據階段處理
        result: Dict[str, Any]
        if state.phase == WorkflowPhase.IDLE:
            result = self._start_new_task(user_input, state)
        else:
            # 其他階段暫用通用處理
            result = self._handle_general(user_input, state)

        # 5. 秘書記錄本輪
        secretary.record_turn(
            user_message=user_input,
            role_response=result.get("content", ""),
            role_id=result.get("phase", "orchestrator"),
        )

        # 6. 檢查是否需要摘要 (非阻塞)
        if secretary.should_summarize():
            try:
                asyncio.create_task(secretary.generate_summary())
            except RuntimeError:
                # 不在 async 上下文中，跳過
                pass

        return result

    # ------------------------------------------------------------------ #
    # 階段處理
    # ------------------------------------------------------------------ #

    def _start_new_task(self, user_input, state):
        from .workflow_handlers import start_new_task
        return start_new_task(self, user_input, state)

    def _handle_general(self, user_input, state) -> Dict[str, Any]:
        """通用處理 (未實現階段時的兜底)"""
        return {
            "type": "general",
            "content": f"[{state.phase}] 處理中...",
            "phase": state.phase,
        }

    # 其余方法（抽到 workflow_handlers.py）
    def _handle_requirement(self, user_input, state): ...
    def _handle_planning(self, user_input, state): ...
    def _handle_arch_review(self, user_input, state): ...
    def _handle_execution(self, user_input, state): ...
    def _handle_frontend_dev(self, user_input, state): ...
    def _handle_integration(self, user_input, state): ...

    # ------------------------------------------------------------------ #
    # 工具方法
    # ------------------------------------------------------------------ #

    def _build_task_json(self, task_type, state, **extra):
        return json.dumps(
            {
                "task_type": task_type,
                "session_id": state.session_id,
                "task_topic": state.task_topic,
                "requirement_summary": state.requirement_summary,
                "selected_plan": state.selected_plan,
                "plan_details": state.plan_options.get("full_text", ""),
                **extra,
            },
            ensure_ascii=False,
            indent=2,
        )

    def _parse_agent_result(self, output: str) -> dict:
        if not output:
            return {"output": ""}
        try:
            p = json.loads(output)
            if isinstance(p, dict):
                return p
        except Exception:
            pass
        m = re.search(r"```(?:json)?\s*\n(.*?)\n```", output, re.DOTALL)
        if m:
            try:
                p = json.loads(m.group(1))
                return p if isinstance(p, dict) else {"output": output}
            except Exception:
                pass
        return {"output": output}

    # ------------------------------------------------------------------ #
    # 秘書便捷方法
    # ------------------------------------------------------------------ #

    def get_context_for_llm(self, session_id: str, user_message: str = "") -> str:
        """獲取應注入 LLM 的上下文 (經驗 + 摘要 + 項目狀態 + 糾錯)"""
        self._ensure_secretary(session_id)
        return secretary.get_context_injection(user_message)

    def set_project(self, name: str, phase: str = ""):
        """設置當前活躍項目"""
        secretary.set_project(name, phase)

    def set_project_docs(self, plan: str = "", status: str = "", debt: str = ""):
        """設置項目文檔路徑"""
        secretary.set_project_docs(plan, status, debt)

    def get_secretary_status(self) -> dict:
        """獲取秘書狀態摘要"""
        return secretary.get_status()