# 测试消息的序列化和反序列化
import json
from frame.core.message import Message
def test_message_serialization():
    msg = Message(role="assistant", action="final", content="这是一个测试消息")
    d = msg.to_dict()
    assert d["role"] == "assistant"
    assert d["action"] == "final"
    assert d["content"] == "这是一个测试消息"
    assert "timestamp" in d

def test_message_deserialization():
    d = {
        "role": "user",
        "action": "input",
        "content": "请帮我写一首诗",
        "timestamp": "2024-01-01T12:00:00"
    }
    msg = Message.from_dict(d)
    assert msg.role == "user"
    assert msg.action == "input"
    assert msg.content == "请帮我写一首诗"
    assert msg.timestamp.isoformat() == "2024-01-01T12:00:00"

def test_message_json_serialization():
    msg = Message(role="system", action="init", content="系统初始化")
    json_str = msg.to_json()
    assert isinstance(json_str, str)
    d = json.loads(json_str)
    assert d["role"] == "system"
    assert d["action"] == "init"
    assert d["content"] == "系统初始化"
    assert "timestamp" in d