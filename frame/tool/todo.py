"""简化版 TODO 工具（单线程、内存存储）。

功能：支持 `add` / `get` / `list` / `update` / `delete` 操作。
输入优先解析为 JSON，例如：
  {"op":"add","content":"买菜"}
或命令式文本：
  add 买菜
  update 3 status=COMPLETED
返回值为 JSON 字符串，便于 Agent 解析。
"""
from .base import Tool, ToolParameter
from .persistence import PersistenceBackend, JsonFileBackend
import threading
import os
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple, Union
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
import json

class Status(Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

@dataclass
class TODOItem:
    id: int
    content: str
    status: Status = Status.PENDING
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 历史回答记录，每条为 {"by": str, "at": iso, "content": str, "metadata": {...}}
    responses: List[Dict[str, Any]] = field(default_factory=list)
    # 被哪个 agent claim 了（单进程设计下为标记用途）
    claimed_by: Optional[str] = None
    claimed_at: Optional[str] = None
    # 版本号便于将来实现乐观锁
    version: int = 1

# TODO: 实现持久化储存，线程安全访问等
class TODOTool(Tool):
    _backend: Optional[PersistenceBackend] = None
    def __init__(self, storage_backend: Optional[PersistenceBackend] = None, storage_path: Optional[str] = None):
        super().__init__("TODO", "一个简单的代办事项工具，支持添加、查看、管理待办事项")
        self._items: List[TODOItem] = []
        self._next_id: int = 1
        self._lock = threading.Lock()
        # storage backend selection priority:
        # 1) explicit backend injected
        # 2) compose from environment dir (TODO_JSON_PATH) + filename (storage_path)
        # 3) fallback to project-root/bin/todo.json
        if storage_backend is not None:
            self._backend = storage_backend
        else:
            # determine project root (two levels up from this file: frame/tool -> frame -> project root)
            project_root = Path(__file__).resolve().parents[2]

            # env value should indicate a directory relative to project root (or absolute)
            env_dir_val = os.getenv("TODO_JSON_PATH")
            base_dir: Path
            if env_dir_val:
                env_path = Path(env_dir_val)
                if env_path.is_absolute():
                    base_dir = env_path
                else:
                    base_dir = project_root.joinpath(env_path)
            else:
                base_dir = project_root.joinpath("bin/todo")

            # storage_path (if provided) must be a filename only (no separators)
            if storage_path:
                sp = Path(storage_path)
                if sp.name != storage_path or sp.parent != Path('.'):  # contains separators or is not a bare filename
                    raise ValueError("storage_path must be a filename (no directories). Pass only a filename.")
                filename = storage_path
            else:
                filename = "todo.json"

            full_path = str(base_dir.joinpath(filename))
            self._backend = JsonFileBackend(full_path)

        # load if backend present
        if self._backend is not None:
            try:
                self._load()
            except Exception:
                # on load failure, start empty
                self._items = []
                self._next_id = 1

    def _to_dict(self, item: TODOItem) -> Dict[str, Any]:
        return {
            "id": item.id,
            "content": item.content,
            "status": item.status.value,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "metadata": item.metadata,
            "responses": item.responses,
            "claimed_by": item.claimed_by,
            "claimed_at": item.claimed_at,
            "version": item.version,
        }

    def _find_index(self, item_id: int) -> Optional[int]:
        for i, it in enumerate(self._items):
            if it.id == item_id:
                return i
        return None

    def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            item = TODOItem(id=self._next_id, content=content, metadata=metadata or {})
            self._items.append(item)
            self._next_id += 1
            res = {"ok": True, "id": item.id, "item": self._to_dict(item)}
            self._persist()
            return res

    def get(self, item_id: int) -> Dict[str, Any]:
        idx = self._find_index(item_id)
        if idx is None:
            return {"ok": False, "error": f"item {item_id} not found"}
        return {"ok": True, "item": self._to_dict(self._items[idx])}

    def list(self, status: Optional[str] = None) -> Dict[str, Any]:
        if status:
            try:
                st = Status(status.upper()) if not isinstance(status, Status) else status
            except Exception:
                # accept exact match of enum value
                st = None
            if st:
                filtered = [self._to_dict(it) for it in self._items if it.status == st]
            else:
                filtered = [self._to_dict(it) for it in self._items]
        else:
            filtered = [self._to_dict(it) for it in self._items]
        return {"ok": True, "items": filtered}

    def update(self, item_id: int, content: Optional[str] = None, status: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        idx = self._find_index(item_id)
        if idx is None:
            return {"ok": False, "error": f"item {item_id} not found"}
        with self._lock:
            it = self._items[idx]
            changed = False
            if content is not None:
                it.content = content
                changed = True
            if status is not None:
                try:
                    it.status = Status(status.upper())
                    changed = True
                except Exception:
                    return {"ok": False, "error": f"invalid status: {status}"}
            if metadata is not None:
                it.metadata.update(metadata)
                changed = True
            if changed:
                it.updated_at = datetime.utcnow().isoformat()
                it.version += 1
                res = {"ok": True, "item": self._to_dict(it)}
                self._persist()
                return res
            # no changes
            return {"ok": True, "item": self._to_dict(it)}

    def delete(self, item_id: int) -> Dict[str, Any]:
        with self._lock:
            idx = self._find_index(item_id)
            if idx is None:
                return {"ok": False, "error": f"item {item_id} not found"}
            removed = self._items.pop(idx)
            self._persist()
            return {"ok": True, "deleted": removed.id}

    def claim(self, item_id: int, by: Optional[str] = None) -> Dict[str, Any]:
        """标记某个 item 为被处理（单进程用作标记）。若已被其他人 claim，返回失败。"""
        with self._lock:
            idx = self._find_index(item_id)
            if idx is None:
                return {"ok": False, "error": f"item {item_id} not found"}
            it = self._items[idx]
            if it.claimed_by and it.claimed_by != by:
                return {"ok": False, "error": f"already claimed by {it.claimed_by}"}
            it.claimed_by = by
            it.claimed_at = datetime.utcnow().isoformat()
            it.status = Status.IN_PROGRESS
            it.updated_at = datetime.utcnow().isoformat()
            it.version += 1
            res = {"ok": True, "item": self._to_dict(it)}
            self._persist()
            return res

    def release(self, item_id: int, by: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            idx = self._find_index(item_id)
            if idx is None:
                return {"ok": False, "error": f"item {item_id} not found"}
            it = self._items[idx]
            # 仅允许 claim 的人 release（或无 claim 情况）
            if it.claimed_by and by and it.claimed_by != by:
                return {"ok": False, "error": f"cannot release: claimed by {it.claimed_by}"}
            it.claimed_by = None
            it.claimed_at = None
            it.updated_at = datetime.utcnow().isoformat()
            it.version += 1
            res = {"ok": True, "item": self._to_dict(it)}
            self._persist()
            return res

    def add_response(self, item_id: int, response: str, by: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            idx = self._find_index(item_id)
            if idx is None:
                return {"ok": False, "error": f"item {item_id} not found"}
            it = self._items[idx]
            resp = {"by": by, "at": datetime.utcnow().isoformat(), "content": response, "metadata": metadata or {}}
            it.responses.append(resp)
            it.updated_at = datetime.utcnow().isoformat()
            it.version += 1
            res = {"ok": True, "item": self._to_dict(it)}
            self._persist()
            return res

    def _persist(self) -> None:
        if self._backend is None:
            return
        try:
            state = {"schema_version": 1, "next_id": self._next_id, "items": [self._to_dict(it) for it in self._items]}
            self._backend.persist(state)
        except Exception:
            # best-effort, do not crash the tool on persist errors
            pass

    def _load(self) -> None:
        if self._backend is None:
            return
        data = self._backend.load()
        if not isinstance(data, dict):
            return
        next_id = data.get("next_id")
        items = data.get("items")
        if isinstance(next_id, int):
            self._next_id = next_id
        if isinstance(items, list):
            reconstructed: List[TODOItem] = []
            for d in items:
                if not isinstance(d, dict):
                    continue
                try:
                    status = Status(d.get("status")) if d.get("status") else Status.PENDING
                except Exception:
                    status = Status.PENDING
                # ensure id is valid int
                id_val = d.get("id")
                if id_val is None:
                    # skip entries without id
                    continue
                try:
                    id_int = int(id_val)
                except Exception:
                    # skip invalid entries
                    continue
                ti = TODOItem(
                    id=id_int,
                    content=d.get("content") or "",
                    status=status,
                    created_at=d.get("created_at") or datetime.utcnow().isoformat(),
                    updated_at=d.get("updated_at") or datetime.utcnow().isoformat(),
                    metadata=d.get("metadata") or {},
                    responses=d.get("responses") or [],
                    claimed_by=d.get("claimed_by"),
                    claimed_at=d.get("claimed_at"),
                    version=int(d.get("version") or 1),
                )
                reconstructed.append(ti)
            self._items = reconstructed

    def parse_input(self, input: str) -> Tuple[str, Dict[str, Any]]:
        """解析输入，优先解析 JSON 格式，否则尝试命令式解析。

        返回 (op, params_dict)
        """
        s = input.strip()
        # 尝试 JSON
        try:
            obj = json.loads(s)
            if not isinstance(obj, dict):
                raise ValueError("json must be an object")
            op = obj.get("op")
            if not op:
                raise ValueError("missing op in json")
            params: Dict[str, Any] = obj.copy()
            params.pop("op", None)
            return op.lower(), params
        except Exception:
            # 命令式解析： op arg...
            parts = s.split()
            if not parts:
                raise ValueError("empty input")
            op = parts[0].lower()
            if op == "add":
                content = s[len(parts[0]) :].strip()
                if not content:
                    raise ValueError("add requires content")
                return "add", {"content": content}
            if op in ("get", "delete"):
                if len(parts) < 2:
                    raise ValueError(f"{op} requires id")
                try:
                    item_id = int(parts[1])
                except Exception:
                    raise ValueError(f"invalid id: {parts[1]}")
                return op, {"id": item_id}
            if op == "list":
                # 支持 list [status]
                status = parts[1] if len(parts) > 1 else None
                return "list", {"status": status}
            if op == "update":
                # 支持: update <id> [status=STATUS] [content=...]
                if len(parts) < 2:
                    raise ValueError("update requires id")
                try:
                    item_id = int(parts[1])
                except Exception:
                    raise ValueError(f"invalid id: {parts[1]}")
                params: Dict[str, Any] = {"id": item_id}
                rest = " ".join(parts[2:]) if len(parts) > 2 else ""
                # 简单解析 key=value 对或追加为 content
                tokens = rest.split()
                content_parts: List[str] = []
                for token in tokens:
                    if "=" in token:
                        k, v = token.split("=", 1)
                        if k == "status":
                            params["status"] = v
                        elif k == "content":
                            params["content"] = v
                        else:
                            params[k] = v
                    else:
                        content_parts.append(token)
                if content_parts and "content" not in params:
                    params["content"] = " ".join(content_parts)
                return "update", params
            raise ValueError(f"unknown operation: {op}")

    def run(self, input: str) -> str:
        try:
            op, params = self.parse_input(input)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"parse error: {str(e)}"}, ensure_ascii=False)

        try:
            if op == "add":
                content = params.get("content")
                if not isinstance(content, str):
                    raise ValueError("add requires content string")
                metadata = params.get("metadata") if isinstance(params.get("metadata"), dict) else None
                res = self.add(content, metadata)
            elif op == "get":
                id_val = params.get("id")
                if id_val is None:
                    raise ValueError("get requires id")
                res = self.get(int(id_val))
            elif op == "list":
                status_val = params.get("status")
                if status_val is not None and not isinstance(status_val, str):
                    status_val = str(status_val)
                res = self.list(status_val)
            elif op == "update":
                id_val = params.get("id")
                if id_val is None:
                    raise ValueError("update requires id")
                content = params.get("content")
                status_val = params.get("status")
                metadata = params.get("metadata") if isinstance(params.get("metadata"), dict) else None
                res = self.update(int(id_val), content if isinstance(content, str) else None, status_val if isinstance(status_val, str) else None, metadata)
            elif op == "delete":
                id_val = params.get("id")
                if id_val is None:
                    raise ValueError("delete requires id")
                res = self.delete(int(id_val))
            elif op == "claim":
                id_val = params.get("id")
                if id_val is None:
                    raise ValueError("claim requires id")
                by = params.get("by")
                res = self.claim(int(id_val), by)
            elif op == "release":
                id_val = params.get("id")
                if id_val is None:
                    raise ValueError("release requires id")
                by = params.get("by")
                res = self.release(int(id_val), by)
            elif op == "add_response":
                id_val = params.get("id")
                if id_val is None:
                    raise ValueError("add_response requires id")
                response = params.get("response")
                if response is None:
                    raise ValueError("add_response requires response")
                by = params.get("by")
                metadata = params.get("metadata") if isinstance(params.get("metadata"), dict) else None
                res = self.add_response(int(id_val), response, by, metadata)
            else:
                res = {"ok": False, "error": f"unsupported op: {op}"}
        except Exception as e:
            res = {"ok": False, "error": f"execution error: {str(e)}"}

        return json.dumps(res, ensure_ascii=False)
    
    def format_item(self, item: Union[TODOItem, Dict[str, Any]]) -> str:
        """返回一个简短的人类可读字符串表示，用于可视化展示。"""
        if isinstance(item, TODOItem):
            d = self._to_dict(item)
        elif isinstance(item, dict):
            d = item
        else:
            return str(item)

        mid = d.get("id")
        status = d.get("status")
        content = d.get("content")
        meta = d.get("metadata")
        s = f"[{mid}] {status} - {content}"
        if meta:
            try:
                # 简短展示 metadata
                s += f" (meta: {json.dumps(meta, ensure_ascii=False)})"
            except Exception:
                s += f" (meta: {str(meta)})"
        # 显示最新回答的简短摘要（如果有）
        try:
            resps = d.get("responses")
            if isinstance(resps, list) and resps:
                last = resps[-1]
                cont = last.get("content") if isinstance(last, dict) else str(last)
                if cont:
                    snippet = cont.replace("\n", " ")
                    if len(snippet) > 80:
                        snippet = snippet[:77] + "..."
                    s += f" | latest: {snippet}"
        except Exception:
            pass
        return s

    def __str__(self) -> str:
        """返回整个工具当前内存中任务的可视化摘要，多行字符串。"""
        lines: List[str] = [f"TODOTool: {len(self._items)} items"]
        for it in self._items:
            lines.append(self.format_item(self._to_dict(it)))
        return "\n".join(lines)


    @classmethod
    def description(cls) -> str:
        return (
            "TODO 工具 — JSON 输入说明：\n"
            "请求必须为 JSON 对象，顶层字段：\n"
            "- \"op\" (必需)：取值为 \"add\" / \"get\" / \"list\" / \"update\" / \"delete\"。\n"
            "- 其余字段按操作直接放在顶层（不要嵌套在 \"params\"）。\n\n"
            "示例 JSON 格式：\n"
            "1) 新增任务 add：\n"
            "   {\"op\":\"add\",\"content\":\"买菜\",\"metadata\":{...}}\n"
            "2) 查询任务 get：\n"
            "   {\"op\":\"get\",\"id\":123}\n"
            "3) 列表 list（可选按状态过滤）：\n"
            "   {\"op\":\"list\"} 或 {\"op\":\"list\",\"status\":\"PENDING\"}\n"
            "4) 更新任务 update：\n"
            "   {\"op\":\"update\",\"id\":123,\"content\":\"新描述\",\"status\":\"COMPLETED\",\"metadata\":{...}}\n"
            "5) 删除任务 delete：\n"
            "   {\"op\":\"delete\",\"id\":123}\n\n"
            "字段说明：\n"
            "- content：字符串。\n"
            "- id：整数。\n"
            "- status：字符串，取值为 PENDING / IN_PROGRESS / COMPLETED / CANCELLED。\n"
            "- metadata：可选对象，用于放置附加信息。\n\n"
            "返回：工具将返回 JSON 字符串，例如 {\"ok\":true,\"id\":1,\"item\":{...}} 或 {\"ok\":false,\"error\":\"...\"}。\n"
            "说明：工具仍兼容简单命令式文本（例如：add 买菜）作为回退，但请优先使用上述 JSON 格式以确保解析一致性。"
        )