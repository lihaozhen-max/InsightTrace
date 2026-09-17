# InsightTrace

InsightTrace 是一个面向经营分析场景的多轮归因分析系统。当前仓库处于 MVP v1 基础骨架阶段。

## 当前能力

- React + TypeScript 前端骨架；
- FastAPI 后端骨架；
- PostgreSQL 与 Alembic 迁移基础；
- 十张核心业务表及数据库约束；
- 内置模拟 OAuth 登录、签名 Cookie 会话与分析用户/管理员角色识别；
- 统一的认证错误响应；
- 登录用户创建会话并查看自己的会话列表；
- 在自己的会话中保存用户消息并回放历史消息；
- 会话重命名、归档、恢复和级联删除；
- 会话附件上传、列表、下载和删除，支持 CSV、XLSX、JSON、TXT；
- 附件类型、单文件 20 MB 和单会话 100 MB 限制；
- 附件自动解析、解析状态展示和失败后手动重试；
- 分析任务创建、查询、取消、重试、并发限制和持久化日志；
- 一次性 WebSocket 令牌和实时任务状态事件；
- 受控任务状态转换、成功结果原子提交和后端重启恢复；
- 单进程异步分析任务执行器和协作式取消；
- 经过结构校验的确定性演示结果；
- 文本、工具、结果和终态的完整 WebSocket 实时事件；
- Docker Compose 本地运行环境；
- 存活与就绪健康检查；
- 前后端基础测试入口；
- 受控的上传、导出和临时工作目录。

M3 实时分析任务已经闭环。M4 将继续实现只读数据查询、指标计算和经营归因能力。

## 快速启动

1. 复制环境变量模板：

   ```powershell
   Copy-Item .env.example .env
   ```

2. 编辑 `.env`，至少填写：

   - `APP_SECRET_KEY`：长度不少于 32 位的随机字符串；
   - `POSTGRES_PASSWORD`：本地 PostgreSQL 密码；
   - `DATABASE_URL`：使用相同密码的开发数据库连接；
   - `TEST_DATABASE_URL`：数据库名必须以 `_test` 结尾。

   可以用下面的命令生成随机签名密钥：

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

3. 启动服务：

   ```powershell
   docker compose up --build
   ```

4. 访问：

   - Web：<http://localhost:3000>
   - 模拟登录：在 Web 首页点击“进入演示登录”，选择分析用户或系统管理员
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

后端质量检查使用隔离的 Docker 测试镜像：

```powershell
docker build --target test -t insighttrace-backend-test backend
docker run --rm insighttrace-backend-test ruff check app tests alembic
```

数据库集成测试只允许使用名称以 `_test` 结尾的独立数据库：

```powershell
docker compose --profile test run --rm --build backend-test
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
