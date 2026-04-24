"""
Code Agent
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence

from frame.core.base_agent import BaseAgent
from frame.core.base_llm import BaseLLM
from frame.core.config import AgentConfig, LLMConfig
from frame.core.llm_types import ToolCallMode
from frame.core.logger import Logger
from frame.core.message import LLMResponseFunCallMsg, Message, ToolResponseMessage, UserTextMessage
from frame.memory.base import AgentMemoryHooks
from frame.tool.base import BaseTool
from frame.tool.builtin.apply_patch import ApplyPatchTool
from frame.tool.builtin.list_dir import ListDirTool
from frame.tool.builtin.read_file import ReadFileTool
from frame.tool.builtin.run_command import RunCommandTool
from frame.tool.builtin.run_tests import RunTestsTool
from frame.tool.builtin.search_tool import SearchTool
from frame.tool.builtin.todo.storage import JsonTodoStorage
from frame.tool.builtin.todo.tool import TodoTool
from frame.tool.builtin.write_file import WriteFileTool
from frame.tool.register import ToolRegistry

PROGRESS_TOOL_NAMES = frozenset({"apply_patch", "write_file", "run_tests"})
TASK_STATE_UPDATE_ACTIONS = frozenset({"create", "update", "delete"})


class CodeAgentPhase(str, Enum):
    ANALYSIS = "analysis"
    GENERATION = "generation"
    VERIFICATION = "verification"


# 对于一个code agent，必须严格限制其的工作空间
CODE_AGENT_SYS_PROMPT_TEMPLATE = """
You are CodeAgent working inside the workspace rooted at:
{workspace_root}

You can only inspect and modify files under that workspace.
Your job is to turn a user request into actual code changes in the workspace and verify them.

Execution policy:
1. Start by reading relevant files or searching the workspace before modifying anything.
2. Prefer minimal viable changes and use apply_patch for edits.
3. After editing, run tests or restricted commands to verify behavior.
4. If a tool fails, use the failure output to repair the change and retry.
5. Keep user-facing updates concise and progress-oriented.
6. Only return a final completion response when work is actually done. The final completion response MUST contain the token [TASK_COMPLETED].
7. If the task is not complete, continue using tools and do not output [TASK_COMPLETED].

