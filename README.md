# InsightTrace

InsightTrace 是一个面向经营分析场景的多轮归因分析系统。当前仓库处于 MVP v1 基础骨架阶段。

## 当前能力

- React + TypeScript 前端骨架；
- FastAPI 后端骨架；
- PostgreSQL 与 Alembic 迁移基础；
- Docker Compose 本地运行环境；
- 存活与就绪健康检查；
- 前后端基础测试入口；
- 受控的上传、导出和临时工作目录。

业务会话、附件、分析任务和归因能力将在后续里程碑中实现。

## 快速启动

1. 复制环境变量模板：

   ```powershell
   Copy-Item .env.example .env
   ```

2. 启动服务：

   ```powershell
   docker compose up --build
   ```

3. 访问：

   - Web：<http://localhost:3000>
   - API 文档：<http://localhost:8000/docs>
   - 后端存活检查：<http://localhost:8000/health/live>
   - 后端就绪检查：<http://localhost:8000/health/ready>

## 本地开发

后端要求 Python 3.12：

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload
```

前端要求 Node.js 22：

```powershell
cd frontend
npm install
npm run dev
```

## 文档

- [项目规划](./PROJECT_PLAN.md)
- [技术设计](./TECHNICAL_DESIGN.md)

## 目录

```text
frontend/      React 前端
backend/       FastAPI 后端
database/      数据库初始化内容
demo-data/     演示业务数据
docs/          接口、演示和截图文档
storage/       运行时文件，不提交实际内容
tests/e2e/     端到端测试
```
