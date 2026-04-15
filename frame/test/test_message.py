import json

from frame.core.message import SystemMessage, UserMessage, FunctionMessage


def run():
    m1 = SystemMessage('sys')
    assert m1.to_openai_dict() == {'role': 'system', 'content': 'sys'}

    m2 = UserMessage({'foo': 'bar'})
    d2 = m2.to_openai_dict()
    assert d2['role'] == 'user'
    assert json.loads(d2['content']) == {'foo': 'bar'}

    m3 = FunctionMessage(name='f', content={'ok': True})
    d3 = m3.to_openai_dict()
    assert d3['role'] == 'function'
    assert d3['name'] == 'f'
    assert json.loads(d3['content']) == {'ok': True}

    print('OK')


if __name__ == '__main__':
    run()
