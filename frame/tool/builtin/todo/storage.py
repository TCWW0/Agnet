from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from threading import RLock
from typing import List, Optional

from frame.tool.builtin.todo.models import TodoItem


class TodoStorage(ABC):
    @abstractmethod
    def load_items(self) -> List[TodoItem]:
        raise NotImplementedError

    @abstractmethod
    def save_items(self, items: List[TodoItem]) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def path(self) -> Path:
        raise NotImplementedError


class JsonTodoStorage(TodoStorage):
    def __init__(self, filename: Optional[str] = None, base_dir: Optional[str] = None) -> None:
        self._lock = RLock()
        self._path = self._resolve_path(filename=filename, base_dir=base_dir)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def load_items(self) -> List[TodoItem]:
        with self._lock:
            if not self._path.exists():
                return []

            with self._path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)

            if isinstance(raw, dict):
                raw_items = raw.get("items", [])
            else:
                raw_items = raw

            if not isinstance(raw_items, list):
                raise ValueError("Invalid todo json format: items must be a list")

            return [TodoItem.model_validate(item) for item in raw_items]

    def save_items(self, items: List[TodoItem]) -> None:
        with self._lock:
            payload = [item.model_dump(mode="json") for item in items]
            tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
            with tmp_path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)

    @staticmethod
    def _resolve_path(filename: Optional[str], base_dir: Optional[str]) -> Path:
        env_base = os.getenv("TODO_JSON_PATH", "bin/todo")
        base = Path(base_dir or env_base)

        final_name = filename.strip() if isinstance(filename, str) else ""
        if not final_name:
            final_name = "todo.json"
        # External input is treated as a file name, not a full path.
        final_name = Path(final_name).name
        if Path(final_name).suffix == "":
            final_name = f"{final_name}.json"

        return base / final_name
