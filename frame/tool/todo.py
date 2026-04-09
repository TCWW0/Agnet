"""简化版 TODO 工具（单线程、内存存储）。

功能：支持 `add` / `get` / `list` / `update` / `delete` 操作。
输入优先解析为 JSON，例如：
  {"op":"add","content":"买菜"}
或命令式文本：
  add 买菜
  update 3 status=COMPLETED
返回值为 `ToolResult` 对象，便于边界层序列化。
"""
from .base import Tool, ToolParameter, validate_tool_message
from frame.core.message import ToolMessage, ToolResult
from .persistence import PersistenceBackend, JsonFileBackend
import threading
import os
from enum import Enum
from typing import List, Optional, Dict, Any, Union
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
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
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
                it.updated_at = datetime.now().isoformat()
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
            it.claimed_at = datetime.now().isoformat()
            it.status = Status.IN_PROGRESS
            it.updated_at = datetime.now().isoformat()
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
            it.updated_at = datetime.now().isoformat()
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
            resp = {"by": by, "at": datetime.now().isoformat(), "content": response, "metadata": metadata or {}}
            it.responses.append(resp)
            it.updated_at = datetime.now().isoformat()
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
                    created_at=d.get("created_at") or datetime.now().isoformat(),
                    updated_at=d.get("updated_at") or datetime.now().isoformat(),
                    metadata=d.get("metadata") or {},
                    responses=d.get("responses") or [],
                    claimed_by=d.get("claimed_by"),
                    claimed_at=d.get("claimed_at"),
                    version=int(d.get("version") or 1),
                )
                reconstructed.append(ti)
            self._items = reconstructed
            
    def _run_op(self, op: Optional[str], params: Dict[str, Any]) -> Dict[str, Any]:
        """基于归一化的 op/params 执行具体操作，返回与旧 run() 相同风格的结果 dict。"""
        try:
            if op == 'add':
                content = params.get('content') or params.get('raw_str') or params.get('input')
                if not isinstance(content, str):
                    raise ValueError('add requires content string')
                metadata = params.get('metadata') if isinstance(params.get('metadata'), dict) else None
                return self.add(content, metadata)

            if op == 'get':
                id_val = params.get('id')
                if id_val is None:
                    raise ValueError('get requires id')
                return self.get(int(id_val))

            if op == 'list':
                status_val = params.get('status')
                if status_val is not None and not isinstance(status_val, str):
                    status_val = str(status_val)
                return self.list(status_val)

            if op == 'update':
                id_val = params.get('id')
                if id_val is None:
                    raise ValueError('update requires id')
                content = params.get('content')
                status_val = params.get('status')
                metadata = params.get('metadata') if isinstance(params.get('metadata'), dict) else None
                return self.update(int(id_val), content if isinstance(content, str) else None, status_val if isinstance(status_val, str) else None, metadata)

            if op == 'delete':
                id_val = params.get('id')
                if id_val is None:
                    raise ValueError('delete requires id')
                return self.delete(int(id_val))

            if op == 'claim':
                id_val = params.get('id')
                if id_val is None:
                    raise ValueError('claim requires id')
                by = params.get('by')
                return self.claim(int(id_val), by)

            if op == 'release':
                id_val = params.get('id')
                if id_val is None:
                    raise ValueError('release requires id')
                by = params.get('by')
                return self.release(int(id_val), by)

            if op == 'add_response':
                id_val = params.get('id')
                if id_val is None:
                    raise ValueError('add_response requires id')
                response = params.get('response')
                if response is None:
                    raise ValueError('add_response requires response')
                by = params.get('by')
                metadata = params.get('metadata') if isinstance(params.get('metadata'), dict) else None
                return self.add_response(int(id_val), response, by, metadata)

            return {"ok": False, "error": f"unsupported op: {op}"}
        except Exception as e:
            return {"ok": False, "error": f"execution error: {str(e)}"}

    

    def run(self, tool_message: ToolMessage) -> ToolResult:
        """只接受 `ToolMessage` 对象，并返回 `ToolResult`。

        要求示例：
        {"type":"tool","tool_name":"TODO","tool_input":{"op":"add","content":"买菜"},"phase":"call"}
        """
        start = datetime.now()

        # 严格校验为 ToolMessage 对象
        try:
            tm = validate_tool_message(tool_message)
        except Exception as e:
            err = f"invalid input: {str(e)}"
            return ToolResult(
                tool_name="TODO",
                status="error",
                output=None,
                original_input=tool_message,
                nl=err,
                error_message=err,
                timestamp=datetime.now().isoformat(),
                duration_ms=0,
            )

        # 支持两种输入：
        # 1) 单操作：{"op":"add",...}
        # 2) 批量操作：{"ops":[{"op":"add",...},{...}]} 或直接传入 [{"op":...}, ...]
        tool_input = tm.tool_input
        ops: List[Dict[str, Any]] = []

        if isinstance(tool_input, dict) and "op" in tool_input:
            ops = [tool_input]
        elif isinstance(tool_input, dict) and isinstance(tool_input.get("ops"), list):
            raw_ops = tool_input.get("ops") or []
            ops = [op for op in raw_ops if isinstance(op, dict)]
        elif isinstance(tool_input, list):
            ops = [op for op in tool_input if isinstance(op, dict)]

        if not ops:
            err = (
                "invalid tool_input: expected {'op':...} or {'ops':[{'op':...}, ...]} "
                "or a list of operation objects."
            )
            return ToolResult(
                tool_name="TODO",
                status="error",
                output=None,
                original_input=tm,
                nl=err,
                error_message=err,
                timestamp=datetime.now().isoformat(),
                duration_ms=0,
            )

        # 单操作：保持原有返回语义，兼容现有调用方
        if len(ops) == 1:
            op_obj = ops[0]
            op = str(op_obj.get("op", "")).lower()
            params = {k: v for k, v in op_obj.items() if k != "op"}
            res = self._run_op(op, params)
        else:
            # 批量操作：顺序执行，每步都返回结构化结果
            batch_results: List[Dict[str, Any]] = []
            ok_count = 0
            for idx, op_obj in enumerate(ops):
                op = str(op_obj.get("op", "")).lower()
                params = {k: v for k, v in op_obj.items() if k != "op"}
                one = self._run_op(op, params)
                one_ok = isinstance(one, dict) and bool(one.get("ok"))
                if one_ok:
                    ok_count += 1
                batch_results.append(
                    {
                        "index": idx,
                        "op": op,
                        "ok": one_ok,
                        "result": one,
                    }
                )

            res = {
                "ok": ok_count == len(ops),
                "batch": True,
                "total": len(ops),
                "ok_count": ok_count,
                "error_count": len(ops) - ok_count,
                "results": batch_results,
            }

        end = datetime.now()
        duration_ms = int((end - start).total_seconds() * 1000)
        status = "ok" if isinstance(res, dict) and res.get("ok") else "error"
        output = None
        if isinstance(res, dict):
            if 'item' in res:
                output = res.get('item')
            elif 'items' in res:
                output = res.get('items')
            elif 'batch' in res:
                output = {
                    "batch": True,
                    "total": res.get("total", 0),
                    "ok_count": res.get("ok_count", 0),
                    "error_count": res.get("error_count", 0),
                    "results": res.get("results", []),
                }
            else:
                output = res
        else:
            output = res

        if isinstance(res, dict) and res.get('ok'):
            if 'id' in res:
                nl = f"ok id={res.get('id')}"
            elif res.get("batch"):
                nl = f"batch ok {res.get('ok_count', 0)}/{res.get('total', 0)}"
            elif isinstance(output, list):
                nl = f"返回 {len(output)} 条"
            else:
                nl = "ok"
        else:
            if isinstance(res, dict) and res.get("batch"):
                nl = f"batch partial {res.get('ok_count', 0)}/{res.get('total', 0)}"
            else:
                nl = res.get('error') if isinstance(res, dict) else str(res)

        tool_result = {
            "version": "1.0",
            "tool_name": "TODO",
            "status": status,
            "output": output,
            "original_input": tm.tool_input,
            "nl": nl,
            "error_message": None if status == 'ok' else (res.get('error') if isinstance(res, dict) else str(res)),
            "timestamp": end.isoformat(),
            "duration_ms": duration_ms,
        }

        return ToolResult.from_dict(tool_result)
    
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
        # 支持单操作与批量操作
        return (
            "TODO 工具 — 简要说明：\n"
            "输入为 ToolMessage 风格 JSON（type=\"tool\"）。支持两种 tool_input：\n"
            "1) 单操作：{\"op\":\"add\",\"content\":\"买菜\"}\n"
            "2) 批量：{\"ops\":[{\"op\":\"add\",\"content\":\"A\"},{\"op\":\"add\",\"content\":\"B\"}]}\n"
            "批量返回 output.batch=true，并包含 total/ok_count/error_count/results。"
        )