from __future__ import annotations

import argparse
import json
from typing import Optional, Sequence

from frame.tool.builtin.todo.manager import TodoManager
from frame.tool.builtin.todo.models import TodoStatus
from frame.tool.builtin.todo.storage import JsonTodoStorage


class TodoCLI:
    def __init__(self) -> None:
        self.parser = self._build_parser()

    def run(self, argv: Optional[Sequence[str]] = None) -> int:
        args = self.parser.parse_args(list(argv) if argv is not None else None)

        storage = JsonTodoStorage(filename=args.file)
        manager = TodoManager(storage=storage)

        if args.command == "add":
            status = TodoStatus(args.status) if args.status else TodoStatus.NOT_STARTED
            item = manager.create_item(text=args.text, status=status)
            self._print({"ok": True, "item": item.model_dump(mode="json"), "storage_path": manager.storage_path})
            return 0

        if args.command == "list":
            status = TodoStatus(args.status) if args.status else None
            items = manager.list_items(status=status)
            self._print(
                {
                    "ok": True,
                    "count": len(items),
                    "items": [item.model_dump(mode="json") for item in items],
                    "storage_path": manager.storage_path,
                }
            )
            return 0

        if args.command == "get":
            item = manager.get_item(args.item_id)
            self._print(
                {
                    "ok": True,
                    "found": item is not None,
                    "item": None if item is None else item.model_dump(mode="json"),
                    "storage_path": manager.storage_path,
                }
            )
            return 0

        if args.command == "update":
            status = TodoStatus(args.status) if args.status else None
            try:
                item = manager.update_item(item_id=args.item_id, text=args.text, status=status)
            except (KeyError, ValueError) as exc:
                self._print({"ok": False, "error": str(exc), "storage_path": manager.storage_path})
                return 1
            self._print({"ok": True, "item": item.model_dump(mode="json"), "storage_path": manager.storage_path})
            return 0

        if args.command == "delete":
            deleted = manager.delete_item(args.item_id)
            self._print({"ok": True, "deleted": deleted, "storage_path": manager.storage_path})
            return 0

        self._print({"ok": False, "error": "unknown command"})
        return 1

    @staticmethod
    def _print(payload: dict) -> None:
        print(json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _build_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description="TODO CLI")
        sub = parser.add_subparsers(dest="command", required=True)

        add = sub.add_parser("add", help="create a todo item")
        add.add_argument("text", type=str)
        add.add_argument("--status", choices=["not-started", "in-progress", "completed"], default="not-started")
        add.add_argument("--file", type=str, default=None, help="todo filename, joined with TODO_JSON_PATH")

        list_cmd = sub.add_parser("list", help="list items")
        list_cmd.add_argument("--status", choices=["not-started", "in-progress", "completed"], default=None)
        list_cmd.add_argument("--file", type=str, default=None)

        get_cmd = sub.add_parser("get", help="get one item")
        get_cmd.add_argument("item_id", type=str)
        get_cmd.add_argument("--file", type=str, default=None)

        update = sub.add_parser("update", help="update one item")
        update.add_argument("item_id", type=str)
        update.add_argument("--text", type=str, default=None)
        update.add_argument("--status", choices=["not-started", "in-progress", "completed"], default=None)
        update.add_argument("--file", type=str, default=None)

        delete = sub.add_parser("delete", help="delete one item")
        delete.add_argument("item_id", type=str)
        delete.add_argument("--file", type=str, default=None)

        return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    cli = TodoCLI()
    return cli.run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
