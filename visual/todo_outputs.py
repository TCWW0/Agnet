"""TODO 工具可视化示例脚本

该脚本演示如何构造 `ToolMessage` 调用 `TODOTool.run()`，
并以结构化 JSON（格式化）方式打印每次调用的请求与返回。

运行（在项目根目录）：
  python visual\todo_outputs.py

输出为一系列 JSON 对象，每个对象包含：
  - operation: 操作名称
  - request: 发送给工具的 `ToolMessage`（dict）
  - result: 工具返回的 `ToolResult`（dict）

注意：脚本使用内存后端（不会写盘），可安全运行。
"""
from pathlib import Path
import sys

# Ensure project root is on sys.path so `frame` package imports work when running this script
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import json
import threading
from typing import Any, Dict, Optional

from frame.tool.todo import TODOTool
from frame.core.message import ToolMessage
from frame.tool.persistence import PersistenceBackend


class InMemoryBackend(PersistenceBackend):
    """简单的内存持久化后端，仅用于演示（线程安全）。"""
    def __init__(self):
        self._lock = threading.Lock()
        # 与 JsonFileBackend 相同的 state shape
        self._state: Dict[str, Any] = {"next_id": 1, "items": [], "schema_version": 1}

    def load(self) -> Dict[str, Any]:
        with self._lock:
            # 返回深拷贝，避免外部修改内部 state
            return json.loads(json.dumps(self._state))

    def persist(self, state: Dict[str, Any]) -> None:
        with self._lock:
            # 存储深拷贝
            self._state = json.loads(json.dumps(state))

    def backup(self) -> None:  # pragma: no cover - optional
        return None

    def close(self) -> None:  # pragma: no cover - optional
        return None


def _show_operation(name: str, request_tm: ToolMessage, result_tr: Any) -> None:
    obj = {
        "operation": name,
        "request": request_tm.to_dict() if hasattr(request_tm, "to_dict") else str(request_tm),
        "result": result_tr.to_dict() if hasattr(result_tr, "to_dict") else str(result_tr),
    }
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main() -> None:
    backend = InMemoryBackend()
    todo = TODOTool(storage_backend=backend)

    # 1) add 第一个
    tm_add1 = ToolMessage(tool_name="TODO", tool_input={"op": "add", "content": "买菜"}, phase="call")
    tr_add1 = todo.run(tm_add1)
    _show_operation("add: 买菜", tm_add1, tr_add1)
    id1: Optional[int] = None
    try:
        if isinstance(tr_add1.output, dict):
            id1 = tr_add1.output.get("id")
    except Exception:
        id1 = None

    # 2) add 第二个
    tm_add2 = ToolMessage(tool_name="TODO", tool_input={"op": "add", "content": "写报告"}, phase="call")
    tr_add2 = todo.run(tm_add2)
    _show_operation("add: 写报告", tm_add2, tr_add2)
    id2: Optional[int] = None
    try:
        if isinstance(tr_add2.output, dict):
            id2 = tr_add2.output.get("id")
    except Exception:
        id2 = None

    # 3) list all
    tm_list = ToolMessage(tool_name="TODO", tool_input={"op": "list"}, phase="call")
    tr_list = todo.run(tm_list)
    _show_operation("list: all", tm_list, tr_list)

    # 4) get item 1
    if id1 is not None:
        tm_get = ToolMessage(tool_name="TODO", tool_input={"op": "get", "id": id1}, phase="call")
        tr_get = todo.run(tm_get)
        _show_operation(f"get: id={id1}", tm_get, tr_get)

        # 5) update item 1 -> COMPLETED
        tm_update = ToolMessage(tool_name="TODO", tool_input={"op": "update", "id": id1, "status": "COMPLETED"}, phase="call")
        tr_update = todo.run(tm_update)
        _show_operation(f"update: id={id1} status=COMPLETED", tm_update, tr_update)

        # 6) add_response to item 1
        tm_resp = ToolMessage(tool_name="TODO", tool_input={"op": "add_response", "id": id1, "response": "已完成买菜", "by": "assistant"}, phase="call")
        tr_resp = todo.run(tm_resp)
        _show_operation(f"add_response: id={id1}", tm_resp, tr_resp)

        # 7) delete item 1
        tm_del = ToolMessage(tool_name="TODO", tool_input={"op": "delete", "id": id1}, phase="call")
        tr_del = todo.run(tm_del)
        _show_operation(f"delete: id={id1}", tm_del, tr_del)

    # 8) claim / claim-fail / release for item 2
    if id2 is not None:
        tm_claim = ToolMessage(tool_name="TODO", tool_input={"op": "claim", "id": id2, "by": "agent-A"}, phase="call")
        tr_claim = todo.run(tm_claim)
        _show_operation(f"claim: id={id2} by=agent-A", tm_claim, tr_claim)

        tm_claim_fail = ToolMessage(tool_name="TODO", tool_input={"op": "claim", "id": id2, "by": "other"}, phase="call")
        tr_claim_fail = todo.run(tm_claim_fail)
        _show_operation(f"claim (expected fail): id={id2} by=other", tm_claim_fail, tr_claim_fail)

        tm_release = ToolMessage(tool_name="TODO", tool_input={"op": "release", "id": id2, "by": "agent-A"}, phase="call")
        tr_release = todo.run(tm_release)
        _show_operation(f"release: id={id2} by=agent-A", tm_release, tr_release)

    # final list
    tm_final = ToolMessage(tool_name="TODO", tool_input={"op": "list"}, phase="call")
    tr_final = todo.run(tm_final)
    _show_operation("final list", tm_final, tr_final)


if __name__ == "__main__":
    main()
