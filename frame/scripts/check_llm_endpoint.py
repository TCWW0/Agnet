import json
import sys
import traceback
from pathlib import Path

# Ensure project root is on sys.path so `frame` package imports work when running this script
ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from frame.core.config import LLMConfig

def main():
    cfg = LLMConfig.from_env()
    base = cfg.base_url_.rstrip('/')
    endpoint = f"{base}/chat/completions"
    payload = {
        "model": cfg.model_id_,
        "messages": [{"role": "user", "content": "hello from healthcheck"}],
        "temperature": 0.0,
        "max_tokens": 64,
    }
    print("Endpoint:", endpoint)
    print("Payload:", json.dumps(payload, ensure_ascii=False))

    try:
        # use urllib to avoid extra dependencies
        from urllib import request, error
        data = json.dumps(payload).encode('utf-8')
        req = request.Request(endpoint, data=data, headers={"Content-Type": "application/json"}, method='POST')
        with request.urlopen(req, timeout=cfg.timeout_) as resp:
            status = getattr(resp, 'status', None)
            body = resp.read().decode('utf-8', errors='replace')
            print("Status:", status)
            print("Response body:")
            print(body)
    except Exception as e:
        print("Exception during request:")
        traceback.print_exc()
        sys.exit(2)

if __name__ == '__main__':
    main()
