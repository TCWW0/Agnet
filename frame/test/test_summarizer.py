import os
import json
import tempfile
import unittest

from frame.tool.persistence import JsonFileBackend
from frame.tool.todo import TODOTool
from frame.agent.summarizer_agent import TODOSummarizerAgent
from frame.core.config import AgentConfig


class DummyLLM:
    def invoke(self, prompt: str) -> str:
        # simple echo-ish summarization for tests (short)
        return "SUMMARY:" + (prompt[:200])


class TestTODOSummarizer(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="summ-test-")
        self.path = os.path.join(self.tmpdir, "todo.json")
        self.backend = JsonFileBackend(self.path)

    def test_summarize_creates_summary_item(self):
        todo = TODOTool(storage_backend=self.backend)
        # add two tasks with workflow_id
        r1 = todo.add("任务一", metadata={"workflow_id": "wf-1", "index": 1, "type": "task"})
        r2 = todo.add("任务二", metadata={"workflow_id": "wf-1", "index": 2, "type": "task"})
        id1 = int(r1.get("id"))
        id2 = int(r2.get("id"))

        # simulate processor results
        todo.add_response(id1, "回答一", by="proc")
        todo.update(id1, status="COMPLETED")
        todo.add_response(id2, "回答二", by="proc")
        todo.update(id2, status="COMPLETED")

        cfg = AgentConfig.from_env()
        llm = DummyLLM()
        agent = TODOSummarizerAgent("Summ", cfg, llm)
        agent.build()

        res = agent.summarize(todo_tool=todo, workflow_id="wf-1", user_prompt="请总结任务")
        self.assertTrue(res.get("ok"))
        self.assertIn("summary_text", res)

        # find summary item
        lst = todo.list()
        items = lst.get("items") or []
        found = [it for it in items if (isinstance(it.get("metadata"), dict) and it.get("metadata").get("type") == "summary")]
        self.assertTrue(len(found) >= 1)


if __name__ == "__main__":
    unittest.main()
