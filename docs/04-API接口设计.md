# 04 API 接口设计

## 1. 通用约定

### 1.1 基础信息

| 项 | 约定 |
|---|---|
| Base URL | `/api/v1` |
| 认证方式 | JWT 放在 httpOnly Cookie `access_token` 中 |
| 请求格式 | JSON；文件上传使用 `multipart/form-data` |
| 响应格式 | JSON；问答流使用 `text/event-stream` |
| 时间格式 | ISO 8601 UTC，例如 `2026-11-09T10:00:00Z` |
| 分页参数 | `page`（默认 1）、`page_size`（默认 20，最大 100） |
| 分页响应 | `{ "items": [], "total": 0, "page": 1, "page_size": 20 }` |
| 文件上限 | 50MB |
| 允许扩展名 | `.pdf`、`.docx`、`.md`、`.markdown`、`.txt` |

前端请求需要携带 `credentials: "include"`，后端 CORS 允许配置的前端来源并开启 `allow_credentials`。

### 1.2 错误响应

```json
{
  "error": {
    "code": "TICKET_INVALID_TRANSITION",
    "message": "当前状态不允许该操作",
    "details": {}
  }
}
```

### 1.3 乐观锁

所有工单状态变更接口都必须在请求体中携带当前 `version`。服务端更新条件包含 `id`、`version` 和期望状态；影响行数为 0 时返回 `409 CONFLICT_VERSION` 或 `409 TICKET_INVALID_TRANSITION`。

### 1.4 角色

| 编码 | 含义 |
|---|---|
| `employee` | 员工 |
| `leader` | 领导 |

## 2. 接口总览

| 模块 | 方法 | 路径 | 权限 |
|---|---|---|---|
| 认证 | POST | `/auth/login` | 公开 |
| 认证 | POST | `/auth/logout` | 登录用户 |
| 认证 | GET | `/auth/me` | 登录用户 |
| 用户 | GET | `/users` | 领导 |
| 会话 | GET | `/conversations` | 登录用户（仅自己） |
| 会话 | GET | `/conversations/{id}` | 登录用户（仅自己） |
| 会话 | DELETE | `/conversations/{id}` | 登录用户（仅自己） |
| 问答 | POST | `/chat/stream` | 登录用户 |
| 文档 | GET | `/documents` | 登录用户 |
| 文档 | GET | `/documents/{id}` | 登录用户 |
| 文档 | GET | `/documents/{id}/download` | 登录用户 |
| 文档 | POST | `/documents` | 登录用户（员工待审、领导直接） |
| 文档 | PUT | `/documents/{id}` | 登录用户（员工待审、领导直接） |
| 文档 | DELETE | `/documents/{id}` | 登录用户（员工待审、领导直接） |
| 文档 | POST | `/documents/{id}/reindex` | 领导 |
| 文档审批 | GET | `/document-changes` | 领导全部；员工仅自己 |
| 文档审批 | GET | `/document-changes/{id}` | 领导或申请人 |
| 文档审批 | POST | `/document-changes/{id}/approve` | 领导 |
| 文档审批 | POST | `/document-changes/{id}/reject` | 领导 |
| 工单 | POST | `/tickets` | 登录用户 |
| 工单 | GET | `/tickets` | 登录用户（角色范围） |
| 工单 | GET | `/tickets/{id}` | 提交人、处理人、领导 |
| 工单 | PATCH | `/tickets/{id}` | 处理人（仅 `returned`） |
| 工单 | POST | `/tickets/{id}/approve` | 领导 |
| 工单 | POST | `/tickets/{id}/reject` | 领导 |
| 工单 | POST | `/tickets/{id}/assign` | 领导 |
| 工单 | POST | `/tickets/{id}/complete` | 处理人 |
| 工单 | POST | `/tickets/{id}/modify-complete` | 处理人 |
| 工单 | POST | `/tickets/{id}/confirm` | 提交领导 |
| 工单附件 | POST | `/tickets/{id}/attachments` | 处理人（仅 `returned`） |
| 工单附件 | DELETE | `/tickets/{id}/attachments/{attachment_id}` | 处理人（仅 `returned`） |
| 工单附件 | GET | `/tickets/{id}/attachments/{attachment_id}/download` | 可查看该工单的人 |
| 健康检查 | GET | `/health/live` | 公开 |
| 健康检查 | GET | `/health/ready` | 公开 |

## 3. 认证接口

### 3.1 登录

`POST /api/v1/auth/login`

请求：

