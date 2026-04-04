import os
import json
import tempfile
import unittest

from frame.tool.persistence import JsonFileBackend
from frame.tool.todo import TODOTool


class TestTODOPersistence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="todo-test-")
        self.path = os.path.join(self.tmpdir, "todo.json")
        self.backend = JsonFileBackend(self.path)

    def test_add_and_load(self):
        tool = TODOTool(storage_backend=self.backend)
        r1 = tool.add("task one")
        self.assertTrue(r1.get("ok"))
        self.assertEqual(r1.get("id"), 1)

        r2 = tool.add("task two")
        self.assertTrue(r2.get("ok"))
        self.assertEqual(r2.get("id"), 2)

        # Create new tool with same backend and verify items loaded
        tool2 = TODOTool(storage_backend=self.backend)
        lst = tool2.list()
        self.assertTrue(isinstance(lst, dict))
        self.assertTrue(lst.get("ok"))
        items = lst.get("items") or []
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 2)
        self.assertIsInstance(items[0], dict)
        self.assertIsInstance(items[1], dict)
        self.assertEqual(items[0].get("id"), 1)
        self.assertEqual(items[1].get("id"), 2)

    def test_claim_and_response_persist(self):
        tool = TODOTool(storage_backend=self.backend)
        r = tool.add("claim-task")
        self.assertIsInstance(r, dict)
        tid_val = r.get("id")
        self.assertIsInstance(tid_val, int)
        tid = int(tid_val) # type: ignore
        c = tool.claim(tid, by="tester")
        self.assertIsInstance(c, dict)
        self.assertTrue(c.get("ok"))

        a = tool.add_response(tid, "answer", by="tester")
        self.assertIsInstance(a, dict)
        self.assertTrue(a.get("ok"))

        # reload
        tool2 = TODOTool(storage_backend=self.backend)
        g = tool2.get(tid)
        self.assertIsInstance(g, dict)
        self.assertTrue(g.get("ok"))
        item = g.get("item") or {}
        self.assertIsInstance(item, dict)
        self.assertEqual(item.get("claimed_by"), "tester")
        resps = item.get("responses")
        self.assertIsInstance(resps, list)
        self.assertGreater(len(resps), 0) # type: ignore
        last = resps[-1] # type: ignore
        self.assertIsInstance(last, dict)
        self.assertEqual(last.get("content"), "answer")


if __name__ == "__main__":
    unittest.main()
