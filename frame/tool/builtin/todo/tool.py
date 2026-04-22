from __future__ import annotations

import json
from typing import Any, Dict, Optional

from frame.tool.base import BaseTool, Property, ToolDesc, ToolParameters, ToolResponse
from frame.tool.builtin.todo.manager import TodoManager
from frame.tool.builtin.todo.models import TodoStatus
from frame.tool.builtin.todo.storage import JsonTodoStorage, TodoStorage


class TodoTool(BaseTool):
    def __init__(self, filename: Optional[str] = None, storage: Optional[TodoStorage] = None) -> None:
        super().__init__(
            name="todo",
            description="管理待办事项，支持 create/list/get/update/delete 基础操作",
        )
        backend = storage or JsonTodoStorage(filename=filename)
        self.manager_ = TodoManager(storage=backend)

    @classmethod
    def desc(cls) -> ToolDesc:
        params = ToolParameters(
            properties={
                "action": Property(
                    type="string",
                    description="要执行的操作类型",
                    enum=["create", "list", "get", "update", "delete"],
                ),
                "item_id": Property(type="string", description="待办 ID，get/update/delete 时必填"),
                "text": Property(type="string", description="待办文本，create/update 时可用"),
                "status": Property(
                    type="string",
                    description="任务状态，可选 not-started | in-progress | completed",
                    enum=["not-started", "in-progress", "completed"],
                ),
            },
            required=["action"],
        )
        return ToolDesc(
            name="todo",
            description="执行 TODO 的增删改查操作",
            parameters=params,
        )

    def valid_paras(self, params: Dict[str, str]) -> bool:
        action = params.get("action")
        if action not in {"create", "list", "get", "update", "delete"}:
            return False

        if action == "create":
            text_ok = bool(str(params.get("text", "")).strip())
            status = params.get("status")
            status_ok = status is None or status in {"not-started", "in-progress", "completed"}
            return text_ok and status_ok

        if action == "list":
            status = params.get("status")
            return status is None or status in {"not-started", "in-progress", "completed"}

        if action in {"get", "delete"}:
            return bool(str(params.get("item_id", "")).strip())

        if action == "update":
            item_id_ok = bool(str(params.get("item_id", "")).strip())
            has_text = "text" in params
            has_status = "status" in params
            status_ok = params.get("status") in {"not-started", "in-progress", "completed", None}
            return item_id_ok and (has_text or has_status) and status_ok

        return False

    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        action = str(params.get("action", "")).strip()

        if action == "create":
            status = self._parse_status(params.get("status")) or TodoStatus.NOT_STARTED
            item = self.manager_.create_item(text=str(params.get("text", "")), status=status)
            return self._success({"action": action, "item": item.model_dump(mode="json")})

        if action == "list":
            status = self._parse_status(params.get("status"))
            items = self.manager_.list_items(status=status)
            return self._success(
                {
                    "action": action,
                    "count": len(items),
                    "items": [item.model_dump(mode="json") for item in items],
                }
            )

        if action == "get":
            item = self.manager_.get_item(str(params.get("item_id", "")))
            return self._success(
                {
                    "action": action,
                    "found": item is not None,
                    "item": None if item is None else item.model_dump(mode="json"),
                }
            )

        if action == "update":
            status = self._parse_status(params.get("status"))
            item = self.manager_.update_item(
                item_id=str(params.get("item_id", "")),
                text=params.get("text"),
                status=status,
            )
            return self._success({"action": action, "item": item.model_dump(mode="json")})

        if action == "delete":
            deleted = self.manager_.delete_item(str(params.get("item_id", "")))
            return self._success({"action": action, "deleted": deleted})

        return ToolResponse(tool_name=self.name, status="error", output="unsupported action")

    def _success(self, payload: Dict[str, Any]) -> ToolResponse:
        payload["storage_path"] = self.manager_.storage_path
        output = json.dumps(payload, ensure_ascii=False)
        return ToolResponse(tool_name=self.name, status="success", output=output)

    @staticmethod
    def _parse_status(raw: Any) -> Optional[TodoStatus]:
        if raw is None:
            return None
        value = str(raw).strip()
        if not value:
            return None
        return TodoStatus(value)
