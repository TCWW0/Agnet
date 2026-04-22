from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Dict, List, Optional

from frame.tool.builtin.todo.models import TodoItem, TodoStatus
from frame.tool.builtin.todo.storage import TodoStorage


class TodoManager:
    def __init__(self, storage: TodoStorage, autosave: bool = True) -> None:
        self._storage = storage
        self._autosave = autosave
        self._lock = RLock()
        self._items: Dict[str, TodoItem] = {}
        self._load_from_storage()

    @property
    def storage_path(self) -> str:
        return str(self._storage.path)

    def create_item(self, text: str, status: TodoStatus = TodoStatus.NOT_STARTED) -> TodoItem:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("text must not be empty")

        with self._lock:
            item = TodoItem(text=clean_text, status=status)
            self._items[item.item_id] = item
            self._persist_if_needed()
            return item

    def list_items(self, status: Optional[TodoStatus] = None) -> List[TodoItem]:
        with self._lock:
            items = list(self._items.values())
            if status is not None:
                items = [item for item in items if item.status == status]
            items.sort(key=lambda item: (item.created_at, item.item_id))
            return [item.model_copy(deep=True) for item in items]

    def get_item(self, item_id: str) -> Optional[TodoItem]:
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                return None
            return item.model_copy(deep=True)

    def update_item(
        self,
        item_id: str,
        text: Optional[str] = None,
        status: Optional[TodoStatus] = None,
    ) -> TodoItem:
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                raise KeyError(f"item '{item_id}' not found")

            changed = False

            if text is not None:
                clean_text = text.strip()
                if not clean_text:
                    raise ValueError("text must not be empty")
                if clean_text != item.text:
                    item.text = clean_text
                    changed = True

            if status is not None and status != item.status:
                item.status = status
                changed = True

            if changed:
                item.updated_at = datetime.now(timezone.utc)
                self._persist_if_needed()

            return item.model_copy(deep=True)

    def delete_item(self, item_id: str) -> bool:
        with self._lock:
            existed = item_id in self._items
            if not existed:
                return False
            self._items.pop(item_id, None)
            self._persist_if_needed()
            return True

    def flush(self) -> None:
        with self._lock:
            self._storage.save_items(list(self._items.values()))

    def _load_from_storage(self) -> None:
        with self._lock:
            loaded = self._storage.load_items()
            self._items = {item.item_id: item for item in loaded}

    def _persist_if_needed(self) -> None:
        if self._autosave:
            self._storage.save_items(list(self._items.values()))
