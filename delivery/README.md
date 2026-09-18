# InsightTrace MVP v1 最终交付

> 交付日期：2026-09-18；交付范围：M0–M5

## 交付内容

- 可通过 Docker Compose 运行的 React + FastAPI + PostgreSQL 应用；
- 内置模拟 OAuth 的分析用户和系统管理员身份；
- 会话、消息、附件、实时任务、结构化结果和 Markdown 报告闭环；
- 商品目录与客户行为两套真实演示数据及多轮脚本；
- 只读 SQL、资源隔离、文件边界、一次性令牌和日志脱敏防护；
- 管理员健康、配置重载和任务日志面板；
- 项目规划、技术设计、API、运维、演示和验收文档。

## 验收入口

- [M5 验收报告](./ACCEPTANCE_REPORT.md)
- [项目规划](../PROJECT_PLAN.md)
- [技术设计](../TECHNICAL_DESIGN.md)
- [API 接口说明](../API_REFERENCE.md)
- [部署与操作说明](../OPERATIONS.md)
- [多轮演示脚本](../DEMO_SCRIPTS.md)
- [就绪首页截图](./screenshots/01-home-ready.png)
- [管理员登录截图](./screenshots/02-admin-signed-in.png)

## 启动

按 [部署与操作说明](../OPERATIONS.md) 配置 `.env`，然后执行：

```powershell
docker compose up --build
```

浏览器打开 <http://localhost:3000>，选择演示身份即可开始。
