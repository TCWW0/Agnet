# DeepResearch Backend

本目录用于承载 deepresearch 前后端联调时的后端实现，默认不修改 `frame` 目录。

## Current Scope (v1)

- `POST /api/v1/chat`: 同步聊天响应
- `POST /api/v1/chat/stream`: SSE 流式响应
- `POST /api/v1/chat/stream/pause`: 暂停指定 streamId（best-effort）
- `GET /api/v1/health`: 服务健康检查

## Run

在项目根目录执行：

```bash
source .venv/bin/activate
pip install -r deepresearch/backend/requirements.txt
uvicorn src.main:app --app-dir deepresearch/backend --reload --port 8000
```

## Environment Variables

- `DEEPRESEARCH_CHAT_MODE`: `mock` (default) or `frame`
- `DEEPRESEARCH_CORS_ORIGINS`: 逗号分隔的前端源，默认包含 `http://localhost:5173`

当 `DEEPRESEARCH_CHAT_MODE=frame` 时，会调用 `frame.core.BaseLLM`。

## Test

```bash
source .venv/bin/activate
pytest deepresearch/backend/tests -q
```
