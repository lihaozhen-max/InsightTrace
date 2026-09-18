# InsightTrace 部署与操作说明

本文档面向 Windows + Docker Desktop 的本地 MVP 演示环境。命令默认在仓库根目录执行。

## 1. 运行前提

- Docker Desktop 已启动；
- Docker Compose v2 可用；
- 本机端口 `3000`、`5432`、`8000` 未被其他服务占用；
- 仓库中存在 `.env.example`；
- 不要把 `.env`、数据库密码、Cookie、WebSocket 令牌或模型密钥提交到 Git。

## 2. 首次配置

复制模板：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少填写：

```dotenv
APP_SECRET_KEY=<至少32位的随机字符串>
POSTGRES_PASSWORD=<本地数据库密码>
DATABASE_URL=postgresql+asyncpg://insighttrace:<URL编码后的密码>@postgres:5432/insighttrace
TEST_DATABASE_URL=postgresql+asyncpg://insighttrace:<URL编码后的密码>@postgres:5432/insighttrace_test
```

生成签名密钥：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

容器内数据库主机名必须写 `postgres`，不能写 `localhost`。如果密码包含 `@`、`:`、`/`
等 URL 特殊字符，应在连接字符串中进行 URL 编码。演示环境保持
`ANALYSIS_MODE=demo`，不需要模型密钥。

## 3. 启动和访问

首次启动或代码更新后执行：

```powershell
docker compose up -d --build
docker compose ps
```

后端容器启动时会先执行 `alembic upgrade head`，然后启动 FastAPI。访问地址：

- 前端：<http://localhost:3000>
- API 文档：<http://localhost:8000/docs>
- 存活检查：<http://localhost:8000/health/live>
- 就绪检查：<http://localhost:8000/health/ready>

等待 `postgres` 和 `backend` 显示 healthy 后，再打开前端并完成模拟登录。

## 4. 日常更新

获取新代码后：

```powershell
git pull --ff-only
docker compose up -d --build
docker compose ps
```

`postgres_data` 是命名卷，普通重建不会删除数据库。`storage/` 是仓库下的运行时目录，保存
上传文件和导出的 Markdown 报告。升级完成后检查：

```powershell
docker compose exec backend alembic current
Invoke-RestMethod http://localhost:8000/health/ready
```

不要使用 `docker compose down -v` 进行普通升级，因为 `-v` 会删除数据库卷。

## 5. 停止与重新启动

停止但保留数据：

```powershell
docker compose stop
```

重新启动：

```powershell
docker compose start
```

移除容器但保留命名卷：

```powershell
docker compose down
```

后端重启时，遗留的 `running` 任务会被标记为可重试失败。用户可在页面点击重新分析，
或调用任务重试接口；已经成功保存的结果不会受影响。

## 6. 日志与健康排查

查看所有服务最近日志：

```powershell
docker compose logs --tail 200
```

持续查看后端日志：

```powershell
docker compose logs -f --tail 100 backend
```

单独检查数据库：

```powershell
docker compose exec postgres pg_isready -U insighttrace -d insighttrace
```

任务过程日志也会持久化到数据库，可通过页面或
`GET /api/tasks/{task_id}/logs` 查看。对外报告问题时优先提供错误响应中的 `request_id`，
不要复制包含 Cookie、密码或令牌的请求头。

## 7. 测试

数据库集成测试只允许连接数据库名以 `_test` 结尾的独立数据库：

```powershell
docker compose --profile test run --rm --build backend-test
```

后端静态检查：

```powershell
docker compose --profile test run --rm --build backend-test ruff check app tests alembic
```

前端测试和生产构建：

```powershell
Push-Location frontend
npm ci
npm test
npm run build
Pop-Location
docker build -t insighttrace-frontend-check frontend
```

这一步需要本机安装 Node.js 22；只运行部署环境时不需要本机 Node.js。

完整演示步骤见 [DEMO_SCRIPTS.md](./DEMO_SCRIPTS.md)。

## 8. 数据备份

先创建本地备份目录：

```powershell
New-Item -ItemType Directory -Force backups
```

在数据库容器内生成自定义格式备份，再复制到本机：

```powershell
docker compose exec postgres pg_dump -U insighttrace -d insighttrace -Fc -f /tmp/insighttrace.dump
docker compose cp postgres:/tmp/insighttrace.dump backups/insighttrace.dump
docker compose exec postgres rm /tmp/insighttrace.dump
```

同时备份 `storage/`，否则数据库里的附件和报告记录可能找不到对应文件。`backups/` 不应
提交到公共仓库。

## 9. 数据恢复

恢复会覆盖目标数据库内的对象，只能在已经确认目标和备份文件后执行。恢复前先停止后端，
避免业务请求同时写入：

```powershell
docker compose stop backend
docker compose cp backups/insighttrace.dump postgres:/tmp/insighttrace.dump
docker compose exec postgres pg_restore --clean --if-exists --no-owner -U insighttrace -d insighttrace /tmp/insighttrace.dump
docker compose exec postgres rm /tmp/insighttrace.dump
docker compose start backend
```

恢复对应的 `storage/` 备份后，再检查 `/health/ready` 和关键会话资源。

## 10. 完全重置本地演示环境

以下操作会永久删除本地数据库卷，且不会自动恢复 `storage/` 文件。只有明确需要空环境并已
确认备份后才能执行：

```powershell
docker compose down -v
docker compose up -d --build
```

## 11. 常见问题

### 前端无法打开

执行 `docker compose ps`，确认 `frontend` 正在运行且端口映射为 `3000:80`。再查看
`docker compose logs --tail 100 frontend`。

### 后端一直 unhealthy

先访问 `/health/ready`。数据库失败时检查 `DATABASE_URL` 中主机名、用户名和 URL 编码后的
密码；存储失败时检查 `storage/` 是否可写。

### 登录后又变成未登录

确认浏览器访问的是配置在 `FRONTEND_URL` 和 `CORS_ORIGINS` 中的地址，并允许 Cookie。
不要混用 `localhost` 与 `127.0.0.1`。

### 任务一直 queued

查看后端日志确认单进程任务执行器已启动。测试环境不会启动后台执行器；正常演示环境应使用
`APP_ENV=development` 或 `production`。

### 报告无法下载

先调用导出功能生成报告，并确认 `storage/exports` 可写。数据库恢复后还必须恢复匹配的
`storage/` 备份。
