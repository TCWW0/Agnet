"""处理 `TODOTool` 中任务的 Agent。

功能：
- 从 `TODOTool` 拉取任务（按 id 列表或按状态/全部）
- 提供 `summarize` 与 `prioritize` 两种初始处理模式
- 使用 LLM 生成建议（`prioritize`），并将建议写回 `TODOTool`（可选 dry_run）

文件定位：`frame/agent/processor_agent.py`
"""
from typing import Any, Dict, List, Optional
import json
import logging

from frame.core.base_agent import BaseAgent
from frame.core.config import AgentConfig, LLMConfig
from frame.core.llm import LLMClient
from frame.tool.registry import ToolRegistry
from frame.tool.todo import TODOTool
from frame.core.prompts import TOOL_SYSTEM_PROMPT

class TODOProcessorAgent(BaseAgent):
    """对 `TODOTool` 中的任务进行处理的 Agent。

    主要职责：
      - 接受外部注入的 `ToolRegistry` 或 `TODOTool` 实例（可选）以共享数据
      - 扫描 `TODOTool` 中的项，选择一个合适的项进行思考与回答
      - 将 LLM 的回答写回 `TODOTool`（作为 responses）并可选地更新状态

    支持 mode:
      - summarize: 列出任务摘要
      - process: 选择单个任务并使用 LLM 生成回答，写回到该项的 responses
    """

    def __init__(self, name: str, config: AgentConfig, llm: LLMClient, tool_registry: Optional[ToolRegistry] = None, todo_tool: Optional[TODOTool] = None):
        # 支持注入外部 registry 或直接注入 TODOTool
        if tool_registry is not None:
            self.tool_registry = tool_registry
        else:
            self.tool_registry = ToolRegistry()

        if todo_tool is not None:
            # 若外部直接提供 todotool，则在 registry 中注册它（覆盖同名）
            try:
                self.tool_registry.register(todo_tool)
            except Exception:
                pass
        else:
            # 确保至少有一个 TODO 工具可用
            if "TODO" not in self.tool_registry.list_tools():
                self.tool_registry.register(TODOTool())

        super().__init__(name, config, llm)

    def init_sys_prompt(self) -> str:
        tools = self.tool_registry.list_tools()
        desc_lines = []
        for t in tools:
            try:
                desc = self.tool_registry.describe(t)
            except Exception:
                desc = ""
            desc_lines.append(f"- {t}: {desc}")
        return TOOL_SYSTEM_PROMPT + "\n\n可用的工具列表：\n" + "\n".join(desc_lines)

    def _parse_input(self, input_str: str) -> Dict[str, Any]:
        """解析用户输入，支持 JSON 或简单的短命令。

        优先尝试 JSON，例如：
        {"mode":"prioritize","ids":[1,2],"dry_run":true,"as_json":false}
        否则简单解析："prioritize ids=1,2 dry_run=false"
        """
        try:
            obj = json.loads(input_str)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        parts = input_str.strip().split()
        out: Dict[str, Any] = {}
        if not parts:
            return out
        out["mode"] = parts[0]
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k == "ids":
                    ids = []
                    for s in v.split(","):
                        try:
                            ids.append(int(s))
                        except Exception:
                            continue
                    out["ids"] = ids
                elif k in ("dry_run", "as_json"):
                    out[k] = v.lower() in ("1", "true", "yes")
                else:
                    out[k] = v
        return out

    def _fetch_tasks(self, spec: Optional[Any]) -> List[Dict[str, Any]]:
        """从 TODOTool 拉取任务。返回任务 dict 列表。

        spec: None | list of ids | dict with filters (e.g., {"status":"PENDING"})
        """
        todo_tool = self.tool_registry.get("TODO")
        if not todo_tool:
            raise RuntimeError("TODO tool not registered")

        # helper to parse JSON response from tool.run
        def run_and_parse(cmd: str) -> Dict[str, Any]:
            res_str = todo_tool.run(cmd)
            try:
                return json.loads(res_str)
            except Exception:
                return {"ok": False, "error": "invalid tool response"}

        tasks: List[Dict[str, Any]] = []
        if spec is None:
            r = run_and_parse(json.dumps({"op": "list"}, ensure_ascii=False))
            if r.get("ok"):
                items = r.get("items")
                if isinstance(items, list):
                    tasks = [it for it in items if isinstance(it, dict)]
        elif isinstance(spec, list):
            for i in spec:
                try:
                    r = run_and_parse(json.dumps({"op": "get", "id": int(i)}, ensure_ascii=False))
                except Exception:
                    continue
                if r.get("ok"):
                    item = r.get("item")
                    if isinstance(item, dict):
                        tasks.append(item)
        elif isinstance(spec, dict):
            # 支持按 status 过滤
            status = spec.get("status")
            if status:
                r = run_and_parse(json.dumps({"op": "list", "status": status}, ensure_ascii=False))
                if r.get("ok"):
                    items = r.get("items")
                    if isinstance(items, list):
                        tasks = [it for it in items if isinstance(it, dict)]
            else:
                r = run_and_parse(json.dumps({"op": "list"}, ensure_ascii=False))
                if r.get("ok"):
                    items = r.get("items")
                    if isinstance(items, list):
                        tasks = [it for it in items if isinstance(it, dict)]
        else:
            # 尝试按原样当作 status
            r = run_and_parse(json.dumps({"op": "list", "status": str(spec)}, ensure_ascii=False))
            if r.get("ok"):
                items = r.get("items")
                if isinstance(items, list):
                    tasks = [it for it in items if isinstance(it, dict)]

        return tasks

    def _select_task(self, tasks: List[Dict[str, Any]], params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # 支持指定 id
        if not tasks:
            return None
        ids = params.get("ids")
        if ids:
            for t in tasks:
                if t.get("id") == ids[0]:
                    return t

        # 首选 PENDING 且未被 claim 的项
        for t in tasks:
            if t.get("status") == "PENDING" and not t.get("claimed_by"):
                return t

        # 否则返回第一项
        return tasks[0]

    def _build_answer_prompt(self, item: Dict[str, Any], user_context: Optional[str] = None) -> str:
        lines = [
            "你是一个知识型助手，请基于下面的任务条目内容生成对用户的回答。",
            "严格返回回答文本本身，不要包含额外的 JSON 或元信息。",
            "任务条目：",
            f"id={item.get('id')}: {item.get('content')}",
        ]
        if user_context:
            lines.append("用户上下文：")
            lines.append(user_context)
        lines.append("请基于上述内容直接给出对用户的回答：")
        return "\n".join(lines)

    def _apply_priorities(self, actions: List[Dict[str, Any]], dry_run: bool = True) -> List[Dict[str, Any]]:
        todo_tool = self.tool_registry.get("TODO")
        results: List[Dict[str, Any]] = []
        if not todo_tool:
            return [{"ok": False, "error": "TODO tool not registered"}]

        for a in actions:
            tid = a.get("id")
            pr = a.get("priority")
            if tid is None or pr is None:
                results.append({"ok": False, "error": "invalid action"})
                continue
            if dry_run:
                results.append({"ok": True, "id": tid, "priority": pr, "dry_run": True})
            else:
                cmd = json.dumps({"op": "update", "id": int(tid), "metadata": {"priority": int(pr)}}, ensure_ascii=False)
                try:
                    rstr = todo_tool.run(cmd)
                    r = json.loads(rstr)
                except Exception as e:
                    r = {"ok": False, "error": str(e)}
                results.append(r)

        return results

    def _think_impl(self, input: str) -> str:
        # 解析输入；支持 JSON 或命令式
        params = self._parse_input(input)
        mode = params.get("mode", "summarize")
        as_json = params.get("as_json", False)
        dry_run = params.get("dry_run", True)
        ids = params.get("ids")
        status = params.get("status")

        # 拉取任务
        spec = None
        if ids:
            spec = ids
        elif status:
            spec = {"status": status}
        tasks = self._fetch_tasks(spec)

        # 对于 summarize 模式，直接按照任务式返回任务摘要
        if mode == "summarize":
            todo_tool = self.tool_registry.get("TODO")
            lines = [f"任务摘要：共 {len(tasks)} 项"]
            for t in tasks:
                if isinstance(todo_tool, TODOTool):
                    try:
                        lines.append(todo_tool.format_item(t))
                    except Exception:
                        lines.append(str(t))
                else:
                    lines.append(str(t))
            if as_json:
                return json.dumps({"ok": True, "items": tasks}, ensure_ascii=False)
            return "\n".join(lines)

        if mode == "process":
            if not tasks:
                return "没有找到待处理的任务"

            todo_tool = self.tool_registry.get("TODO")
            if not todo_tool:
                return "TODO 工具未注册"

            # 选择一个任务
            sel = self._select_task(tasks, params)
            if not sel:
                return "未能选择到任务"

            task_id = sel.get("id")

            # helper
            def run_and_parse(cmd: str) -> Dict[str, Any]:
                t = self.tool_registry.get("TODO")
                if not t:
                    return {"ok": False, "error": "TODO tool not registered"}
                try:
                    r = t.run(cmd)
                    return json.loads(r)
                except Exception:
                    return {"ok": False, "error": "invalid tool response"}

            # claim
            claim_res = run_and_parse(json.dumps({"op": "claim", "id": task_id, "by": self.name_}, ensure_ascii=False))
            if not claim_res.get("ok"):
                # 如果 claim 失败，继续返回错误信息
                return f"claim 失败: {claim_res.get('error')}"

            # 构造 prompt 并调用 LLM
            user_context = params.get("context") or params.get("user_prompt") or None
            prompt = self._build_answer_prompt(sel, user_context)
            try:
                answer = self.llm_.invoke(prompt)
            except Exception:
                logging.getLogger("agent.processor").exception("LLM 调用失败")
                # release 并返回错误
                run_and_parse(json.dumps({"op": "release", "id": task_id, "by": self.name_}, ensure_ascii=False))
                return "LLM 调用失败"

            # 写回回答
            addresp = run_and_parse(json.dumps({"op": "add_response", "id": task_id, "response": answer, "by": self.name_}, ensure_ascii=False))

            # 可选地将状态标为 COMPLETED（默认不自动完成，除非传入 complete=True）
            if params.get("complete", True):
                run_and_parse(json.dumps({"op": "update", "id": task_id, "status": "COMPLETED"}, ensure_ascii=False))

            # release
            run_and_parse(json.dumps({"op": "release", "id": task_id, "by": self.name_}, ensure_ascii=False))

            if as_json:
                return json.dumps({"ok": True, "id": task_id, "answer": answer, "add_response": addresp}, ensure_ascii=False)

            return f"基于任务 [{task_id}] 的回答：\n{answer}"

        # Fallback to unsupported mode
        return "unsupported mode: " + str(mode)



if __name__ == "__main__":
    # demo
    from frame.core.logging_config import setup_logging
    setup_logging()
    cfg = AgentConfig.from_env()
    llm_cfg = LLMConfig.from_env()
    llm = LLMClient(llm_cfg)
    # 为 demo 准备一个共享的 TODOTool，并在其中添加示例任务

    reg = ToolRegistry()
    todo = TODOTool(storage_path="processor_demo.json")
    reg.register(todo)
    # 添加示例任务
    todo.run(json.dumps({"op": "add", "content": "了解 LLM 定义和特点"}, ensure_ascii=False))
    todo.run(json.dumps({"op": "add", "content": "学习 LLM 的历史和发展"}, ensure_ascii=False))
    todo.run(json.dumps({"op": "add", "content": "掌握 LLM 的基本概念和技术"}, ensure_ascii=False))
    todo.run(json.dumps({"op": "add", "content": "实践 LLM 在自然语言处理中的应用"}, ensure_ascii=False))

    agent = TODOProcessorAgent("Processor", cfg, llm, tool_registry=reg)
    agent.build()

    # 示例：先列出当前所有任务
    print("=== Summarize ===")
    print(agent.think("summarize"))

    # 示例：处理首个任务（process 模式）
    print("\n=== Process (process mode) ===")
    print(agent.think(json.dumps({"mode": "process", "complete": True}, ensure_ascii=False)))

    # 再次列出当前所有任务，观察状态变化
    print("\n=== Summarize After Processing ===")
    print(agent.think("summarize"))
