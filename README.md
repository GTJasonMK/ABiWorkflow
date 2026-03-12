# AbiWorkflow

AbiWorkflow 是一个“剧本 -> 场景提示词 -> 分镜视频 -> 成片合成”的自动化工作流项目。  
仓库包含：
- `backend/`：FastAPI + SQLAlchemy + Celery + Redis 的后端服务
- `frontend/`：React + TypeScript + Ant Design 的前端界面

## 功能概览
- 剧本解析：将剧本拆解为角色与场景，并生成场景级视频提示词
- 视频生成：按场景逐段调用视频提供者，支持失败重试
- 成片合成：拼接场景、转场控制、可选字幕与 TTS 配音
- 任务中心：统一查看解析/生成/合成任务状态与历史

## 目录结构
```text
backend/
  app/            # API、服务、模型、任务
  tests/          # 后端测试
frontend/
  src/            # 页面、组件、状态管理、API 封装
install.bat       # 一键安装依赖（Windows）
run.bat           # 一键启动前后端（Windows）
test.bat          # 一键测试与静态检查（Windows）
install.sh        # 一键安装依赖（Linux/WSL）
run.sh            # 一键启动前后端（Linux/WSL）
test.sh           # 一键测试与静态检查（Linux/WSL）
```

## 快速开始（Windows）
> 注意：`install.bat` / `run.bat` / `test.bat` 仅用于 **Windows PowerShell / cmd**。  
> 不要在 WSL/bash 里直接执行（可能产生 `nul` 文件、并导致依赖按 Linux/Windows 混装）。
>
> Windows 脚本会固定使用 `backend\.venv-win` 作为后端虚拟环境，
> 不再复用 `backend\.venv`，以避免和 WSL/Linux 环境互相覆盖。

1. 安装依赖：
```bat
install.bat
```

2. 配置环境变量（根目录 `.env`）：
```env
LLM_PROVIDER=openai
LLM_API_KEY=your-key
LLM_MODEL=gpt-4o
LLM_BASE_URL=
VIDEO_PROVIDER=mock
```

也可使用 DeepSeek（OpenAI 兼容接口）：
```env
LLM_PROVIDER=openai
LLM_API_KEY=your-key
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com/v1
```

也可接入 `GGK-rs` 提供的 OpenAI 兼容 API：
```env
# 剧本分析（LLM）
LLM_PROVIDER=openai
LLM_API_KEY=your-ggk-api-key
LLM_MODEL=grok-4.1-fast
LLM_BASE_URL=http://127.0.0.1:7321/v1

# 视频生成（GGK 视频提供者）
VIDEO_PROVIDER=ggk
GGK_BASE_URL=http://127.0.0.1:7321/v1
GGK_API_KEY=your-ggk-api-key
GGK_VIDEO_MODEL=grok-imagine-1.0-video
GGK_VIDEO_ASPECT_RATIO=16:9
GGK_VIDEO_RESOLUTION=SD
GGK_VIDEO_PRESET=normal
# 可选：按模型定义时长策略与提示词模板（JSON 字符串）
GGK_VIDEO_MODEL_DURATION_PROFILES={"grok-imagine-1.0-video":{"min_seconds":5,"max_seconds":15,"allowed_seconds":[5,6,8,10,15],"prompt_hint_template":"请将该镜头时长控制在约 {seconds} 秒，保证动作节奏完整。"}}

# 可选：角色立绘也走 GGK-rs 的 /v1/images/generations
PORTRAIT_API_BASE_URL=http://127.0.0.1:7321/v1
PORTRAIT_API_KEY=your-ggk-api-key
PORTRAIT_IMAGE_MODEL=grok-imagine-1.0
```

3. 启动项目：
```bat
run.bat
```
说明：默认启动 Electron 桌面 GUI。
若未安装 Electron 依赖，请先在 `frontend/` 下执行 `npm install`。

如果要启动浏览器网页模式：
```bat
run.bat web
```

桌面 GUI 模式（Electron）：
```bat
run.bat desktop
```

