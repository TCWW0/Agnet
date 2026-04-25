"""使用 ReAct 范式的 code agent 实现。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Sequence

from frame.core.base_agent import BaseAgent
from frame.core.base_llm import BaseLLM
from frame.core.config import AgentConfig, LLMConfig
from frame.core.llm_types import ToolCallMode
from frame.core.logger import Logger
from frame.core.message import LLMResponseFunCallMsg, LLMResponseTextMsg, Message, ToolResponseMessage, UserTextMessage
from frame.memory.base import AgentMemoryHooks
from frame.tool.base import BaseTool
from frame.tool.builtin.apply_patch import ApplyPatchTool
from frame.tool.builtin.read_file import ReadFileTool
from frame.tool.builtin.run_tests import RunTestsTool
from frame.tool.register import ToolRegistry

REACT_CODE_AGENT_SYS_PROMPT_TEMPLATE = """
You are ReactCodeAgent working inside the workspace rooted at:
{workspace_root}

Use a single Thought -> Action -> Observation loop.

Rules:
1. Think before acting.
2. Read before modifying.
3. Make minimal changes with apply_patch.
4. After modifying code, run tests.
5. Do not make unrelated actions in one step.
6. Finish only when the code is correct and tests pass.
7. Output [TASK_COMPLETED] only at the end.
8. When you need a tool, emit exactly one tool call or one compact JSON tool directive.

