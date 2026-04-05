import os
import json
import tempfile
import unittest

from frame.tool.persistence import JsonFileBackend
from frame.tool.todo import TODOTool
from frame.tool.registry import ToolRegistry
from frame.core.config import AgentConfig

from frame.agent.todo_agent import TODOAgent
from frame.agent.processor_agent import TODOProcessorAgent
from frame.agent.summarizer_agent import TODOSummarizerAgent
from frame.agent.workflow_agent import WorkflowAgent
from frame.core.llm import LLMClient


class SplitDummyLLM(LLMClient):
    def __init__(self):
        # avoid calling base initializer which may contact external services
        self.config = None

    def invoke(self, prompt: str) -> str:
        # return two simple tasks as JSON array
        return json.dumps([{"content": "task A"}, {"content": "task B"}], ensure_ascii=False)


class ProcDummyLLM(LLMClient):
    def __init__(self):
        self.config = None

    def invoke(self, prompt: str) -> str:
        # produce a predictable answer
        return "Processed result"


class SumDummyLLM(LLMClient):
    def __init__(self):
        self.config = None

    def invoke(self, prompt: str) -> str:
        return "FINAL_SUMMARY"


class TestWorkflowIntegration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="wf-test-")
        self.path = os.path.join(self.tmpdir, "todo.json")
        self.backend = JsonFileBackend(self.path)
        self.registry = ToolRegistry()
        self.todo = TODOTool(storage_backend=self.backend)
        self.registry.register(self.todo)

    def test_workflow_end_to_end(self):
        cfg = AgentConfig.from_env()

        todo_agent = TODOAgent("TODOAgent", cfg, SplitDummyLLM(), tool_registry=self.registry)
        proc_agent = TODOProcessorAgent("Processor", cfg, ProcDummyLLM(), tool_registry=self.registry)
        sum_agent = TODOSummarizerAgent("Summ", cfg, SumDummyLLM(), tool_registry=self.registry)

        wf = WorkflowAgent("Workflow", cfg, SumDummyLLM(), tool_registry=self.registry, todo_agent=todo_agent, processor_agent=proc_agent, summarizer_agent=sum_agent)
        wf.build()

        out = wf.think("请帮我处理以下任务并总结")
        # now the agent returns plain natural text (summary_text) directly
        self.assertIsInstance(out, str)
        self.assertTrue(out.strip())
        self.assertEqual(out, "FINAL_SUMMARY")

        # verify a summary item exists in the TODO list
        lst = self.todo.list()
        items = lst.get("items") or []
        found = [it for it in items if (isinstance(it.get("metadata"), dict) and it.get("metadata").get("type") == "summary")]
        self.assertTrue(len(found) >= 1)


if __name__ == "__main__":
    unittest.main()
