from pathlib import Path
from datetime import datetime
import argparse
import sys


def load_env(path: Path) -> dict:
    config = {}
    if not path.exists():
        return config
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            config[k] = v
    return config


class SimpleTerminalAgent:
    def __init__(self, config: dict):
        self.config = config
        self.name = config.get('BOT_NAME') or config.get('LLM_MODEL_ID') or 'SimpleAgent'
        self.greeting = config.get('GREETING') or f"你好，我是 {self.name}。输入 quit 或 exit 结束对话。"

    def process(self, text: str) -> str:
        t = text.strip()
        if not t:
            return f"{self.name}: 请说点什么~"
        lower = t.lower()
        if lower in ('hi', 'hello', '你好'):
            return f"{self.name}: {self.greeting}"
        if lower in ('time', 'date', '现在几点'):
            return f"{self.name}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return f"{self.name}: 我收到了：{text}"


def main():
    env_path = Path(__file__).parent / '.env'
    config = load_env(env_path)
    agent = SimpleTerminalAgent(config)

    parser = argparse.ArgumentParser(description='Simple terminal agent')
    parser.add_argument('--once', '-c', help='处理单条输入并退出（便于测试）')
    args = parser.parse_args()

    if args.once:
        resp = agent.process(args.once)
        print(resp)
        return

    print(agent.greeting)
    try:
        while True:
            try:
                user_input = input('> ')
            except EOFError:
                print('\n退出')
                break
            if user_input.strip().lower() in ('quit', 'exit'):
                print('再见。')
                break
            resp = agent.process(user_input)
            print(resp)
    except KeyboardInterrupt:
        print('\n已中断，退出。')


if __name__ == '__main__':
    main()
