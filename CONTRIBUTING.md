# Contributing Guide

## 开发前准备
- 使用 Python `>=3.11`、Node.js LTS
- Windows 用户推荐直接执行：
  - `install.bat` 安装依赖
  - `run.bat` 启动开发环境
- 提交前运行：
  - `test.bat`

## 分支与提交规范
- 建议分支命名：
  - `feat/<topic>`
  - `fix/<topic>`
  - `refactor/<topic>`
- 提交信息建议采用 Conventional Commits：
  - `feat(api): add scene retry endpoint`
  - `fix(frontend): handle empty prompt display`

## 代码规范
- Python：4 空格缩进，`snake_case`，使用 `ruff` 检查
- TypeScript/React：2 空格缩进，组件使用 `PascalCase`
- 关键逻辑请补充简洁注释，避免冗余解释

## 测试要求
- 后端测试文件命名：`test_*.py`
- API 行为改动应至少补充一条对应测试
- 常用命令：
  - `cd backend && pytest tests -v`
  - `cd backend && ruff check app`
  - `cd frontend && npm run lint`

## Pull Request 要求
- 说明变更目的与影响范围
- 关联 Issue（如有）
- 附上本地验证结果（测试/静态检查）
- UI 改动请附截图
