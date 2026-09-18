# InsightTrace API 接口说明

本文档对应当前仓库的 MVP v1 接口。交互式 OpenAPI 页面位于
`http://localhost:8000/docs`。

## 1. 通用约定

- 后端直连地址：`http://localhost:8000`；
- 前端容器会把 `/api`、`/auth`、`/health` 和 WebSocket 请求代理到后端；
- 除健康检查和登录流程外，业务接口都要求有效的 `insighttrace_session` Cookie；
- Cookie 为 `HttpOnly`、`SameSite=Lax`，前端请求必须携带凭据；
- UUID、日期时间和枚举值均使用 JSON 字符串；
- 用户只能访问自己的会话、附件、任务和结果，越权访问统一返回资源不存在；
- 创建任务时会同时保存用户消息，不需要再调用消息创建接口。

统一错误结构：

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "资源不存在",
    "details": {},
    "request_id": "请求追踪 ID"
  }
}
```

常见状态码：`400` 登录流程无效，`401` 未登录，`404` 资源不存在，`409` 状态冲突，
`422` 参数校验失败，`500` 未预期错误。

## 2. 健康检查

| 方法 | 路径 | 认证 | 用途 |
| --- | --- | --- | --- |
| GET | `/health/live` | 否 | 确认后端进程存活 |
| GET | `/health/ready` | 否 | 检查数据库和存储目录是否可用 |

`/health/ready` 任一组件失败时返回 `503`，响应中的 `components` 会分别显示数据库和
存储状态。

## 3. 模拟 OAuth 与当前用户

| 方法 | 路径 | 认证 | 用途 |
| --- | --- | --- | --- |
| GET | `/auth/login` | 否 | 创建登录状态并跳转到模拟授权页 |
| GET | `/auth/mock/authorize` | 登录状态 | 展示分析用户和管理员选择页 |
| POST | `/auth/mock/authorize` | 登录状态 | 签发一次性模拟授权码 |
| GET | `/auth/callback` | 授权码 | 建立 Cookie 会话并跳回前端 |
| POST | `/auth/logout` | 否 | 清空当前 Cookie 会话 |
| GET | `/api/me` | 是 | 返回当前用户身份与角色 |

登录流程应由浏览器完成，不要手工保存或转发 Cookie。模拟授权码和 `state` 都有有效期，
且只能用于当前登录流程。

## 4. 会话与消息

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/conversations` | 列出当前用户的会话 |
| POST | `/api/conversations` | 创建会话 |
| PATCH | `/api/conversations/{conversation_id}` | 重命名、归档或恢复会话 |
| DELETE | `/api/conversations/{conversation_id}` | 删除会话及关联资源 |
| GET | `/api/conversations/{conversation_id}/messages` | 获取历史消息 |
| POST | `/api/conversations/{conversation_id}/messages` | 只保存一条用户消息 |

创建会话：

```json
{"title": "商品目录转化诊断"}
```

更新会话至少提供一个字段：

```json
{"title": "八月商品诊断", "status": "archived"}
```

`status` 只接受 `active` 或 `archived`。归档会话仍可读取历史，但不能新增消息、上传附件、
创建任务或重试任务。删除会话会级联删除数据库记录，并清理对应上传和导出目录。

## 5. 附件

基础路径：`/api/conversations/{conversation_id}/attachments`。

| 方法 | 相对路径 | 用途 |
| --- | --- | --- |
| GET | `` | 列出未删除附件 |
| POST | `` | 以 `multipart/form-data` 上传并自动解析 |
| POST | `/{attachment_id}/parse` | 重新解析附件 |
| GET | `/{attachment_id}/download` | 下载原文件 |
| DELETE | `/{attachment_id}` | 删除附件记录与文件 |

上传字段名为 `file`。支持 CSV、XLSX、JSON 和 TXT；默认单文件上限 20 MB、单会话总量
上限 100 MB、单任务最多选择 20 个附件。只有 `parse_status=success` 的附件能用于任务。

## 6. 分析任务

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/tasks` | 创建任务并保存用户消息 |
| GET | `/api/conversations/{conversation_id}/tasks` | 列出会话任务 |
| GET | `/api/tasks/{task_id}` | 查询任务最新状态 |
| POST | `/api/tasks/{task_id}/cancel` | 取消排队任务或请求运行任务停止 |
| POST | `/api/tasks/{task_id}/retry` | 重试失败或已取消任务 |
| GET | `/api/tasks/{task_id}/logs` | 查询持久化执行日志 |

创建演示任务：

```json
{
  "conversation_id": "会话 UUID",
  "input_text": "为什么 2026 年 8 月商品目录的整体转化率较 7 月下降？",
  "attachment_ids": [],
  "analysis_mode": "demo"
}
```

任务状态：`queued`、`running`、`success`、`failed`、`cancelled`。同一会话同一时间只允许
一个 `queued` 或 `running` 任务。运行任务的取消是协作式的；接口返回后应继续轮询任务
或等待 WebSocket 的 `done` 事件。只有 `failed` 和 `cancelled` 任务可以重试。

当前稳定步骤：`preparing_context`、`inspecting_sources`、`querying_data`、
`calculating_metrics`、`building_evidence`、`generating_conclusion`、`saving_result`。

## 7. 实时事件

先签发一次性令牌：

```http
POST /api/chat/ws-token
Content-Type: application/json

{"conversation_id": "会话 UUID"}
```

随后立即连接：

```text
ws://localhost:3000/api/chat/ws/chat?websocket_token=令牌&conversation_id=会话UUID
```

令牌默认 60 秒过期，只能消费一次。所有事件共享以下外层结构：

```json
{
  "event_id": "事件 UUID",
  "event_type": "task_status",
  "task_id": "任务 UUID 或 null",
  "conversation_id": "会话 UUID",
  "seq_no": 1,
  "timestamp": "ISO 8601 时间",
  "payload": {}
}
```

| 事件 | 说明 |
| --- | --- |
| `connected` | 令牌验证成功 |
| `task_status` | 任务状态、当前步骤或取消请求变化 |
| `message_start` | 助手增量消息开始 |
| `message_delta` | 新增一段助手文本 |
| `tool_start` | 工具调用开始 |
| `tool_finish` | 工具调用完成 |
| `result_ready` | 结构化结果已经持久化 |
| `error` | 令牌或任务失败信息 |
| `done` | 终态事件，随后正常关闭连接 |

令牌无效、过期或重复使用时先发送 `error`，再以 WebSocket 关闭码 `4401` 关闭。

## 8. 分析结果与报告

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/results/{task_id}` | 获取六部分结构化结果 |
| POST | `/api/results/{task_id}/export` | 生成或覆盖 Markdown 报告 |
| GET | `/api/results/{task_id}/download` | 下载已经生成的报告 |

结构化结果包含问题定义、关键指标、证据、结论、缺失数据、下一步建议、Markdown 正文、
生成模式和整体置信度。必须先调用 `export`，`download` 才可用。

## 9. 演示分析范围

`demo` 模式支持：

- 商品目录：整体转化、类目、商品、渠道、设备和点击到加购漏斗；
- 客户行为：访问到下单漏斗、渠道、地区、新老访客和可疑会话；
- 同一会话内依据上一轮结构化证据继承场景的模糊追问。

`model` 是预留枚举，目前没有外部模型执行器。MVP 演示应使用 `demo`。
