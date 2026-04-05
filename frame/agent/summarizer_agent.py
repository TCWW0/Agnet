"""汇总 Agent：读取 `TODOTool` 中已完成任务的 responses，构建 prompt 并调用 LLM 生成最终总结。

注意：该 Agent 不负责轮询/驱动流程，由上层 Workflow/调用方负责触发。该类提供 `summarize(...)` 方法供外部调用。
"""
from typing import Any, Dict, List, Optional
import json
import logging
import os
import time

from frame.core.base_agent import BaseAgent
from frame.core.config import AgentConfig
from frame.core.llm import LLMClient
from frame.tool.registry import ToolRegistry
from frame.tool.todo import TODOTool


class TODOSummarizerAgent(BaseAgent):
    def __init__(self, name: str, config: AgentConfig, llm: LLMClient, tool_registry: Optional[ToolRegistry] = None, lock_dir: Optional[str] = None):
        super().__init__(name, config, llm)
        self.tool_registry = tool_registry or ToolRegistry()
        self.lock_dir = lock_dir

    def _run_and_parse(self, todo_tool: TODOTool, cmd: Dict[str, Any]) -> Dict[str, Any]:
        try:
            r = todo_tool.run(json.dumps(cmd, ensure_ascii=False))
            return json.loads(r)
        except Exception:
            return {"ok": False, "error": "invalid tool response"}

    def collect_tasks(self, todo_tool: TODOTool, workflow_id: Optional[str] = None, task_ids: Optional[List[int]] = None, require_completed: bool = True) -> List[Dict[str, Any]]:
        tasks: List[Dict[str, Any]] = []
        if task_ids:
            for i in task_ids:
                try:
                    r = self._run_and_parse(todo_tool, {"op": "get", "id": int(i)})
                except Exception:
                    continue
                if r.get("ok"):
                    it = r.get("item")
                    if isinstance(it, dict):
                        tasks.append(it)
            return tasks

        # otherwise list and filter by workflow_id if provided
        r = self._run_and_parse(todo_tool, {"op": "list"})
        if not r.get("ok"):
            return []
        items = r.get("items")
        if not isinstance(items, list):
            return []
        for it in items:
            if not isinstance(it, dict):
                continue
            # skip summary items
            meta = it.get("metadata") or {}
            if isinstance(meta, dict) and meta.get("type") == "summary":
                continue
            if workflow_id:
                if not isinstance(meta, dict):
                    continue
                if meta.get("workflow_id") != workflow_id:
                    continue
            if require_completed and it.get("status") != "COMPLETED":
                continue
            tasks.append(it)
        return tasks

    def already_summarized(self, todo_tool: TODOTool, workflow_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not workflow_id:
            return None
        r = self._run_and_parse(todo_tool, {"op": "list"})
        if not r.get("ok"):
            return None
        items = r.get("items") or []
        for it in items:
            if not isinstance(it, dict):
                continue
            meta = it.get("metadata") or {}
            if isinstance(meta, dict) and meta.get("type") == "summary" and meta.get("workflow_id") == workflow_id:
                return it
        return None

    def build_prompt(self, tasks: List[Dict[str, Any]], user_prompt: Optional[str] = None, response_strategy: str = "last", style: str = "concise") -> str:
        lines: List[str] = []
        if user_prompt:
            lines.append("原始问题：")
            lines.append(user_prompt)
            lines.append("")
        lines.append("下面是分解的任务及对应的处理结果，请基于这些内容生成针对原始问题的最终综合回答。")
        lines.append("")
        for t in tasks:
            tid = t.get("id")
            content = t.get("content")
            lines.append(f"任务 [{tid}]: {content}")
            resps = t.get("responses") or []
            if response_strategy == "last":
                if isinstance(resps, list) and resps:
                    last = resps[-1]
                    if isinstance(last, dict):
                        lines.append(f"  最新回答: {last.get('content')}")
                    else:
                        lines.append(f"  最新回答: {str(last)}")
                else:
                    lines.append("  最新回答: (无)")
            elif response_strategy == "all":
                if isinstance(resps, list) and resps:
                    for idx, rr in enumerate(resps):
                        if isinstance(rr, dict):
                            lines.append(f"    回答{idx+1}: {rr.get('content')}")
                        else:
                            lines.append(f"    回答{idx+1}: {str(rr)}")
                else:
                    lines.append("  回答: (无)")
            lines.append("")

        lines.append("请根据以上内容直接给出对用户的最终回答，语言简洁、要点清楚。不要包含不必要的元信息。")
        if style == "concise":
            lines.append("输出要求：用一段或多段总结，不要超过 400 字。")
        return "\n".join(lines)

    def _acquire_lock(self, todo_tool: TODOTool, workflow_id: Optional[str], timeout: int = 5) -> Optional[str]:
        # simple lock file in same dir as backend if available
        lock_path = None
        backend = getattr(todo_tool, "_backend", None)
        if backend and hasattr(backend, "path"):
            base = os.path.dirname(getattr(backend, "path")) or "."
            fname = f"summarize_{workflow_id or 'global'}.lock"
            lock_path = os.path.join(base, fname)
            start = time.time()
            while True:
                try:
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.close(fd)
                    return lock_path
                except FileExistsError:
                    if time.time() - start > timeout:
                        return None
                    time.sleep(0.1)
                except Exception:
                    return None
        return None

    def _release_lock(self, lock_path: Optional[str]) -> None:
        if lock_path and os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except Exception:
                pass

    def write_summary(self, todo_tool: TODOTool, summary_text: str, workflow_id: Optional[str] = None) -> Optional[int]:
        meta = {"type": "summary"}
        if workflow_id:
            meta["workflow_id"] = workflow_id
        cmd = {"op": "add", "content": summary_text, "metadata": meta}
        r = self._run_and_parse(todo_tool, cmd)
        if r.get("ok"):
            id_val = r.get("id")
            try:
                return int(id_val) if id_val is not None else None
            except Exception:
                return None
        return None

    def summarize(self, todo_tool: Optional[TODOTool] = None, tool_registry: Optional[ToolRegistry] = None, workflow_id: Optional[str] = None, task_ids: Optional[List[int]] = None, user_prompt: Optional[str] = None, as_item: bool = True, response_strategy: str = "last", require_completed: bool = True) -> Dict[str, Any]:
        # resolve todo tool
        if todo_tool is None:
            tr = tool_registry or self.tool_registry
            maybe_tool = tr.get("TODO")
            if isinstance(maybe_tool, TODOTool):
                todo_tool = maybe_tool
            else:
                return {"ok": False, "error": "TODO tool not provided"}

        # collect tasks
        tasks = self.collect_tasks(todo_tool, workflow_id=workflow_id, task_ids=task_ids, require_completed=require_completed)
        if not tasks:
            return {"ok": False, "error": "no tasks to summarize"}

        # idempotence: if already summarized, return existing
        existing = self.already_summarized(todo_tool, workflow_id)
        if existing:
            return {"ok": True, "summary_text": existing.get("content"), "summary_item": existing}

        # build prompt and call LLM
        prompt = self.build_prompt(tasks, user_prompt=user_prompt, response_strategy=response_strategy)
        try:
            self._ensure_built()
        except Exception:
            # allow not built case by not requiring sys prompt
            pass
        try:
            answer = self.llm_.invoke(prompt)
        except Exception as e:
            logging.getLogger("agent.summarizer").exception("LLM 调用失败")
            return {"ok": False, "error": f"LLM invoke failed: {e}"}

        # acquire lock and write summary
        lock = self._acquire_lock(todo_tool, workflow_id)
        try:
            sid = None
            if as_item:
                sid = self.write_summary(todo_tool, answer, workflow_id=workflow_id)
            # also update a workflow meta by creating a small metadata-only item (optional)
            try:
                # mark summarized on a workflow meta item
                if workflow_id:
                    meta_cmd = {"op": "add", "content": f"workflow {workflow_id} summarized", "metadata": {"type": "workflow_meta", "workflow_id": workflow_id, "status": "summarized"}}
                    self._run_and_parse(todo_tool, meta_cmd)
            except Exception:
                pass
            return {"ok": True, "summary_text": answer, "summary_item_id": sid}
        finally:
            self._release_lock(lock)

    def _think_impl(self, input: str) -> str:
        # support a simple JSON command to trigger summarize via think
        try:
            obj = json.loads(input)
            if not isinstance(obj, dict):
                return "invalid input"
        except Exception:
            return "invalid input"
        todo_name = obj.get("todo_name")
        workflow_id = obj.get("workflow_id")
        user_prompt = obj.get("user_prompt")
        todo_tool = None
        if todo_name:
            maybe = self.tool_registry.get(todo_name)
            if isinstance(maybe, TODOTool):
                todo_tool = maybe
        res = self.summarize(todo_tool=todo_tool, workflow_id=workflow_id, user_prompt=user_prompt)
        return json.dumps(res, ensure_ascii=False)


if __name__ == "__main__":
    # Demo: create a TODOTool with two completed tasks, run summarizer and print result
    import tempfile
    from frame.tool.persistence import JsonFileBackend
    from frame.tool.todo import TODOTool
    # Use real LLMClient for demo (configured via environment)
    from frame.core.config import LLMConfig

    tmpdir = tempfile.mkdtemp(prefix="summ-demo-")
    path = os.path.join(tmpdir, "todo.json")
    backend = JsonFileBackend(path)
    todo = TODOTool(storage_backend=backend)
    # add semantically meaningful tasks with workflow id and sample responses
    r1 = todo.add("快速开始指南：如何在本地设置并运行项目", metadata={"workflow_id": "demo-wf", "index": 1, "type": "task"})
    r2 = todo.add("测试与调试：如何运行单元测试并查看日志", metadata={"workflow_id": "demo-wf", "index": 2, "type": "task"})
    r3 = todo.add("部署建议：在生产环境部署本项目时需要注意的要点", metadata={"workflow_id": "demo-wf", "index": 3, "type": "task"})
    id1 = int(r1.get("id")) # type: ignore
    id2 = int(r2.get("id")) # type: ignore
    id3 = int(r3.get("id")) # type: ignore
    todo.add_response(id1, "创建虚拟环境：python -m venv .venv；激活：.\\.venv\\Scripts\\Activate.ps1；安装依赖：pip install -r requirements.txt；配置 .env 后运行 demo。", by="demo")
    todo.update(id1, status="COMPLETED")
    todo.add_response(id2, "运行测试：python -m unittest discover -s frame/test -v；启用日志以便定位失败；单测失败时可单独运行具体测试模块进行调试。", by="demo")
    todo.update(id2, status="COMPLETED")
    todo.add_response(id3, "部署要点：配置 LLM_BASE_URL、设置超时与重试、妥善保管 API 密钥、容器化部署并监控资源使用。", by="demo")
    todo.update(id3, status="COMPLETED")

    cfg = AgentConfig.from_env()
    llm_cfg = LLMConfig.from_env()
    llm = LLMClient(llm_cfg)
    agent = TODOSummarizerAgent("SummDemo", cfg, llm)
    agent.build()
    out = agent.summarize(todo_tool=todo, workflow_id="demo-wf", user_prompt="请对上述任务的结果生成一段面向新手的快速总结，便于快速上手本项目。")
    print(json.dumps(out, ensure_ascii=False, indent=2))