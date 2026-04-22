from __future__ import annotations

import json

from frame.tool.builtin.todo.cli import main as todo_cli_main
from frame.tool.builtin.todo.manager import TodoManager
from frame.tool.builtin.todo.models import TodoStatus
from frame.tool.builtin.todo.storage import JsonTodoStorage
from frame.tool.builtin.todo.tool import TodoTool


def test_json_storage_uses_env_base_and_filename(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TODO_JSON_PATH", str(tmp_path))
    storage = JsonTodoStorage(filename="work")
    assert storage.path == tmp_path / "work.json"


def test_json_storage_filename_is_sanitized(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TODO_JSON_PATH", str(tmp_path))
    storage = JsonTodoStorage(filename="../outside")
    assert storage.path == tmp_path / "outside.json"


def test_manager_crud_and_persistence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TODO_JSON_PATH", str(tmp_path))
    storage = JsonTodoStorage(filename="cases")
    manager = TodoManager(storage=storage)

    created = manager.create_item("draft design")
    assert created.status == TodoStatus.NOT_STARTED

    got = manager.get_item(created.item_id)
    assert got is not None
    assert got.text == "draft design"

    updated = manager.update_item(created.item_id, status=TodoStatus.COMPLETED)
    assert updated.status == TodoStatus.COMPLETED

    manager2 = TodoManager(storage=JsonTodoStorage(filename="cases"))
    loaded = manager2.get_item(created.item_id)
    assert loaded is not None
    assert loaded.status == TodoStatus.COMPLETED

    deleted = manager2.delete_item(created.item_id)
    assert deleted is True
    assert manager2.get_item(created.item_id) is None


def test_todo_tool_crud_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TODO_JSON_PATH", str(tmp_path))
    tool = TodoTool(filename="toolstore")

    created = tool.execute({"action": "create", "text": "review todo mvp"})
    assert created.status == "success"
    payload = json.loads(created.output)
    item_id = payload["item"]["item_id"]

    listed = tool.execute({"action": "list"})
    listed_payload = json.loads(listed.output)
    assert listed_payload["count"] == 1

    updated = tool.execute({"action": "update", "item_id": item_id, "status": "in-progress"})
    updated_payload = json.loads(updated.output)
    assert updated_payload["item"]["status"] == "in-progress"

    fetched = tool.execute({"action": "get", "item_id": item_id})
    fetched_payload = json.loads(fetched.output)
    assert fetched_payload["found"] is True

    removed = tool.execute({"action": "delete", "item_id": item_id})
    removed_payload = json.loads(removed.output)
    assert removed_payload["deleted"] is True


def test_todo_cli_add_and_list(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("TODO_JSON_PATH", str(tmp_path))

    add_rc = todo_cli_main(["add", "write tests", "--file", "cli"])
    assert add_rc == 0
    add_out = capsys.readouterr().out.strip()
    add_payload = json.loads(add_out)
    assert add_payload["ok"] is True

    list_rc = todo_cli_main(["list", "--file", "cli"])
    assert list_rc == 0
    list_out = capsys.readouterr().out.strip()
    list_payload = json.loads(list_out)
    assert list_payload["count"] == 1
    assert list_payload["items"][0]["text"] == "write tests"
