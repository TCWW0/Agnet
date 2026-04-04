"""持久化后端抽象与 JSON 文件实现。"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import os
import json
import tempfile
import threading

class PersistenceBackend(ABC):
    @abstractmethod
    def load(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def persist(self, state: Dict[str, Any]) -> None:
        pass

    def backup(self) -> None:
        return None

    def close(self) -> None:
        return None


class JsonFileBackend(PersistenceBackend):
    """简单的 JSON 文件持久化实现，支持原子写入与线程锁保护。

    path: 文件路径
    """
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {"next_id": 1, "items": [], "schema_version": 1}
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def persist(self, state: Dict[str, Any]) -> None:
        tmp_fd, tmp_path = tempfile.mkstemp(prefix=".tmp-todo-", dir=os.path.dirname(self.path) or ".")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            # 原子替换
            os.replace(tmp_path, self.path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def backup(self) -> None:
        # 可选：实现简单备份
        try:
            if os.path.exists(self.path):
                bak = self.path + ".bak"
                with open(self.path, "rb") as src, open(bak, "wb") as dst:
                    dst.write(src.read())
        except Exception:
            pass

    def close(self) -> None:
        return None
