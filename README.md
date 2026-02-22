# AbiWorkflow

AbiWorkflow 是一个“剧本 -> 场景提示词 -> 分镜视频 -> 成片合成”的自动化工作流项目。  
仓库包含：
- `backend/`：FastAPI + SQLAlchemy + Celery + Redis 的后端服务
- `frontend/`：React + TypeScript + Ant Design 的前端界面

## 功能概览
- 剧本解析：将剧本拆解为角色与场景，并生成场景级视频提示词
- 视频生成：按场景逐段调用视频提供者，支持失败重试
- 成片合成：拼接场景、转场控制、可选字幕与 TTS 配音

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

3. 启动项目：
```bat
run.bat
```

默认地址：
- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`

## 本地开发命令
- 后端测试：`cd backend && pytest tests -v`
- 后端检查：`cd backend && ruff check app`
- 前端检查：`cd frontend && npm run lint`
- 前端构建：`cd frontend && npm run build`

## 生产接入说明
- 默认 `VIDEO_PROVIDER=mock` 为演示模式
- 使用真实文生视频服务时，设置 `VIDEO_PROVIDER=http` 并配置：
  - `VIDEO_HTTP_BASE_URL`
  - `VIDEO_HTTP_API_KEY`
  - 其他 `VIDEO_HTTP_*` 字段

## 提交前建议
- 不要提交 `.env`、数据库文件、`node_modules/`、`backend/outputs/`
- 提交前至少执行一次后端 + 前端静态检查
- 参考 `CONTRIBUTING.md` 的提交与 PR 规范
