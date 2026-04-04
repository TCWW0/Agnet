"""基于一个TODOTool的Agent，用于演示如何使用TODOTool进行任务的拆解以及记录"""

from frame.core.base_agent import BaseAgent
from frame.core.config import AgentConfig, LLMConfig
from frame.core.llm import LLMClient
from frame.core.message import Message
from frame.tool import ToolRegistry
from frame.tool.todo import TODOTool
from frame.core.prompts import TOOL_SYSTEM_PROMPT
import json
import re
import logging
from frame.core.logging_config import setup_logging

class TODOAgent(BaseAgent):
    def __init__(self, name: str, config: AgentConfig, llm: LLMClient):
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(TODOTool())
        super().__init__(name, config, llm)

    def init_sys_prompt(self) -> str:
        # 组合可用工具的描述，供模型参考
        tools = self.tool_registry.list_tools()
        desc_lines = []
        for t in tools:
            try:
                desc = self.tool_registry.describe(t)
            except Exception:
                desc = ""
            desc_lines.append(f"- {t}: {desc}")
        return TOOL_SYSTEM_PROMPT + "\n\n可用的工具列表如下：\n" + "\n".join(desc_lines)
    
    def _think_impl(self, input: str) -> str:
        # 将用户输入加入历史
        self.history.append(Message(role="user", action="input", content=input))

        # 构造给 LLM 的提示，要求返回一个 JSON 数组，每个元素为 {"content": "...", "metadata": {...} }
        prompt = self.sys_prompt_ + "\n\n" #type: ignore
        # 附带历史上下文
        for m in self.history:
            try:
                prompt += m.to_prompt() + "\n"
            except Exception:
                prompt += str(m) + "\n"

        prompt += (
            "请把上面的用户输入拆分为若干个不相互依赖的子任务。\n"
            "严格只输出一个 JSON 数组，数组中每个元素为对象，字段至少包含:\n"
            "  - \"content\": 子任务描述（字符串）\n"
            "可选字段:\n"
            "  - \"metadata\": 对象，用于携带额外信息\n"
            "示例输出（仅示例）：\n"
            "  [{\"content\":\"撰写报告\"},{\"content\":\"制作 PPT\"}]\n"
        )

        try:
            response = self.llm_.invoke(prompt)
        except Exception as e:
            logging.getLogger("agent.todo").exception("LLM 调用失败")
            # 回退到简单分割策略
            tasks = self._simple_split(input)
            response = json.dumps(tasks, ensure_ascii=False)

        # 尝试从模型输出中抽取 JSON 数组
        tasks = []
        try:
            tasks = json.loads(response)
            if isinstance(tasks, dict) and "tasks" in tasks:
                tasks = tasks["tasks"]
            if not isinstance(tasks, list):
                raise ValueError("not a list")
        except Exception:
            # 尝试提取首个方括号包裹的 JSON
            start = response.find("[")
            end = response.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    tasks = json.loads(response[start:end+1])
                except Exception:
                    tasks = []

        if not tasks:
            tasks = self._simple_split(input)

        # 逐项调用 TODO 工具进行保存
        todo_tool = self.tool_registry.get("TODO")
        if not todo_tool:
            return json.dumps({"ok": False, "error": "TODO tool not registered"}, ensure_ascii=False)

        created = []
        for t in tasks:
            # 支持直接字符串或对象
            if isinstance(t, str):
                content = t
                metadata = None
            elif isinstance(t, dict):
                content = t.get("content") or t.get("task") or str(t)
                metadata = t.get("metadata")
            else:
                content = str(t)
                metadata = None

            if not isinstance(content, str) or not content.strip():
                continue

            call_input = json.dumps({"op": "add", "content": content, "metadata": metadata}, ensure_ascii=False)
            res_str = todo_tool.run(call_input)
            try:
                res_obj = json.loads(res_str)
            except Exception:
                res_obj = {"ok": False, "raw": res_str}
            created.append({"input": {"content": content, "metadata": metadata}, "result": res_obj})

        # 返回创建的记录摘要（仅返回是否成功与可视化的已保存条目，不返回完整数据）
        saved_display = []
        for c in created:
            res = c.get("result", {})
            if isinstance(res, dict) and res.get("ok") and res.get("item"):
                # ToolRegistry.get() 返回的是 Tool 类型，静态类型检查器无法推断 TODOTool 的扩展方法
                # 此处做运行时类型检查以安全调用 format_item
                if isinstance(todo_tool, TODOTool):
                    try:
                        saved_display.append(todo_tool.format_item(res["item"]))
                    except Exception:
                        saved_display.append(f"[id:{res.get('id')}] saved")
                else:
                    try:
                        saved_display.append(str(res.get("item")))
                    except Exception:
                        saved_display.append(f"[id:{res.get('id')}] saved")
            else:
                err = res.get("error") if isinstance(res, dict) else str(res)
                saved_display.append(f"failed: {err}")

        # 将输出格式化为可读文本；不返回完整 JSON，便于人工查看
        success_any = any(not s.startswith("failed:") for s in saved_display)
        if success_any:
            lines = ["任务拆分并已保存到内存 TODO 工具，已保存项："]
            for i, line in enumerate(saved_display, start=1):
                lines.append(f"{i}. {line}")
            return "\n".join(lines)
        else:
            # 全部失败
            return "任务拆分失败：" + "; ".join(saved_display)

    def _simple_split(self, text: str):
        # 简单分割策略：按换行或中文/英文分隔符切分
        # 支持常见中英文分隔符，包括中文顿号、全角逗号等
        parts = [p.strip() for p in re.split(r"[\n。；、，;,.]+", text) if p.strip()]
        return [{"content": p} for p in parts]


if __name__ == "__main__":
    # 使用虚拟环境的 Python 在项目根运行此模块：
    # e:\project\agent\.venv\Scripts\python.exe -m frame.agent.todo_agent
    setup_logging()
    cfg = AgentConfig.from_env()
    llm_cfg = LLMConfig.from_env()
    llm = LLMClient(llm_cfg)
    agent = TODOAgent("DemoTODOAgent", cfg, llm)
    agent.build()
    user_input = "请给我分析解释一下什么是LLM，并帮我列出学习LLM的几个重要方面。"
    print("用户输入:", user_input)
    result = agent.think(user_input)
    print("Agent 返回:")
    print(result)