""".strip()


class CodeAgent(BaseAgent):
    COMPLETION_TOKEN = "[TASK_COMPLETED]"

    def __init__(
        self,
        config: AgentConfig,
        llm: BaseLLM,
        working_dir: Optional[str],
        sys_prompt: Optional[str] = None,
        logger: Optional[Logger] = None,
        session_id: Optional[str] = None,
        memory_hooks: Optional[AgentMemoryHooks] = None,
        agent_id: Optional[str] = None,
    ):
        self.repo_root_ = Path(__file__).resolve().parents[2]
        self.workspace_root_ = self._resolve_workspace_root(working_dir)
        self.workspace_root_.mkdir(parents=True, exist_ok=True)
        self.todo_storage_: Optional[JsonTodoStorage] = None
        self.active_user_request_: str = ""

        self.tool_registry_ = ToolRegistry()
        self._register_code_tools()

        resolved_prompt = self._build_system_prompt(self.workspace_root_, base_prompt=sys_prompt)
        super().__init__(
            config,
            llm,
            resolved_prompt,
            logger,
            session_id,
            memory_hooks,
            agent_id,
        )

        self.max_refinement_rounds_ = max(1, int(getattr(config, "max_rounds_", 15)))
        self.max_phase_tool_rounds_ = 6
        self.task_state_update_backpressure_rounds_ = max(
            1, int(getattr(config, "task_state_update_backpressure_rounds_", 2))
        )

    def _build_system_prompt(self, workspace_root: Path, base_prompt: Optional[str] = None) -> str:
        prompt = CODE_AGENT_SYS_PROMPT_TEMPLATE.format(
            workspace_root=str(workspace_root),
        )
        if base_prompt:
            return f"{base_prompt.strip()}\n\n{prompt}"
        return prompt

    # 约定agent的工作空间必须在终端启动的当前路径下，防止误操作
    def _resolve_workspace_root(self, working_dir: Optional[str]) -> Path:
        base = Path.cwd()
        if not working_dir:
            return (base / ".agent_workspace").resolve()

        candidate = Path(working_dir).expanduser()

        if candidate.is_absolute():
            return candidate.resolve()

        return (base / candidate).resolve()

    def _register_code_tools(self) -> None:
        workspace_root = str(self.workspace_root_)
        todo_storage = JsonTodoStorage(filename="code_agent", base_dir=str(self.workspace_root_ / ".todo"))
        self.todo_storage_ = todo_storage
        tools = [
            ReadFileTool(base_dir=workspace_root),
            SearchTool(base_dir=workspace_root),
            ListDirTool(base_dir=workspace_root),
            TodoTool(storage=todo_storage),
            WriteFileTool(base_dir=workspace_root),
            ApplyPatchTool(workspace_root=workspace_root),
            RunCommandTool(workspace_root=workspace_root),
            RunTestsTool(workspace_root=workspace_root),
        ]
        for tool in tools:
            self.tool_registry_.register_tool(tool)

    def _emit_progress(self, stage: str, message: str) -> None:
        text = f"[CodeAgent:{stage}] {message}"
        self.logger_.info(text)
        print(text, flush=True)

    def _build_code_task_brief(self, user_input: str) -> str:
        return (
            "[Code Task]\n"
            "If you need to inspect directories, prefer list_dir over shell ls.\n"
            "Follow a read -> patch/write -> run -> verify workflow.\n"
            "If you need to modify files, use apply_patch instead of rewriting entire files.\n"
            "If tests fail, inspect the reported error and repair only the failing slice.\n\n"
            f"[User Request]\n{user_input}"
        )

    def _phase_instructions(self, phase: CodeAgentPhase | str) -> str:
        phase_value = phase.value if isinstance(phase, CodeAgentPhase) else str(phase)
        if phase_value == CodeAgentPhase.ANALYSIS.value:
            return (
                "Analyze the request, persist the plan into todo items when useful, and produce a concise implementation plan. "
                "Name the files or tool actions you expect to use, but do not modify files yet."
                "Persist the complete execution plan using the TODO tool."
            )
        if phase_value == CodeAgentPhase.GENERATION.value:
            return (
                "Execute the implementation plan using the available tools. "
                "Use read_file/search/list_dir before editing, write_file/apply_patch for changes, and run_tests to verify. "
                "Keep todo items updated when the task state changes. "
                "Do NOT output raw JSON, diff blocks, or pseudo-commands as plain text. "
                "If an action is needed, call a tool directly with a valid non-empty tool name. "
            )
        if phase_value == CodeAgentPhase.VERIFICATION.value:
            return (
                "Verify the workspace state. Prefer run_tests and direct file checks. "
                "Use todo to mark the task state only if the implementation is truly complete. "
                "If and only if the task is fully completed, include the exact token [TASK_COMPLETED] in your response."
            )
        if phase_value == "retry":
            return (
                "The previous attempt reported a tool error or verification failure. "
                "Inspect the failure, repair the smallest possible slice, and try again."
            )
        return ""

    def _phase_usable_tools(self, phase: CodeAgentPhase) -> List[BaseTool]:
        tool_names_by_phase = {
            CodeAgentPhase.ANALYSIS: ["read_file", "search", "list_dir", "todo"],
            CodeAgentPhase.GENERATION: [
                "read_file",
                "search",
                "list_dir",
                "todo",
                "write_file",
                "apply_patch",
                "run_command",
                "run_tests",
            ],
            CodeAgentPhase.VERIFICATION: ["read_file", "search", "list_dir", "todo", "run_tests"],
        }
        return [self.tool_registry_.get_tool_by_name(name) for name in tool_names_by_phase[phase]]

    def _tool_call_logger(self):
        def _callback(call) -> None:
            tool_name = getattr(call, "tool_name", "")
            arguments = getattr(call, "arguments", {})
            self._emit_progress("tool", f"request {tool_name} args={arguments}")

        return _callback

    def _tool_result_logger(self, call: LLMResponseFunCallMsg, result_status: str) -> None:
        tool_name = getattr(call, "tool_name", "")
        self._emit_progress("tool", f"executed {tool_name} status={result_status}")

    def _token_printer(self, token: str) -> None:
        print(token, end="", flush=True)

    def _should_finish(self, verified: Sequence[Message]) -> bool:
        if not verified:
            return False
        if self._messages_have_tool_error(verified):
            return False
        return self._has_completion_token(verified) or self._messages_have_progress_tool_activity(verified)

    def _messages_have_tool_error(self, messages: Sequence[Message]) -> bool:
        for msg in messages:
            if getattr(msg, "type", "") != "tool_response":
                continue
            if getattr(msg, "status", "") == "error":
                return True
        return False

    def _has_completion_token(self, messages: Sequence[Message]) -> bool:
        for msg in messages:
            if getattr(msg, "type", "") != "text":
                continue
            content = getattr(msg, "content", "")
            if isinstance(content, str) and self.COMPLETION_TOKEN in content:
                return True
        return False

    def _messages_have_progress_tool_activity(self, messages: Sequence[Message]) -> bool:
        for msg in messages:
            if getattr(msg, "type", "") != "tool_response":
                continue
            if getattr(msg, "status", "") != "success":
                continue
            tool_name = getattr(msg, "tool_name", "")
            if tool_name in PROGRESS_TOOL_NAMES:
                return True
        return False

    def _compose_retry_context(
        self,
        base_messages: List[Message],
        analyzed: List[Message],
        generated: List[Message],
        verified: List[Message],
    ) -> List[Message]:
        retry_hint = UserTextMessage(
            content=(
                "Please repair the previous attempt using the tool error / verification output above. "
                "Only make the minimal follow-up change required to complete the task. "
                "If you need to act on files or commands, issue tool calls instead of raw JSON text.\n"
                f"{self._build_failure_guidance([*generated, *verified])}"
            )
        )
        return [*base_messages, *analyzed, *generated, *verified, retry_hint]

    def _build_failure_guidance(self, messages: Sequence[Message]) -> str:
        error_msgs = [
            msg
            for msg in messages
            if getattr(msg, "type", "") == "tool_response" and getattr(msg, "status", "") == "error"
        ]
        if not error_msgs:
            return "Failure guidance: If a tool fails, change strategy instead of repeating the same read/list loop."

        latest = error_msgs[-1]
        tool_name = str(getattr(latest, "tool_name", ""))
        content = str(getattr(latest, "content", ""))
        details = getattr(latest, "details", None) or {}

        if tool_name == "run_tests":
            error_type = str(details.get("error_type", ""))
            lowered = content.lower()
            if error_type == "tests_not_found" or "file or directory not found" in lowered:
                return (
                    "Failure guidance: run_tests did not find test files. Create a minimal test file first "
                    "(for example tests/test_<feature>.py), then rerun run_tests using an existing path. "
                    "Do not repeat read_file/list_dir loops before creating the missing test file."
                )
            if error_type == "no_tests_collected" or "no tests ran" in lowered:
                return (
                    "Failure guidance: pytest collected zero tests. Add at least one valid test_*.py with a test_ function, "
                    "then rerun run_tests."
                )
            return (
                "Failure guidance: run_tests failed. Read the failing traceback, patch the related code/tests, "
                "then rerun run_tests once after edits."
            )

        if tool_name == "list_dir" and "directory not found" in content.lower():
            return (
                "Failure guidance: list_dir path is invalid. First call list_dir with path='.' (or empty path) "
                "to discover actual folders, then use discovered paths only."
            )

        if tool_name == "run_command":
            lowered = content.lower()
            if "interactive python is not allowed" in lowered:
                return (
                    "Failure guidance: run_command rejected an interactive python call. "
                    "Use a complete command with arguments, for example command='python' with args='-m pytest -q frame/test/...', "
                    "or cmd='python -m pytest -q ...'. Do not retry bare 'python'."
                )
            if "command not allowed" in lowered:
                return (
                    "Failure guidance: run_command used a non-allowlisted command. "
                    "Switch to an allowlisted command and include concrete arguments."
                )
            return (
                "Failure guidance: run_command failed. Inspect stderr and rerun with a full command line and explicit arguments, "
                "instead of repeating the same call."
            )

        return (
            "Failure guidance: Use the latest tool error details to perform one concrete repair action "
            "before running verification again."
        )

    def _extract_todo_action(self, raw_output: str) -> str:
        try:
            parsed = json.loads(raw_output)
        except Exception:
            return ""
        if not isinstance(parsed, dict):
            return ""
        return str(parsed.get("action", "")).strip()

    def _phase_has_task_state_update(self, messages: Sequence[Message]) -> bool:
        for msg in messages:
            if getattr(msg, "type", "") != "tool_response":
                continue
            if getattr(msg, "tool_name", "") != "todo":
                continue
            if getattr(msg, "status", "") != "success":
                continue
            action = self._extract_todo_action(str(getattr(msg, "content", "")))
            if action in TASK_STATE_UPDATE_ACTIONS:
                return True
        return False

    def _describe_todo_snapshot(self) -> str:
        storage = self.todo_storage_
        if storage is None:
            return "- todo storage unavailable"

        try:
            items = storage.load_items()
        except Exception as exc:
            return f"- failed to load todo items: {exc}"

        if not items:
            return "- no todo items yet"

        lines = []
        for item in items:
            lines.append(f"- [{item.status.value}] {item.text} ({item.item_id})")
        return "\n".join(lines)

    def _build_task_focus_message(self, phase: CodeAgentPhase, rounds_without_update: int) -> UserTextMessage:
        reminder_text = (
            "[Task Focus]\n"
            f"Active phase: {phase.value}\n"
            f"Rounds without todo state updates: {rounds_without_update}\n"
            f"Current user request: {self.active_user_request_}\n"
            f"Todo snapshot:\n{self._describe_todo_snapshot()}\n"
            "Return to the current task, update the todo state if it has changed, and avoid drifting to new work."
        )
        return UserTextMessage(content=reminder_text)

    def _extract_tool_calls(self, messages: Sequence[Message]) -> List[LLMResponseFunCallMsg]:
        tool_calls: List[LLMResponseFunCallMsg] = []
        for msg in messages:
            if isinstance(msg, LLMResponseFunCallMsg):
                tool_calls.append(msg)
                continue

            if getattr(msg, "type", "") != "function":
                continue

            tool_calls.append(
                LLMResponseFunCallMsg.from_raw(
                    tool_name=str(getattr(msg, "tool_name", "")),
                    call_id=str(getattr(msg, "call_id", "")),
                    arguments_json=str(getattr(msg, "arguments_json", "{}")),
                    arguments=getattr(msg, "arguments", {}) or {},
                )
            )
        return tool_calls

    def _execute_tool_calls(self, tool_calls: Sequence[LLMResponseFunCallMsg]) -> List[ToolResponseMessage]:
        tool_results: List[ToolResponseMessage] = []
        for call in tool_calls:
            tool_name = (call.tool_name or "").strip()
            if not tool_name:
                self._emit_progress("tool", f"skip empty tool name call_id={call.call_id}")
                continue

            result = self.tool_registry_.execute_tool(call_info=call)
            self._tool_result_logger(call, result.status)
            tool_results.append(
                ToolResponseMessage.from_tool_result(
                    tool_name=tool_name,
                    call_id=call.call_id,
                    status=result.status,
                    output=result.output,
                    details=result.details,
                )
            )
        return tool_results

    def _run_phase_with_manual_tools(self, phase: CodeAgentPhase, context: List[Message]) -> List[Message]:
        phase_messages: List[Message] = []
        phase_context = list(context)
        tools = self._phase_usable_tools(phase)
        tmp_sys_prompt = self.sys_prompt_ + "\n\n" + self._phase_instructions(phase)

        for tool_round in range(self.max_phase_tool_rounds_):
            self._emit_progress(phase.value, f"manual round {tool_round + 1}/{self.max_phase_tool_rounds_}")
            llm_messages = self.llm_.invoke_streaming(
                messages=phase_context,
                tools=tools,
                sys_instructions=tmp_sys_prompt,
                on_token_callback=self._token_printer,
                on_tool_call_callback=self._tool_call_logger(),
                tool_mode=ToolCallMode.MANUAL,
            )
            phase_messages.extend(llm_messages)
            phase_context.extend(llm_messages)

            tool_calls = self._extract_tool_calls(llm_messages)
            if not tool_calls:
                break

            tool_results = self._execute_tool_calls(tool_calls)
            if not tool_results:
                break

            phase_messages.extend(tool_results)
            phase_context.extend(tool_results)

        return phase_messages

    def _think_impl(self, user_input: str):
        task_brief = self._build_code_task_brief(user_input)
        self.active_user_request_ = user_input
        invoke_message = self._prepare_invoke_messages(task_brief)

        self._emit_progress("start", f"Starting code task execution in workspace: {self.workspace_root_}")

        conversation_messages = list(invoke_message)
        final_message: List[Message] = []
        rounds_without_task_state_update = 0

        for round_index in range(self.max_refinement_rounds_):
            self._emit_progress("round", f"Starting round {round_index + 1}/{self.max_refinement_rounds_}")

            if rounds_without_task_state_update >= self.task_state_update_backpressure_rounds_:
                reminder_message = self._build_task_focus_message(
                    CodeAgentPhase.GENERATION, rounds_without_task_state_update
                )
                conversation_messages.append(reminder_message)
                self._emit_progress(
                    "backpressure",
                    f"injecting task reminder after {rounds_without_task_state_update} rounds without todo updates",
                )

            analyzed = self._run_analysis_phase(conversation_messages)
            conversation_messages.extend(analyzed)

            generated = self._run_generation_phase(conversation_messages)
            conversation_messages.extend(generated)

            verified = self._run_verification_phase(conversation_messages)
            conversation_messages.extend(verified)

            final_message = verified or generated or analyzed
            if self._phase_has_task_state_update([*analyzed, *generated, *verified]):
                rounds_without_task_state_update = 0
                self._emit_progress("todo", "task state updated; backpressure counter reset")
            else:
                rounds_without_task_state_update += 1
                self._emit_progress(
                    "todo",
                    f"no task state update this round; idle rounds={rounds_without_task_state_update}",
                )

            if self._should_finish(verified):
                break

        if not final_message:
            print("No response generated.")
            return

        if not self._has_completion_token(final_message) and not self._messages_have_progress_tool_activity(final_message):
            self._emit_progress("finish", "max rounds reached without completion signal; committing last messages for debugging")
        else:
            self._emit_progress("finish", f"committing {len(final_message)} messages")
        self._commit_turn(user_input=user_input, llm_messages=conversation_messages)

    def _run_analysis_phase(self, context: List[Message]) -> List[Message]:
        self._emit_progress("analysis", "Analyzing the task and formulating an implementation plan.")
        response = self._run_phase_with_manual_tools(CodeAgentPhase.ANALYSIS, context)
        print()
        self._emit_progress("analysis", "Analysis phase completed. Implementation plan formulated.")
        return response

    def _run_generation_phase(self, context: List[Message]) -> List[Message]:
        self._emit_progress("generation", "Executing the implementation plan with tool usage.")
        response = self._run_phase_with_manual_tools(CodeAgentPhase.GENERATION, context)
        print()
        self._emit_progress("generation", "Generation phase completed. Implementation executed.")
        return response

    def _run_verification_phase(self, context: List[Message]) -> List[Message]:
        self._emit_progress("verification", "Verifying the implementation and workspace state.")
        response = self._run_phase_with_manual_tools(CodeAgentPhase.VERIFICATION, context)
        print()
        self._emit_progress("verification", "Verification phase completed.")
        return response


if __name__ == "__main__":
    llm_config = LLMConfig.from_env()
    llm = BaseLLM(llm_config)
    agent_config = AgentConfig.from_env()

    agent = CodeAgent(config=agent_config, llm=llm, working_dir="code_space")

    demo_request = (
        "请帮我写一个 Python 函数 `is_palindrome(text: str) -> bool`，"
        "忽略大小写与非字母数字字符，并补一个最小测试示例。"
    )

    print("CodeAgent demo started. Sending one-shot request...\n")
    print(f"User: {demo_request}\n")
    agent.think(demo_request)