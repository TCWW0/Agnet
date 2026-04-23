"""
Code Agent
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Sequence

from frame.core.base_agent import BaseAgent
from frame.core.base_llm import BaseLLM
from frame.core.config import AgentConfig, LLMConfig
from frame.core.llm_types import ToolCallMode
from frame.core.logger import Logger
from frame.core.message import Message, UserTextMessage
from frame.memory.base import AgentMemoryHooks
from frame.tool.builtin.apply_patch import ApplyPatchTool
from frame.tool.builtin.git_commit import GitCommitTool
from frame.tool.builtin.git_diff import GitDiffTool
from frame.tool.builtin.git_reset import GitResetTool
from frame.tool.builtin.list_dir import ListDirTool
from frame.tool.builtin.read_file import ReadFileTool
from frame.tool.builtin.run_command import RunCommandTool
from frame.tool.builtin.run_tests import RunTestsTool
from frame.tool.builtin.search_tool import SearchTool
from frame.tool.register import ToolRegistry

PROGRESS_TOOL_NAMES = {"apply_patch", "run_tests", "git_commit", "git_reset"}

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
5. Once the workspace is stable, you may use git_diff and git_commit.
6. Keep user-facing updates concise and progress-oriented.
7. Only return a final completion response when work is actually done. The final completion response MUST contain the token [TASK_COMPLETED].
8. If the task is not complete, continue using tools and do not output [TASK_COMPLETED].
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

    def _register_code_tools(self) -> None:
        workspace_root = str(self.workspace_root_)
        tools = [
            ReadFileTool(base_dir=workspace_root),
            SearchTool(base_dir=workspace_root),
            ListDirTool(base_dir=workspace_root),
            ApplyPatchTool(workspace_root=workspace_root),
            RunCommandTool(workspace_root=workspace_root),
            RunTestsTool(workspace_root=workspace_root),
            GitDiffTool(workspace_root=workspace_root),
            GitCommitTool(workspace_root=workspace_root),
            GitResetTool(workspace_root=workspace_root),
        ]
        for tool in tools:
            self.tool_registry_.register_tool(tool)

    def _build_system_prompt(self, workspace_root: Path, base_prompt: Optional[str] = None) -> str:
        prompt = CODE_AGENT_SYS_PROMPT_TEMPLATE.format(
            workspace_root=str(workspace_root)
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

    def _emit_progress(self, stage: str, message: str) -> None:
        text = f"[CodeAgent:{stage}] {message}"
        self.logger_.info(text)
        print(text, flush=True)

    def _build_code_task_brief(self, user_input: str) -> str:
        return (
            "[Code Task]\n"
            f"Workspace root: {self.workspace_root_}\n"
            "If you need to inspect directories, prefer list_dir over shell ls.\n"
            "Follow a read -> patch -> run -> verify -> commit workflow.\n"
            "If you need to modify files, use apply_patch instead of rewriting entire files.\n"
            "If tests fail, inspect the reported error and repair only the failing slice.\n\n"
            f"[User Request]\n{user_input}"
        )

    def _phase_instructions(self, phase: str) -> str:
        if phase == "analysis":
            return (
                "Analyze the request and produce a concise implementation plan. "
                "Name the files or tool actions you expect to use, but do not modify files yet."
            )
        if phase == "generation":
            return (
                "Execute the implementation plan using the available tools. "
                "Use read_file/search before editing, apply_patch for changes, and run_command/run_tests to verify. "
                "Do NOT output raw JSON, diff blocks, or pseudo-commands as plain text. "
                "If an action is needed, call a tool directly with a valid non-empty tool name."
            )
        if phase == "verification":
            return (
                "Verify the workspace state. Prefer run_tests and git_diff, and commit only if the result is stable. "
                "If and only if the task is fully completed, include the exact token [TASK_COMPLETED] in your response."
            )
        if phase == "retry":
            return (
                "The previous attempt reported a tool error or verification failure. "
                "Inspect the failure, repair the smallest possible slice, and try again."
            )
        return ""

    def _tool_call_logger(self):
        def _callback(call) -> None:
            tool_name = getattr(call, "tool_name", "")
            arguments = getattr(call, "arguments", {})
            self._emit_progress("tool", f"request {tool_name} args={arguments}")

        return _callback

    def _token_printer(self, token: str) -> None:
        print(token, end="", flush=True)

    def _build_phase_summary_note(self, label: str, messages: Sequence[Message]) -> Message:
        lines: List[str] = []
        tail = list(messages)[-6:]
        for msg in tail:
            msg_type = getattr(msg, "type", "")
            role = getattr(msg, "role", "")
            content = str(getattr(msg, "content", ""))
            if msg_type == "tool_response":
                tool_name = getattr(msg, "tool_name", "")
                status = getattr(msg, "status", "")
                details = getattr(msg, "details", None)
                lines.append(f"{role}/{msg_type}/{tool_name}/{status}: {content[:240]} details={details}")
            else:
                lines.append(f"{role}/{msg_type}: {content[:240]}")

        summary = "\n".join(lines) if lines else "(no content)"
        return Message(role="system", content=f"[{label}_summary]\n{summary}", type="text")

    # TODO：这里先考虑将对应的工具调用放开，由底层自行调度，后续再考虑取回控制权
    def _run_analysis_phase(self, invoke_messages: List[Message]) -> List[Message]:
        self._emit_progress("analysis", "starting")
        messages = self.llm_.invoke_streaming(
            messages=invoke_messages,
            tools=[],
            sys_instructions=self._phase_instructions("analysis"),
            on_token_callback=self._token_printer,
            tool_mode=ToolCallMode.OFF,
        )
        print()
        self._emit_progress("analysis", f"completed with {len(messages)} messages")
        return messages

    def _run_generation_phase(self, messages: List[Message]) -> List[Message]:
        self._emit_progress("generation", "starting")
        generated = self.llm_.invoke_streaming(
            messages=messages,
            tools=self.tool_registry_.get_tools(),
            sys_instructions=self._phase_instructions("generation"),
            on_token_callback=self._token_printer,
            tool_mode=ToolCallMode.AUTO,
        )
        print()
        self._emit_progress("generation", f"completed with {len(generated)} messages")
        return generated

    def _run_verification_phase(self, messages: List[Message]) -> List[Message]:
        self._emit_progress("verification", "starting")
        verified = self.llm_.invoke_streaming(
            messages=messages,
            tools=self.tool_registry_.get_tools(),
            sys_instructions=self._phase_instructions("verification"),
            on_token_callback=self._token_printer,
            tool_mode=ToolCallMode.AUTO,
        )
        print()
        self._emit_progress("verification", f"completed with {len(verified)} messages")
        return verified

    def _has_completion_token(self, messages: Sequence[Message]) -> bool:
        for msg in messages:
            if getattr(msg, "type", "") != "text":
                continue
            content = getattr(msg, "content", "")
            if isinstance(content, str) and self.COMPLETION_TOKEN in content:
                return True
        return False

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

    def _messages_have_tool_activity(self, messages: Sequence[Message]) -> bool:
        for msg in messages:
            msg_type = getattr(msg, "type", "")
            if msg_type in {"function", "tool_response"}:
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
                "If you need to act on files or commands, you must issue tool calls instead of raw JSON text."
            )
        )
        return [*base_messages, *analyzed, *generated, *verified, retry_hint]

    def _think_impl(self, user_input: str):
        task_brief = self._build_code_task_brief(user_input)
        invoke_messages = self._prepare_invoke_messages(task_brief)

        self._emit_progress("start", f"workspace={self.workspace_root_}")

        context = invoke_messages
        final_messages: List[Message] = []

        for round_index in range(self.max_refinement_rounds_):
            self._emit_progress("round", f"{round_index + 1}/{self.max_refinement_rounds_}")
            analyzed = self._run_analysis_phase(context)
            context_summary = self._build_phase_summary_note("context", context)
            analysis_summary = self._build_phase_summary_note("analysis", analyzed)
            generated = self._run_generation_phase([context_summary, analysis_summary])
            generation_summary = self._build_phase_summary_note("generation", generated)
            verified = self._run_verification_phase([context_summary, analysis_summary, generation_summary])

            final_messages = verified or generated or analyzed
            if self._should_finish(verified) or self._should_finish(generated):
                break

            # If a round produced no tool activity at all, force a stronger retry prompt.
            no_tool_activity = not self._messages_have_tool_activity([*generated, *verified])
            if no_tool_activity and round_index + 1 < self.max_refinement_rounds_:
                self._emit_progress("retry", "no effective tool activity detected; forcing tool-call format")
                format_hint = UserTextMessage(
                    content=(
                        "FORMAT REQUIREMENT: In the next response, do not output raw JSON or prose-only plans. "
                        "Call concrete tools (read_file/search/list_dir/apply_patch/run_tests/run_command) with valid names."
                    )
                )
                context = [*self._compose_retry_context(context, analyzed, generated, verified), format_hint]
                continue

            if round_index + 1 < self.max_refinement_rounds_:
                self._emit_progress("retry", "task not completed yet, retrying with refined context")
                context = self._compose_retry_context(context, analyzed, generated, verified)

        if not final_messages:
            print("Agent: (No response)")
            return

        if not self._has_completion_token(final_messages) and not self._messages_have_progress_tool_activity(final_messages):
            self._emit_progress("finish", "max rounds reached without completion signal; committing last messages for debugging")
        else:
            self._emit_progress("finish", f"committing {len(final_messages)} messages")
        self._commit_turn(user_input=user_input, llm_messages=final_messages)

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