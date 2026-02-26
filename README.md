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
```

## 快速开始（Windows）
1. 安装依赖：
```bat
install.bat
```

2. 配置环境变量（根目录 `.env`）：
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your-key
VIDEO_PROVIDER=mock
```

也可使用 DeepSeek（OpenAI 兼容接口）：
```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

也可接入 GGK 的剧本分析与视频生成：
```env
# 剧本分析（LLM）
LLM_PROVIDER=ggk
GGK_BASE_URL=http://127.0.0.1:8000/v1
GGK_API_KEY=your-ggk-api-key
GGK_TEXT_MODEL=grok-3

# 视频生成
VIDEO_PROVIDER=ggk
GGK_VIDEO_MODEL=grok-imagine-1.0-video
GGK_VIDEO_ASPECT_RATIO=16:9
GGK_VIDEO_RESOLUTION=SD
GGK_VIDEO_PRESET=normal
# 可选：按模型定义时长策略与提示词模板（JSON 字符串）
GGK_VIDEO_MODEL_DURATION_PROFILES={"grok-imagine-1.0-video":{"min_seconds":5,"max_seconds":15,"allowed_seconds":[5,6,8,10,15],"prompt_hint_template":"请将该镜头时长控制在约 {seconds} 秒，保证动作节奏完整。"}}

# 可选：如果 GGK 不在同级目录，可显式指定项目路径（用于自动读取 GGK 的 data/data.db）
GGK_PROJECT_PATH=E:/Code/GGK
```

3. 启动项目：
```bat
run.bat
```
说明：默认启动 Electron 桌面 GUI。
若未安装 Electron 依赖，会自动回退到网页模式并给出安装提示。

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

`run.bat` 默认会额外启动一个 Celery Worker（`ENABLE_CELERY_WORKER=1`），用于异步解析/生成/合成任务。

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

当 Worker 不可用时，接口会自动降级为同步执行并直接返回业务结果。

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

### GGK 自动导入（开箱即用）
- 目标：只运行 `GGK + AbiWorkflow` 两个项目即可直接联通。
- 机制：AbiWorkflow 会在读取运行配置时自动尝试发现同级 `GGK` 项目，读取其 `data/data.db` 中可用 API Key，并自动写入本项目 `.env`。
- 自动导入会优先补齐：
  - `GGK_BASE_URL`
  - `GGK_API_KEY`（优先读取 `api_keys` 表中的启用 Key）
  - `LLM_PROVIDER=ggk`（仅当当前是 `openai` 且未配置 OpenAI key）
  - `VIDEO_PROVIDER=ggk`（仅当当前是 `mock`）
- 如果你不希望自动导入，可在环境变量设置：
```env
ABI_DISABLE_GGK_AUTO_IMPORT=true
```
- 也可以在“系统设置”页面点击“从 GGK 自动导入”按钮手动执行一次。

## 提交前建议
- 不要提交 `.env`、数据库文件、`node_modules/`、`backend/outputs/`
- 提交前至少执行一次后端 + 前端静态检查
- 参考 `CONTRIBUTING.md` 的提交与 PR 规范