```json
{
  "username": "employee1",
  "password": "Employee@123"
}
```

成功响应 `200`，并设置 Cookie：

```json
{
  "user": {
    "id": "UUID",
    "username": "employee1",
    "display_name": "张员工",
    "role": "employee"
  }
}
```

失败：`401 AUTH_INVALID_CREDENTIALS`。

### 3.2 退出登录

`POST /api/v1/auth/logout`

响应 `204`，清除 `access_token` Cookie。

### 3.3 当前用户

`GET /api/v1/auth/me`

响应：

```json
{
  "id": "UUID",
  "username": "employee1",
  "display_name": "张员工",
  "role": "employee"
}
```

未登录：`401 AUTH_TOKEN_INVALID`。

## 4. 用户接口

### 4.1 员工列表（用于指派）

`GET /api/v1/users?role=employee`

仅领导可调用。响应：

```json
{
  "items": [
    {"id": "UUID", "display_name": "张员工", "role": "employee"},
    {"id": "UUID", "display_name": "李员工", "role": "employee"}
  ]
}
```

越权：`403 AUTH_FORBIDDEN`。

## 5. 会话与问答接口

### 5.1 会话列表

`GET /api/v1/conversations?page=1&page_size=20`

仅返回当前用户的会话，按 `updated_at` 倒序。

```json
{
  "items": [
    {
      "id": "UUID",
      "title": "年假怎么申请",
      "created_at": "2026-11-09T09:00:00Z",
      "updated_at": "2026-11-09T09:05:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 5.2 会话详情

`GET /api/v1/conversations/{conversation_id}`

仅会话所有者可访问。响应包含消息与引用：

```json
{
  "id": "UUID",
  "title": "年假怎么申请",
  "created_at": "2026-11-09T09:00:00Z",
  "updated_at": "2026-11-09T09:05:00Z",
  "messages": [
    {
      "id": "UUID",
      "role": "user",
      "content": "年假需要提前几天申请？",
      "citations": null,
      "created_at": "2026-11-09T09:00:00Z"
    },
    {
      "id": "UUID",
      "role": "assistant",
      "content": "根据《员工手册》，年假需提前 3 个工作日申请。",
      "citations": [
        {
          "document_id": "UUID",
          "document_title": "员工手册.pdf",
          "chunk_index": 3,
          "snippet": "年假申请需提前 3 个工作日提交……"
        }
      ],
      "created_at": "2026-11-09T09:00:05Z"
    }
  ]
}
```

不存在或不属于当前用户：`404 NOT_FOUND`。

### 5.3 删除会话

`DELETE /api/v1/conversations/{conversation_id}`

响应 `204`；级联删除消息。

### 5.4 流式问答

`POST /api/v1/chat/stream`

请求：

```json
{
  "conversation_id": "UUID 或省略",
  "message": "年假需要提前几天申请？"
}
```

- 省略 `conversation_id` 时创建新会话，标题取消息前 30 个字符。
- 提供 `conversation_id` 时必须属于当前用户，否则 `404 NOT_FOUND`。
- 空消息：`400 CHAT_EMPTY_MESSAGE`。
- 检索：取 top-5 分块；知识库为空时直接返回固定拒答话术，不调用模型。
- 引用列表固定为本次检索到的 top-5 片段，不要求模型输出引用编号。
- 多轮上下文取当前会话最近 5 组 user/assistant 消息；检索只使用当前问题。
- 当 `LLM_PROVIDER=auto` 且未配置 `DEEPSEEK_API_KEY` 时，后端使用本地模拟回答，仅用于联调；配置 Key 后自动使用 DeepSeek。

响应 `200`，`Content-Type: text/event-stream`。事件格式：

```text
event: meta
data: {"conversation_id":"UUID","user_message_id":"UUID"}

event: citations
data: {"items":[{"document_id":"UUID","document_title":"员工手册.pdf","chunk_index":3,"snippet":"..."}]}

event: token
data: {"delta":"根据"}

event: token
data: {"delta":"《员工手册》，"}

