"""DeepThoughtAgent：使用 TODOAgent + ProcessAgent + SummarizerAgent 的编排器。"""

import json
from typing import Any, Dict, List, Optional

from frame.agent.process_agent import ProcessAgent
from frame.agent.summarizer_agent import SummarizerAgent
from frame.agent.todo_agent import TODOAgent
from frame.core.base_agent import BaseAgent
from frame.core.config import AgentConfig, LLMConfig
from frame.core.llm import LLMClient
from frame.core.logger import Logger, Level
from frame.core.message import Message, ToolMessage
from frame.tool.todo import TODOTool


class DeepThoughtAgent(BaseAgent):
    """基础版编排 Agent。

    注意：该 Agent 本身不直接调用 LLM，而是调度子 Agent 完成三阶段流程。
    """

    def __init__(
        self,
        name: str,
        config: AgentConfig,
        llm: LLMClient,
        workflow_id: str = "deep_thought_workflow",
        logger: Optional[Logger] = None,
        todo_tool: Optional[TODOTool] = None,
        max_process_loops: int = 64,
    ):
        m_logger = logger or Logger(file_name=f"{name}.log", min_level=Level.DEBUG)
        super().__init__(name, config, llm, workflow_id=workflow_id, logger=m_logger)

        self.todo_tool_ = todo_tool or TODOTool(storage_path="todo_state_1.json")
        self.max_process_loops_ = max(1, int(max_process_loops))
        self.last_plan_id_: Optional[str] = None

        # 子 Agent 共享同一个 TODOTool 和 workflow_id
        self.todo_agent_ = TODOAgent(
            name=f"{name}_TODOAgent",
            config=config,
            llm=llm,
            workflow_id=workflow_id,
            logger=m_logger,
            todo_tool=self.todo_tool_,
        )
        self.process_agent_ = ProcessAgent(
            name=f"{name}_ProcessAgent",
            config=config,
            llm=llm,
            workflow_id=workflow_id,
            logger=m_logger,
            todo_tool=self.todo_tool_,
        )
        self.summarizer_agent_ = SummarizerAgent(
            name=f"{name}_SummarizerAgent",
            config=config,
            llm=llm,
            workflow_id=workflow_id,
            logger=m_logger,
            todo_tool=self.todo_tool_,
        )

        self.build()

    def init_sys_prompt(self) -> str:
        return (
            "你是 DeepThoughtAgent 的编排器，不直接求解问题。"
            "你负责顺序调度 TODOAgent、ProcessAgent、SummarizerAgent。"
        )

    @staticmethod
    def _build_plan_request(user_input: str) -> str:
        return json.dumps(
            {
                "objective": user_input,
                "source": "deep_thought",
                "force_decompose": True,
            },
            ensure_ascii=False,
        )

    def _list_plan_items(self, plan_id: str) -> List[Dict[str, Any]]:
        tr = self.todo_tool_.run(ToolMessage(tool_name="TODO", tool_input={"op": "list"}, phase="call"))
        if tr.status != "ok" or not isinstance(tr.output, list):
            return []
        all_items = [it for it in tr.output if isinstance(it, dict)]
        selected: List[Dict[str, Any]] = []
        for it in all_items:
            meta_any = it.get("metadata")
            meta: Dict[str, Any] = meta_any if isinstance(meta_any, dict) else {}
            if str(meta.get("plan_id") or "") == plan_id:
                selected.append(it)
        selected.sort(key=lambda x: int(x.get("id", 0) or 0))
        return selected

    # 计算当前等待处理的任务数量（即状态为 PENDING 的任务数）
    def _pending_count(self, plan_id: str) -> int:
        items = self._list_plan_items(plan_id)
        count = 0
        for it in items:
            status = str(it.get("status") or "").upper()
            if status == "PENDING":
                count += 1
        return count

    def _think_impl(self, input: str) -> str:
        self.append_history(Message(role="user", action="input", content=input))
        self.logger_.info("DeepThoughtAgent 开始编排，workflow_id=%s", self.workflow_id_)

        # 阶段1：规划
        self.logger_.info("DeepThoughtAgent 阶段1：调用 TODOAgent 进行任务拆解")
        plan_request = self._build_plan_request(input)
        self.logger_.info("DeepThoughtAgent 规划请求已包装为强制拆解模式")
        plan_text = self.todo_agent_.think(plan_request)
        plan_id = self.todo_agent_.last_plan_id_
        self.last_plan_id_ = plan_id
        if not plan_id:
            final = "规划阶段未生成有效 plan_id，流程终止。"
            self.logger_.error("DeepThoughtAgent 失败：缺少 plan_id")
            self.append_history(Message(role="assistant", action="final", content=final))
            return final

        total_items = len(self._list_plan_items(plan_id))
        self.logger_.info("DeepThoughtAgent 规划完成，plan_id=%s，任务数=%d", plan_id, total_items)

        # 阶段2：逐条执行
        loops = 0
        while loops < self.max_process_loops_:
            before = self._pending_count(plan_id)
            if before <= 0:
                break

            loops += 1
            self.logger_.info(
                "DeepThoughtAgent 阶段2：第%d轮调用 ProcessAgent，plan_id=%s，待执行=%d",
                loops,
                plan_id,
                before,
            )
            process_input = json.dumps({"objective": input, "plan_id": plan_id}, ensure_ascii=False)
            process_text = self.process_agent_.think(process_input)
            self.logger_.info("DeepThoughtAgent ProcessAgent 返回：%s", process_text)

            after = self._pending_count(plan_id)
            if after >= before:
                self.logger_.warning(
                    "DeepThoughtAgent 检测到待执行任务未减少（before=%d, after=%d），提前结束执行循环",
                    before,
                    after,
                )
                break

        remaining = self._pending_count(plan_id)
        self.logger_.info("DeepThoughtAgent 执行阶段结束，轮次=%d，剩余待执行=%d", loops, remaining)

        # 阶段3：汇总
        self.logger_.info("DeepThoughtAgent 阶段3：调用 SummarizerAgent 进行总结")
        summarize_input = json.dumps({"objective": input, "plan_id": plan_id, "mode": "full"}, ensure_ascii=False)
        summary_text = self.summarizer_agent_.think(summarize_input)
        self.logger_.info("DeepThoughtAgent 汇总完成")

        final = (
            f"规划阶段输出：{plan_text}\n\n"
            f"执行阶段：已执行 {loops} 轮，剩余待执行 {remaining} 项。\n\n"
            f"最终总结：{summary_text}"
        )
        self.append_history(Message(role="assistant", action="final", content=final))
        return final


if __name__ == "__main__":
    llm_config = LLMConfig.from_env()
    llm_client = LLMClient(llm_config)
    agent_config = AgentConfig.from_env()
    deep_agent = DeepThoughtAgent(
        name="DeepThoughtAgent",
        config=agent_config,
        llm=llm_client,
        workflow_id="deep_thought_workflow",
    )
    # ensure agent is built
    deep_agent.build()

    print("DeepThoughtAgent ready. 输入 'exit' 或 'quit' 退出。")
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
            try:
                resp = deep_agent.think(user)
            except Exception as e:
                deep_agent.logger_.error("DeepThoughtAgent 调用失败: %s", str(e))
                resp = "[agent error]"
            print("Agent回答：", resp)
    except KeyboardInterrupt:
        print("\n退出")

    deep_agent.logger_.info("DeepThoughtAgent 退出，当前历史消息已保存到日志")
    deep_agent.logger_.info("DeepThoughtAgent 历史：\n%s", deep_agent.history_to_str())