Tool hints:
- read_file: inspect file content
- apply_patch: apply a unified diff patch
- run_tests: run the test suite or a focused test pattern
""".strip()


class ReactCodeAgent(BaseAgent):
    """使用 ReACT 范式的 code agent 实现。"""

    COMPLETION_TOKEN = "[TASK_COMPLETED]"
    REACT_STAGES = ("thought", "action", "observation", "finish")

    def __init__(
        self,
        config: AgentConfig,
        llm: BaseLLM,
        working_dir: Optional[str] = None,
        sys_prompt: Optional[str] = None,
        logger: Logger | None = None,
        session_id: str | None = None,
        memory_hooks: AgentMemoryHooks | None = None,
        agent_id: str | None = None,
    ):
        self.workspace_root_ = self._resolve_workspace_root(working_dir)
        self.workspace_root_.mkdir(parents=True, exist_ok=True)

        self.tool_registry_ = ToolRegistry()
        self._register_code_tools()

        resolved_prompt = self._build_system_prompt(self.workspace_root_, base_prompt=sys_prompt)
        super().__init__(config, llm, resolved_prompt, logger, session_id, memory_hooks, agent_id)

        self.max_steps_ = max(1, int(getattr(config, "max_rounds_", 15)))
        self.max_no_action_rounds_ = 1
        self._has_made_changes_ = False
        self._last_run_tests_success_ = False
        self._completion_ready_ = False
        self._react_step_index_ = 0
        self._react_stage_ = "thought"

    def _resolve_workspace_root(self, working_dir: Optional[str]) -> Path:
        base = Path.cwd()
        if not working_dir:
            return (base / ".agent_workspace").resolve()

        candidate = Path(working_dir).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (base / candidate).resolve()

    def _build_system_prompt(self, workspace_root: Path, base_prompt: Optional[str] = None) -> str:
        prompt = REACT_CODE_AGENT_SYS_PROMPT_TEMPLATE.format(workspace_root=str(workspace_root))
        if base_prompt:
            return f"{base_prompt.strip()}\n\n{prompt}"
        return prompt

    def _register_code_tools(self) -> None:
        workspace_root = str(self.workspace_root_)
        tools: List[BaseTool] = [
            ReadFileTool(base_dir=workspace_root),
            ApplyPatchTool(workspace_root=workspace_root),
            RunTestsTool(workspace_root=workspace_root),
        ]
        for tool in tools:
            self.tool_registry_.register_tool(tool)

    def _emit_progress(self, stage: str, message: str) -> None:
        text = f"[ReactCodeAgent:{stage}] {message}"
        self.logger_.info(text)
        print(text, flush=True)

    def _set_react_stage(self, stage: str, detail: str) -> None:
        self._react_stage_ = stage
        self._emit_progress("state", f"step={self._react_step_index_}/{self.max_steps_} stage={stage} {detail}")

    def _build_code_task_brief(self, user_input: str) -> str:
        return (
            "[Code Task]\n"
            "Use one step per action. Read before modifying. After modifying code, run tests.\n\n"
            f"[User Request]\n{user_input}"
        )

    def _phase_instructions(self) -> str:
        return (
            "Use a Thought -> Action -> Observation loop. "
            "Think before acting. "
            "Read before modifying. "
            "Use apply_patch for edits. "
            "After modifying code, run tests. "
            "Do not perform multiple unrelated actions in one step. "
            "If a tool fails, use the error as the next thought input. "
            f"Only output {self.COMPLETION_TOKEN} when the task is fully complete and tests have passed."
        )

    def _token_printer(self, token: str) -> None:
        print(token, end="", flush=True)

    def _tool_call_logger(self):
        def _callback(call) -> None:
            tool_name = getattr(call, "tool_name", "")
            arguments = getattr(call, "arguments", {})
            self._emit_progress("tool", f"request {tool_name} args={arguments}")

        return _callback

    def _try_parse_text_tool_call(self, message: Message, call_index: int) -> LLMResponseFunCallMsg | None:
        content = getattr(message, "content", "")
        if not isinstance(content, str):
            return None

        candidate = content.strip()
        if not candidate:
            return None

        json_match = re.search(r"\{.*\}", candidate, re.S)
        if json_match is not None:
            candidate = json_match.group(0)

        try:
            loaded = json.loads(candidate)
        except json.JSONDecodeError:
            return None

        if not isinstance(loaded, dict) or not loaded:
            return None

        tool_name: str | None = None
        arguments: dict = {}

        if len(loaded) == 1:
            key, value = next(iter(loaded.items()))
            if key in {"read_file", "apply_patch", "run_tests"}:
                tool_name = key
                if isinstance(value, dict):
                    arguments = value
                elif key == "read_file":
                    arguments = {"file_path": value}
                elif key == "apply_patch":
                    arguments = {"patch": value}
                elif key == "run_tests":
                    arguments = {"pattern": value}
            elif key in {"file_path", "patch", "pattern"}:
                if key == "file_path":
                    tool_name = "read_file"
                elif key == "patch":
                    tool_name = "apply_patch"
                else:
                    tool_name = "run_tests"
                arguments = {key: value}

        if tool_name is None:
            if "patch" in loaded:
                tool_name = "apply_patch"
                arguments = {"patch": loaded["patch"]}
            elif "file_path" in loaded:
                tool_name = "read_file"
                arguments = {"file_path": loaded["file_path"]}
            elif "pattern" in loaded:
                tool_name = "run_tests"
                arguments = {"pattern": loaded["pattern"]}

        if tool_name is None:
            return None

        arguments_json = json.dumps(arguments, ensure_ascii=False)
        synthetic_call_id = f"text-{self._react_step_index_}-{call_index}-{tool_name}"
        self._emit_progress("parse", f"text directive -> {tool_name} args={arguments}")
        return LLMResponseFunCallMsg.from_raw(
            tool_name=tool_name,
            call_id=synthetic_call_id,
            arguments_json=arguments_json,
            arguments=arguments,
        )

    def _extract_tool_calls(self, messages: Sequence[Message]) -> List[LLMResponseFunCallMsg]:
        calls: List[LLMResponseFunCallMsg] = []
        for index, msg in enumerate(messages):
            if isinstance(msg, LLMResponseFunCallMsg):
                calls.append(msg)
                continue
            if getattr(msg, "type", "") != "function":
                parsed_call = self._try_parse_text_tool_call(msg, index)
                if parsed_call is not None:
                    calls.append(parsed_call)
        return calls

    def _execute_tool_calls(self, tool_calls: Sequence[LLMResponseFunCallMsg]) -> List[ToolResponseMessage]:
        observations: List[ToolResponseMessage] = []
        self._set_react_stage("action", f"executing {len(tool_calls)} tool call(s)")
        for call in tool_calls:
            tool_name = (call.tool_name or "").strip()
            if not tool_name:
                self._emit_progress("tool", f"skip empty tool name call_id={call.call_id}")
                continue

            result = self.tool_registry_.execute_tool(call_info=call)
            self._update_state_from_tool_result(tool_name, result.status)
            self._emit_progress("tool", f"executed {tool_name} status={result.status}")
            observations.append(
                ToolResponseMessage.from_tool_result(
                    tool_name=tool_name,
                    call_id=call.call_id,
                    status=result.status,
                    output=result.output,
                    details=result.details,
                )
            )
        return observations

    def _update_state_from_tool_result(self, tool_name: str, status: str) -> None:
        if tool_name == "apply_patch" and status == "success":
            self._has_made_changes_ = True
            self._last_run_tests_success_ = False
            self._completion_ready_ = False
            return

        if tool_name == "run_tests":
            self._last_run_tests_success_ = status == "success"
            if status != "success":
                self._completion_ready_ = False

    def _has_completion_token(self, messages: Sequence[Message]) -> bool:
        for msg in messages:
            if getattr(msg, "type", "") != "text":
                continue
            content = getattr(msg, "content", "")
            if isinstance(content, str) and self.COMPLETION_TOKEN in content:
                return True
        return False

    def _should_finish(self, messages: Sequence[Message]) -> bool:
        return self._completion_ready_

    def _summarize_observations(self, observations: Sequence[ToolResponseMessage]) -> str:
        if not observations:
            return "no observation"
        summary_parts = []
        for obs in observations:
            summary_parts.append(f"{obs.tool_name}:{obs.status}")
        return ", ".join(summary_parts)

    def _think_impl(self, user_input: str):
        task_brief = self._build_code_task_brief(user_input)
        invoke_messages = self._prepare_invoke_messages(task_brief)

        self._emit_progress("start", f"Starting React code task execution in workspace: {self.workspace_root_}")

        context = list(invoke_messages)
        turn_messages: List[Message] = []
        no_action_rounds = 0
        completion_step_index: int | None = None

        for step_index in range(self.max_steps_):
            self._react_step_index_ = step_index + 1
            self._set_react_stage("thought", f"starting step {step_index + 1}/{self.max_steps_}")
            llm_messages = self.llm_.invoke_streaming(
                messages=context,
                tools=self.tool_registry_.get_tools(),
                sys_instructions=self._phase_instructions(),
                on_token_callback=self._token_printer,
                on_tool_call_callback=self._tool_call_logger(),
                tool_mode=ToolCallMode.MANUAL,
            )
            turn_messages.extend(llm_messages)
            context.extend(llm_messages)

            step_has_completion_token = self._has_completion_token(llm_messages)

            tool_calls = self._extract_tool_calls(llm_messages)
            self._emit_progress(
                "trace",
                f"step={step_index + 1}/{self.max_steps_} stage={self._react_stage_} llm_messages={len(llm_messages)} tool_calls={len(tool_calls)} completion_token={step_has_completion_token}",
            )
            if not tool_calls:
                if (
                    step_has_completion_token
                    and (not self._has_made_changes_ or self._last_run_tests_success_)
                ):
                    self._completion_ready_ = True
                    completion_step_index = step_index + 1
                    self._set_react_stage("finish", "completion token observed after valid verification")

                if self._should_finish(turn_messages):
                    break

                no_action_rounds += 1
                self._emit_progress(
                    "idle",
                    f"step={step_index + 1}/{self.max_steps_} no tool call observed; idle rounds={no_action_rounds}; state={self._react_stage_}",
                )
                if no_action_rounds >= self.max_no_action_rounds_:
                    context.append(
                        UserTextMessage(
                            content=(
                                f"State reminder: you are in {self._react_stage_.upper()} but no action was produced. "
                                "Emit exactly one tool call next, or output the completion token only after verification succeeds."
                            )
                        )
                    )
                    self._emit_progress("state", "inserted stage reminder into context")
                    no_action_rounds = 0
                continue

            no_action_rounds = 0
            observations = self._execute_tool_calls(tool_calls)
            if observations:
                turn_messages.extend(observations)
                context.extend(observations)
                self._set_react_stage("observation", self._summarize_observations(observations))

            if step_has_completion_token and (not self._has_made_changes_ or self._last_run_tests_success_):
                self._completion_ready_ = True
                completion_step_index = step_index + 1
                self._set_react_stage("finish", "completion token observed after valid verification")

            if self._should_finish(turn_messages):
                break

        if not turn_messages:
            print("No response generated.")
            return

        if not self._should_finish(turn_messages):
            self._set_react_stage("finish", "max steps reached without completion signal; committing last messages")
        else:
            detail = f"committing {len(turn_messages)} messages"
            if completion_step_index is not None:
                detail = f"{detail}; completed at step {completion_step_index}"
            self._set_react_stage("finish", detail)

        self._commit_turn(user_input=user_input, llm_messages=turn_messages)

if __name__ == "__main__":
    llm_config = LLMConfig.from_env()
    llm = BaseLLM(llm_config)
    agent_config = AgentConfig.from_env()

    agent = ReactCodeAgent(config=agent_config, llm=llm, working_dir="code_space_bak1")

    demo_request = (
        "请帮我写一个 Python 函数 `is_palindrome(text: str) -> bool`，"
        "忽略大小写与非字母数字字符，并补一个最小测试示例。"
    )

    print("CodeAgent demo started. Sending one-shot request...\n")
    print(f"User: {demo_request}\n")
    agent.think(demo_request)