event: done
data: {"assistant_message_id":"UUID"}
```

出错时：

```text
event: error
data: {"code":"LLM_UNAVAILABLE","message":"生成服务暂时不可用"}
```

流式响应前发生的错误仍返回普通 JSON 错误响应。

## 6. 文档接口

### 6.1 文档列表

`GET /api/v1/documents?keyword=&page=1&page_size=20`

所有登录用户可访问。`keyword` 匹配标题或文件名。

```json
{
  "items": [
    {
      "id": "UUID",
      "title": "员工手册",
      "filename": "员工手册.pdf",
      "mime_type": "application/pdf",
      "size_bytes": 1024000,
      "index_status": "ready",
      "uploaded_by": {"id": "UUID", "display_name": "王领导"},
      "created_at": "2026-11-09T08:00:00Z",
      "updated_at": "2026-11-09T08:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 6.2 文档详情

`GET /api/v1/documents/{document_id}`

响应单个文档对象；不存在返回 `404 NOT_FOUND`。

### 6.3 下载文档

`GET /api/v1/documents/{document_id}/download`

响应：

```json
{
  "download_url": "http://minio:9000/kb-documents/...",
  "expires_in": 600
}
```

前端直接打开该 URL 下载。首版不提供在线预览。

### 6.4 新增文档

`POST /api/v1/documents`

`multipart/form-data`：

| 字段 | 必填 | 说明 |
|---|---|---|
| `file` | 是 | 文档文件 |
| `title` | 是 | 文档标题 |

行为：

- **领导**：创建 `documents` 记录（`index_status=pending`），投递索引任务，返回 `201`：

```json
{
  "mode": "direct",
  "document": { "id": "UUID", "title": "员工手册", "...": "..." },
  "change": null
}
```

- **员工**：创建 `document_changes`（`action=create`, `status=pending`），返回 `202`：

```json
{
  "mode": "pending_approval",
  "document": null,
  "change": {
    "id": "UUID",
    "action": "create",
    "status": "pending",
    "title": "员工手册",
    "filename": "员工手册.pdf",
    "created_at": "2026-11-09T08:00:00Z"
  }
}
```

错误：`400 DOC_UNSUPPORTED_TYPE`、`400 DOC_TOO_LARGE`。

### 6.5 修改文档

`PUT /api/v1/documents/{document_id}`

`multipart/form-data`：

| 字段 | 必填 | 说明 |
|---|---|---|
| `file` | 否 | 新文件；不传则只改标题 |
| `title` | 否 | 新标题；不传则保留原标题 |

`file` 和 `title` 至少提供一个，否则 `422 VALIDATION_ERROR`。

行为：

- **领导**：直接更新文档；若上传新文件，`index_status` 置为 `pending`，删除旧分块并投递重新索引任务；仅改标题则保持原索引状态；返回 `200 { mode: "direct", document }`。
- **员工**：创建 `document_changes`（`action=update`, `status=pending`）；新旧内容都保持现状，待审批；返回 `202 { mode: "pending_approval", change }`。
- 若该文档已有待审批变更：`409 DOC_CHANGE_ALREADY_PENDING`。

### 6.6 删除文档

`DELETE /api/v1/documents/{document_id}`

行为：

- **领导**：软删除文档（从列表隐藏），清理分块和 MinIO 对象，返回 `200 { mode: "direct" }`。
- **员工**：创建 `document_changes`（`action=delete`, `status=pending`），返回 `202 { mode: "pending_approval", change }`。
- 若该文档已有待审批变更：`409 DOC_CHANGE_ALREADY_PENDING`。

> 删除采用软删除，保留 `documents` 行和变更历史；文档列表和检索会过滤已删除文档。

### 6.7 重新索引文档

`POST /api/v1/documents/{document_id}/reindex`

仅领导。将文档 `index_status` 置为 `pending`，重新投递索引任务，返回 `202`：

```json
{
  "mode": "direct",
  "document": { "id": "UUID", "index_status": "pending" }
}
```

用于索引失败或需要重新解析切分。员工调用返回 `403 AUTH_FORBIDDEN`。

## 7. 文档审批接口

### 7.1 变更列表

`GET /api/v1/document-changes?status=pending&page=1&page_size=20`

- 领导：返回全部变更，可按 `status` 筛选。
- 员工：只返回自己提交的变更。

```json
{
  "items": [
    {
      "id": "UUID",
      "action": "update",
      "status": "pending",
      "document_id": "UUID",
      "document_title": "员工手册",
      "title": "员工手册（2026 版）",
      "filename": "员工手册-2026.pdf",
      "requested_by": {"id": "UUID", "display_name": "张员工"},
      "reviewed_by": null,
      "review_comment": null,
      "created_at": "2026-11-09T08:00:00Z",
      "reviewed_at": null
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 7.2 变更详情

`GET /api/v1/document-changes/{change_id}`

领导或申请人可访问；其他用户 `403 AUTH_FORBIDDEN`。

### 7.3 通过变更

`POST /api/v1/document-changes/{change_id}/approve`

仅领导。请求：

```json
{ "comment": "同意更新" }
```

行为：

- `create`：创建 `documents` 行（`index_status=pending`），投递索引任务。
- `update`：更新标题；若带新文件，更新文件字段、`index_status=pending`、删除旧分块、投递重新索引任务；旧对象在新索引成功后删除。
- `delete`：删除文档行、分块和 MinIO 对象。
- 变更状态改为 `approved`，记录审批人和审批时间。

响应 `200`：

```json
{
  "change": { "id": "UUID", "status": "approved", "reviewed_at": "..." },
  "document": { "id": "UUID", "title": "员工手册（2026 版）" }
}
```

非 `pending` 变更：`409 DOC_CHANGE_NOT_PENDING`。

### 7.4 驳回变更

`POST /api/v1/document-changes/{change_id}/reject`

仅领导。请求：

```json
{ "comment": "文件版本不对，请重新上传" }
```

`comment` 必填；驳回后变更状态为 `rejected`，不影响现有文档；如果变更是新增或修改且上传了新文件，同时删除该文件对象，避免孤儿文件。响应 `200 { change }`。非 `pending` 变更：`409 DOC_CHANGE_NOT_PENDING`。

## 8. 工单接口

### 8.1 创建工单

`POST /api/v1/tickets`

`multipart/form-data`：

| 字段 | 必填 | 说明 |
|---|---|---|
| `title` | 是 | 标题 |
| `description` | 是 | 描述 |
| `type` | 是 | `it_fault` / `permission_request` / `data_request` / `other` |
| `priority` | 是 | `low` / `medium` / `high` / `urgent` |
| `expected_at` | 否 | 期望完成时间，ISO 8601；普通工单必须晚于当前时间 |
| `is_backfilled` | 否 | 布尔，默认 `false`；`true` 表示补录历史工单 |
| `backfill_created_at` | 否 | 补录专用，原创建时间 ISO 8601；不得晚于当前时间 |
| `submitter_id` | 否 | 补录专用；领导可指定启用中的员工为提交人，员工只能补录自己 |
| `files` | 否 | 附件，可多个 |

行为：

- 普通员工创建 → 状态 `new`。
- 普通领导创建 → 状态 `pending_assignment`。
- 补录工单（员工或领导）→ 状态 `new`；领导审核通过直接变 `resolved`，不进入处理中。
- 普通工单的 `expected_at` 早于当前时间返回 `422 VALIDATION_ERROR`。
- `title` 长度 1–255；文档标题、文档文件名、附件文件名超过 255 返回 `422 VALIDATION_ERROR`。
- 补录允许过去的 `expected_at`；`backfill_created_at` 晚于当前时间返回 422。
- 员工在补录时指定他人为提交人返回 `403 TICKET_FORBIDDEN_ACTION`。

响应 `201`，返回工单详情（含 `is_backfilled`、`events`、`attachments`、`available_actions`、`version`）。

### 8.2 工单列表

`GET /api/v1/tickets?status=&type=&priority=&assignee_id=&keyword=&date_from=&date_to=&page=1&page_size=20`

- 员工：`created_by = 当前用户 OR assignee_id = 当前用户`。
- 领导：全部。
- `date_from` / `date_to` 使用 ISO 8601；带时区按该时区解析，不带时区按 `BUSINESS_TIMEZONE`（默认 `Asia/Shanghai`）解释后转 UTC。

`keyword` 匹配标题、描述、工单编号。

```json
{
  "items": [
    {
      "id": "UUID",
      "ticket_no": "T20261109-000001",
      "title": "无法连接公司 VPN",
      "type": "it_fault",
      "priority": "high",
      "status": "in_progress",
      "is_backfilled": false,
      "created_by": {"id": "UUID", "display_name": "张员工"},
      "assignee": {"id": "UUID", "display_name": "李员工"},
      "created_at": "2026-11-09T08:00:00Z",
      "updated_at": "2026-11-09T09:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 8.3 工单详情

`GET /api/v1/tickets/{ticket_id}`

提交人、处理人、领导可访问；其他用户 `403 AUTH_FORBIDDEN`。

```json
{
  "id": "UUID",
  "ticket_no": "T20261109-000001",
  "title": "无法连接公司 VPN",
  "description": "今天上午开始无法连接 VPN，提示认证失败。",
  "type": "it_fault",
  "priority": "high",
  "expected_at": "2026-11-10T18:00:00Z",
  "status": "in_progress",
  "is_backfilled": false,
  "created_by": {"id": "UUID", "display_name": "张员工", "role": "employee"},
  "assignee": {"id": "UUID", "display_name": "李员工", "role": "employee"},
  "resolution": null,
  "version": 3,
  "attachments": [
    {
      "id": "UUID",
      "filename": "错误截图.png",
      "mime_type": "image/png",
      "size_bytes": 204800,
      "uploaded_by": {"id": "UUID", "display_name": "张员工"},
      "created_at": "2026-11-09T08:00:00Z"
    }
  ],
  "events": [
    {
      "id": 1,
      "actor": {"id": "UUID", "display_name": "张员工"},
      "action": "created",
      "from_status": null,
      "to_status": "new",
      "comment": null,
      "created_at": "2026-11-09T08:00:00Z"
    },
    {
      "id": 2,
      "actor": {"id": "UUID", "display_name": "王领导"},
      "action": "approved",
      "from_status": "new",
      "to_status": "in_progress",
      "comment": "转给李员工处理",
      "created_at": "2026-11-09T08:30:00Z"
    }
  ],
  "available_actions": ["complete"],
  "created_at": "2026-11-09T08:00:00Z",
  "updated_at": "2026-11-09T09:00:00Z"
}
```

`available_actions` 由后端按当前用户、角色、状态计算，取值：

- `approve`、`reject`
- `assign`
- `complete`
- `modify_complete`
- `confirm_resolved`、`confirm_unresolved`
- `edit`
- `add_attachment`、`delete_attachment`

### 8.4 编辑工单

`PATCH /api/v1/tickets/{ticket_id}`

仅处理人（`assignee_id`；未指派时为提交人）且状态为 `returned` 时可调用。

```json
{
  "version": 4,
  "title": "无法连接公司 VPN（已补充环境信息）",
  "description": "补充：Windows 11，客户端版本 5.2。",
  "type": "it_fault",
  "priority": "high",
  "expected_at": "2026-11-10T18:00:00Z"
}
```

响应 `200` 更新后的工单详情。`version` 不匹配：`409 CONFLICT_VERSION`；状态不允许：`409 TICKET_NOT_EDITABLE`。

### 8.5 审核通过

`POST /api/v1/tickets/{ticket_id}/approve`

仅领导。请求：

```json
{
  "version": 2,
  "assignee_id": "UUID 或省略",
  "comment": "同意，转给李员工"
}
```

可用状态与效果：

| 当前状态 | 条件 | 结果 |
|---|---|---|
| `new` | 员工提交的工单 | → `in_progress`；`assignee_id` 省略时默认提交人 |
| `completed` | 员工提交的工单 | → `resolved` |
| `modified` | 任意工单 | → `in_progress`；`assignee_id` 可选，若当前无处理人则默认提交人 |

- `assignee_id` 必须是启用中的员工。
- `modified` 通过时，如果工单当前没有处理人（例如 `new` 被驳回后尚未指派），可指定 `assignee_id`；省略则默认提交人。
- 其他状态：`409 TICKET_INVALID_TRANSITION`。
- 版本不匹配：`409 CONFLICT_VERSION`。

### 8.6 审核不通过

`POST /api/v1/tickets/{ticket_id}/reject`

仅领导。请求：

```json
{
  "version": 2,
  "comment": "处理结果不完整，请补充排查步骤"
}
```

可用状态：`new`（员工工单）、`completed`（员工工单）、`modified`。结果均为 → `returned`。`comment` 必填。

### 8.7 指派处理人

`POST /api/v1/tickets/{ticket_id}/assign`

仅领导。请求：

```json
{
  "version": 2,
  "assignee_id": "UUID"
}
```

仅 `pending_assignment` 状态可调用，结果 → `in_progress`。`assignee_id` 必须是启用中的员工。

### 8.8 标记处理完成

`POST /api/v1/tickets/{ticket_id}/complete`

仅当前处理人。请求：

```json
{
  "version": 3,
  "resolution": "已重置 VPN 证书，用户确认可以连接。"
}
```

仅 `in_progress` 状态可调用：

- 员工提交的工单 → `completed`。
- 领导提交的工单 → `pending_user_confirmation`。

### 8.9 标记修改完成

`POST /api/v1/tickets/{ticket_id}/modify-complete`

仅当前处理人（未指派时为提交人）。请求：

```json
{
  "version": 4,
  "comment": "已补充排查步骤和截图"
}
```

仅 `returned` 状态可调用，结果 → `modified`。

### 8.10 确认领导工单是否解决

`POST /api/v1/tickets/{ticket_id}/confirm`

仅提交该工单的领导。请求：

```json
{
  "version": 5,
  "resolved": true,
  "comment": "问题已解决"
}
```

仅 `pending_user_confirmation` 状态可调用：

- `resolved=true` → `resolved`。
- `resolved=false` → `returned`，`comment` 必填。

### 8.11 新增工单附件

`POST /api/v1/tickets/{ticket_id}/attachments`

仅当前处理人，且工单状态为 `returned`。`multipart/form-data`，字段 `file`。响应 `201`，返回附件对象。

### 8.12 删除工单附件

`DELETE /api/v1/tickets/{ticket_id}/attachments/{attachment_id}`

仅当前处理人，且工单状态为 `returned`。响应 `204`，同时删除 MinIO 对象。

### 8.13 下载工单附件

`GET /api/v1/tickets/{ticket_id}/attachments/{attachment_id}/download`

可查看该工单的用户可调用。响应：

```json
{
  "download_url": "http://minio:9000/ticket-attachments/...",
  "expires_in": 600
}
```

## 9. 健康检查

### 9.1 存活检查

`GET /health/live` → `200 {"status":"ok"}`。

### 9.2 就绪检查

`GET /health/ready`

```json
{
  "status": "ok",
  "components": {
    "database": "ok",
    "redis": "ok",
    "minio": "ok",
    "embedding": "ok"
  }
}
```

任一组件异常时返回 `503`，`status` 为 `degraded`，并标明异常组件。

## 10. 错误码

| 错误码 | HTTP | 说明 |
|---|---|---|
| `AUTH_INVALID_CREDENTIALS` | 401 | 用户名或密码错误 |
| `AUTH_TOKEN_INVALID` | 401 | 未登录或令牌无效 |
| `AUTH_FORBIDDEN` | 403 | 角色或数据权限不足 |
| `NOT_FOUND` | 404 | 资源不存在或无权查看 |
| `VALIDATION_ERROR` | 422 | 请求参数校验失败 |
| `CONFLICT_VERSION` | 409 | 工单版本已变化，请刷新后重试 |
| `DOC_UNSUPPORTED_TYPE` | 400 | 不支持的文件类型 |
| `DOC_TOO_LARGE` | 400 | 文件超过 50MB |
| `DOC_EMPTY` | 400 | 文件内容为空 |
| `DOC_CHANGE_ALREADY_PENDING` | 409 | 该文档已有待审批变更 |
| `DOC_CHANGE_NOT_PENDING` | 409 | 变更不是待审批状态 |
| `TICKET_INVALID_TRANSITION` | 409 | 当前状态不允许该操作 |
| `TICKET_FORBIDDEN_ACTION` | 403 | 当前用户不能执行该工单动作 |
| `TICKET_ASSIGNEE_REQUIRED` | 400 | 该操作必须指定处理人 |
| `TICKET_ASSIGNEE_INVALID` | 400 | 处理人不存在或不是启用中的员工 |
| `TICKET_NOT_EDITABLE` | 409 | 只有 `returned` 状态的处理人可以编辑 |
| `CHAT_EMPTY_MESSAGE` | 400 | 消息为空 |
| `CHAT_CONVERSATION_NOT_FOUND` | 404 | 会话不存在或不属于当前用户 |
| `EMBEDDING_UNAVAILABLE` | 503 | embedding 服务不可用 |
| `LLM_UNAVAILABLE` | 503 | 生成服务不可用 |
| `INTERNAL_ERROR` | 500 | 未预期的服务端错误 |

## 11. SSE 客户端约定

1. 使用 `fetch` + `ReadableStream`，因为 `EventSource` 不支持 POST。
2. 请求头：`Accept: text/event-stream`，`Content-Type: application/json`。
3. 按行解析 `event:` 和 `data:`；空行表示事件结束。
4. `token` 事件追加到当前助手消息；`citations` 事件渲染引用卡片；`done` 事件结束并刷新会话列表。
5. `error` 事件展示错误提示，并允许重试。
6. 组件卸载时使用 `AbortController` 取消请求。

## 12. OpenAPI

- FastAPI 自动生成 `/docs` 与 `/openapi.json`。
- 所有路由按模块打 tag：`auth`、`users`、`chat`、`documents`、`document-changes`、`tickets`、`health`。
- 所有受保护接口在 OpenAPI 中标注 Cookie 认证。
- Pydantic 模型作为请求/响应 schema，避免手写重复定义。
