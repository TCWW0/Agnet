# Agent Workspace 快速上手

创建并激活虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

运行快速验证脚本（在项目根目录执行）：

```bash
python3 - <<'PY'
import sys, os
sys.path.insert(0, os.getcwd())
from frame.test.test_message import run
run()
PY
```