默认地址：
- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`

`run.bat` 默认不启动 Celery Worker（`ENABLE_CELERY_WORKER=0`）。
如果需要异步解析/生成/合成任务，请显式设置 `ENABLE_CELERY_WORKER=1` 并确保 Redis 可用。

## 快速开始（Linux / WSL）
> 注意：`install.sh` / `run.sh` / `test.sh` 仅用于 **Linux / WSL bash**。
>
> Linux/WSL 脚本会固定使用 `backend/.venv-linux` 作为后端虚拟环境，
> 不再复用 `backend/.venv`，以避免和 Windows 环境互相覆盖。

1. 安装依赖：
```bash
./install.sh
```

2. 启动项目：
```bash
./run.sh
```

说明：`run.sh` 默认启动网页模式。

如果要显式启动网页模式：
```bash
./run.sh web
```

如果当前 Linux 环境支持 Electron，也可以启动桌面模式：
```bash
./run.sh desktop
```

运行测试：
```bash
./test.sh
```

## 本地开发命令
- 后端测试：`cd backend && pytest tests -v`
- 后端检查：`cd backend && ruff check app`
- 前端检查：`cd frontend && npm run lint`
- 前端构建：`cd frontend && npm run build`
- 任务状态查询：`GET /api/tasks/{task_id}`

## Electron 桌面 GUI（可选）
前端已支持 Electron 封装为桌面 GUI，后端仍然作为本地 API 服务运行。

1. 先启动后端（推荐根目录 `run.bat`，或单独启动 backend）
2. 开发模式启动 Electron：
```bat
cd frontend
npm run desktop:dev
```
3. 本地构建后运行桌面版：
```bat
cd frontend
npm run desktop:start
```
4. 打包 Windows 安装包（NSIS）：
```bat
cd frontend
npm run desktop:dist
```

## 跨系统开发说明
- Windows 的 `install.bat` / `run.bat` / `test.bat` 固定使用 `backend\.venv-win`
- 如果你在 WSL/Linux 下开发，请使用单独的 Linux 环境目录，例如 `backend/.venv-linux`
- 推荐在 WSL/Linux 下执行：
```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-linux uv sync --extra dev
```
- 这样 Windows 和 WSL/Linux 各自使用独立虚拟环境，不会再互相破坏

默认 Electron 会连接：
- API：`http://127.0.0.1:8000/api`
- WebSocket：`ws://127.0.0.1:8000/ws`

可通过环境变量覆盖：
- `ELECTRON_API_BASE_URL`
- `ELECTRON_WS_BASE_URL`
- `ELECTRON_WINDOW_WIDTH`（默认 1180）
- `ELECTRON_WINDOW_HEIGHT`（默认 760）

## 异步任务接口
- 解析剧本：`POST /api/projects/{project_id}/parse?async_mode=true`
- 视频生成：`POST /api/projects/{project_id}/generate?async_mode=true`
- 视频合成：`POST /api/projects/{project_id}/compose?async_mode=true`

当 Celery Worker 可用时，上述接口返回：
```json
{"task_id":"xxx","mode":"async","status":"queued"}
```

启用异步模式前，请先确保 Celery Worker 可用。

## 生产接入说明
- 默认 `VIDEO_PROVIDER=mock` 为演示模式
- 使用真实文生视频服务时，设置 `VIDEO_PROVIDER=http` 并配置：
  - `VIDEO_HTTP_BASE_URL`
  - `VIDEO_HTTP_API_KEY`
  - 其他 `VIDEO_HTTP_*` 字段
- 使用 GGK 视频生成时，设置 `VIDEO_PROVIDER=ggk` 并配置 `GGK_*` 字段

### GGK 模型时长策略（可选）
- 配置项：`GGK_VIDEO_MODEL_DURATION_PROFILES`
- 格式：JSON 对象，key 为模型名，value 为该模型时长策略
- 支持字段：
  - `min_seconds`：最小时长
  - `max_seconds`：最大时长
  - `allowed_seconds`：可选时长列表（会按最接近请求时长的值进行匹配）
  - `prompt_hint_template`：注入到提示词的时长模板，支持 `{seconds}` 占位符

示例：
```json
{
  "grok-imagine-1.0-video": {
    "min_seconds": 5,
    "max_seconds": 15,
    "allowed_seconds": [5, 6, 8, 10, 15],
    "prompt_hint_template": "请将该镜头时长控制在约 {seconds} 秒，保证动作节奏完整。"
  }
}
```

## 提交前建议
- 不要提交 `.env`、数据库文件、`node_modules/`、`backend/outputs/`
- 提交前至少执行一次后端 + 前端静态检查
- 参考 `CONTRIBUTING.md` 的提交与 PR 规范
