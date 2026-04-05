import json
import logging
import os
import tempfile
import uuid
from typing import List, Optional

from frame.tool.todo import TODOTool
from frame.tool.persistence import JsonFileBackend
from frame.tool.registry import ToolRegistry
from frame.core.config import AgentConfig, LLMConfig
from frame.core.llm import LLMClient
from frame.core.base_agent import BaseAgent
from frame.core.logging_config import setup_logging
from .todo_agent import TODOAgent
from .processor_agent import TODOProcessorAgent
from .summarizer_agent import TODOSummarizerAgent


class WorkflowAgent(BaseAgent):
    """Orchestrates: split -> process (serial) -> summarize.

    Behavior:
    - Uses injected/shared ToolRegistry so all agents operate on same TODOTool.
    - Respects AgentConfig.max_rounds for retry/loop limit.
    - Logs progress at split, per-task completion, and summary start/end.
    - Returns summary payload and persists a summary TODO item.
    """

    def __init__(
        self,
        name: str,
        config: AgentConfig,
        llm: LLMClient,
        tool_registry: Optional[ToolRegistry] = None,
        todo_agent: Optional[TODOAgent] = None,
        processor_agent: Optional[TODOProcessorAgent] = None,
        summarizer_agent: Optional[TODOSummarizerAgent] = None,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.logger = logging.getLogger("agent.workflow")
        super().__init__(name, config, llm)

        # child agents may be injected; if not, create placeholders (built in build)
        self._injected_todo_agent = todo_agent
        self._injected_processor = processor_agent
        self._injected_summarizer = summarizer_agent

    def build(self):
        # ensure a TODOTool exists and is shared
        todo_tool = None
        try:
            todo_tool = self.tool_registry.get("TODO")
        except Exception:
            todo_tool = None

        if not todo_tool:
            # create temporary JSON backend file for workflow runs
            tmpdir = tempfile.mkdtemp(prefix="workflow-todo-")
            path = os.path.join(tmpdir, "todo.json")
            backend = JsonFileBackend(path)
            todo_tool = TODOTool(storage_backend=backend)
            self.tool_registry.register(todo_tool)

        # instantiate child agents if not injected
        if self._injected_todo_agent is None:
            self.todo_agent = TODOAgent("TODOAgent", self.config_, self.llm_, tool_registry=self.tool_registry)
        else:
            self.todo_agent = self._injected_todo_agent

        if self._injected_processor is None:
            self.processor_agent = TODOProcessorAgent("Processor", self.config_, self.llm_, tool_registry=self.tool_registry)
        else:
            self.processor_agent = self._injected_processor

        if self._injected_summarizer is None:
            self.summarizer_agent = TODOSummarizerAgent("Summarizer", self.config_, self.llm_, tool_registry=self.tool_registry)
        else:
            self.summarizer_agent = self._injected_summarizer

        # build child agents to ensure they initialize any internal state
        for a in (self.todo_agent, self.processor_agent, self.summarizer_agent):
            try:
                a.build()
            except Exception:
                self.logger.exception("Failed to build child agent %s", a)

        super().build()

    def _think_impl(self, input: str) -> str:
        """Top-level orchestration entry (internal _think_impl for BaseAgent).

        Input can be either a raw prompt string or a JSON object encoded as string.
        If JSON, supported fields:
          - "user_prompt" / "prompt": the actual user text to process
          - "output": "json" (default) or "text" to control return format

        Returns either a JSON string (default) or plain text (when output=="text").
        """
        # Treat input strictly as natural language prompt (do not parse JSON envelopes)
        user_prompt = input

        workflow_id = uuid.uuid4().hex

        # ensure we have a concrete TODOTool instance
        todo_tool = self.tool_registry.get("TODO")
        if not isinstance(todo_tool, TODOTool):
            try:
                tmpdir = tempfile.mkdtemp(prefix="workflow-todo-")
                path = os.path.join(tmpdir, "todo.json")
                backend = JsonFileBackend(path)
                todo_tool = TODOTool(storage_backend=backend)
                self.tool_registry.register(todo_tool)
            except Exception:
                self.logger.exception("无法创建或注册 TODOTool")
                return json.dumps({"ok": False, "error": "no_todo_tool"}, ensure_ascii=False)

        # 1) create workflow meta item
        try:
            meta_cmd = json.dumps({"op": "add", "content": f"workflow:{workflow_id}", "metadata": {"type": "workflow_meta", "workflow_id": workflow_id, "user_prompt": input}}, ensure_ascii=False)
            meta_resp = todo_tool.run(meta_cmd)
            self.logger.info("Created workflow meta: %s", meta_resp)
        except Exception:
            self.logger.exception("Failed to create workflow meta item")

        self.logger.info("Splitting input into tasks (workflow=%s)", workflow_id)
        task_ids = self.todo_agent.split_and_save(user_prompt, workflow_id=workflow_id)
        if not task_ids:
            self.logger.warning("No tasks created from input")

        self.logger.info("Created %d tasks", len(task_ids))

        # AgentConfig uses `max_rounds_`
        max_rounds = getattr(self.config_, "max_rounds_", None)
        try:
            max_rounds = int(max_rounds) if max_rounds is not None else int(os.getenv("AGENT_MAX_ROUNDS", 3))
        except Exception:
            max_rounds = 3

        incomplete = set(task_ids)
        round_idx = 0
        while round_idx < max_rounds and incomplete:
            round_idx += 1
            self.logger.info("Processing round %d/%d: %d tasks remaining", round_idx, max_rounds, len(incomplete))

            for tid in list(incomplete):
                self.logger.info("Processing task id=%s", tid)
                # call processor to handle this single task
                try:
                    params = {"mode": "process", "ids": [tid], "complete": True, "as_json": True}
                    resp = self.processor_agent.think(json.dumps(params, ensure_ascii=False))
                    try:
                        job = json.loads(resp)
                    except Exception:
                        job = {"ok": False, "error": "processor returned non-json"}

                    if job.get("ok"):
                        incomplete.discard(tid)
                        self.logger.info("Task %s completed", tid)
                    else:
                        self.logger.warning("Task %s not completed: %s", tid, job.get("error"))
                except Exception:
                    self.logger.exception("Processor agent failed for task %s", tid)

            if incomplete:
                self.logger.info("End of round %d, %d tasks still incomplete", round_idx, len(incomplete))

        if incomplete:
            self.logger.warning("Max rounds reached; tasks still incomplete: %s", sorted(incomplete))
            return json.dumps({"ok": False, "error": "max_rounds_reached", "incomplete": sorted(list(incomplete))}, ensure_ascii=False)

        # all tasks done -> summarize
        self.logger.info("All tasks completed; starting summarization (workflow=%s)", workflow_id)
        try:
            # ensure summarizer receives a concrete TODOTool
            if not isinstance(todo_tool, TODOTool):
                return json.dumps({"ok": False, "error": "invalid_todo_tool"}, ensure_ascii=False)
            summary = self.summarizer_agent.summarize(todo_tool=todo_tool, workflow_id=workflow_id, user_prompt=user_prompt)
            # self.logger.info("Summarization completed: %s", summary)
            # For Agent API we return only natural text (summary_text) so callers get plain text.
            if isinstance(summary, dict) and summary.get("ok") and "summary_text" in summary:
                return str(summary.get("summary_text"))
            # fallback: return a short error/notice text
            return "[no summary available]"
        except Exception:
            self.logger.exception("Summarization failed")
            return json.dumps({"ok": False, "error": "summarize_failed"}, ensure_ascii=False)


def main():
    setup_logging()
    cfg = AgentConfig.from_env()
    llm_cfg = LLMConfig.from_env()
    llm = LLMClient(llm_cfg)

    # prepare shared tool registry and persistent TODOTool
    reg = ToolRegistry()
    tmpdir = tempfile.mkdtemp(prefix="workflow-demo-")
    path = os.path.join(tmpdir, "todo.json")
    backend = JsonFileBackend(path)
    todo = TODOTool(storage_backend=backend)
    reg.register(todo)

    # create concrete agents using the real LLM client
    todo_agent = TODOAgent("TODOAgent", cfg, llm, tool_registry=reg)
    proc_agent = TODOProcessorAgent("Processor", cfg, llm, tool_registry=reg)
    sum_agent = TODOSummarizerAgent("Summarizer", cfg, llm, tool_registry=reg)

    wf = WorkflowAgent("Workflow", cfg, llm, tool_registry=reg, todo_agent=todo_agent, processor_agent=proc_agent, summarizer_agent=sum_agent)
    wf.build()

    print("WorkflowAgent ready. 输入 'exit' 或 'quit' 退出。")
    try:
        while True:
            try:
                user = input("输入问题> ").strip()
            except EOFError:
                break
            if not user:
                continue
            if user.lower() in ("exit", "quit"):
                break
            out = wf.think(user)
            # wf.think now returns plain natural text (summary_text) per agent contract
            print(out)
    except KeyboardInterrupt:
        print("\n退出")


if __name__ == "__main__":
    main()
