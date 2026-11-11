# 企业知识库工单系统

面向企业内部的知识库问答与工单处理系统：员工和领导都能基于企业文档提问；员工对知识库的新增、修改、删除需领导审批；工单覆盖提交、审核、指派、处理、回退、确认、解决全流程。

## 当前状态

| 项 | 内容 |
|---|---|
| 阶段 | 首版主体框架完成（Phase 0–4 已验收），Phase 5 交付文档，评测系统首版已实现 |
| 设计文档 | [docs/00-文档索引.md](docs/00-文档索引.md) |
| 测试手册 | [docs/08-首版测试手册.md](docs/08-首版测试手册.md) |
| 已知问题 | [docs/10-已知问题.md](docs/10-已知问题.md) |
| 开发过程问题 | [docs/11-开发过程问题记录.md](docs/11-开发过程问题记录.md) |
| 评测系统 | [docs/12-评测系统设计.md](docs/12-评测系统设计.md) |
| 后续规划 | [docs/09-后续规划.md](docs/09-后续规划.md) |

首版范围：RAG 问答与引用、文档上传/解析/索引/审批、文档批量删除与回收站、员工与领导工单全状态流转、补录历史工单、附件、筛选、历史隔离、RAG 回归评测。不包含：检索准确率调优、OCR、agent 辅助填单、审计、生产部署。

## 技术栈

| 层次 | 选型 |
|---|---|
| 前端 | Next.js 15 App Router + TypeScript + Tailwind CSS（自研组件，未使用组件库 CLI） |
| 后端 | FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic v2 |
| 数据库 | PostgreSQL 16 + pgvector（HNSW） |
| 缓存/队列 | Redis 7 + Celery 5 |
| 对象存储 | MinIO |
| Embedding | 本地 BGE-M3（独立服务，CPU 默认，可选 GPU） |
| 生成模型 | DeepSeek（OpenAI 兼容接口，流式） |
| 部署 | Docker Compose（本机优先，预留服务器） |

## 目录结构

```text
企业知识库工单系统/
├── docs/          # 需求、架构、数据模型、API、状态机、前端、测试手册、已知问题
├── server/        # FastAPI 后端、Alembic 迁移、种子脚本
├── embed/         # BGE-M3 embedding 服务
├── web/           # Next.js 前端
├── infra/         # docker-compose、.env.example、基础设施说明
└── README.md
```

## 环境要求

- Windows 11（或 Linux/macOS）
- Docker Desktop 已启动
- Node.js 20+ 与 npm（仅前端需要）
- 浏览器：Chrome / Edge 最新版
- 可访问 DeepSeek API（需要 Key）；无法访问时可用本地模拟回答联调

> 如果 Docker 拉镜像失败，需要给 Docker Desktop 配置代理（本机环境使用 FlClash `127.0.0.1:7890`）。Docker 的镜像拉取不走系统代理，需在 Docker Desktop → Settings → Resources → Proxies 中手动填写。

## 快速启动

### 1. 准备环境变量

```bash
cd infra
cp .env.example .env
```

PowerShell 可用：

```powershell
Copy-Item .env.example .env
```

编辑 `infra/.env`，至少确认：

- `JWT_SECRET`：改成随机长字符串。
- `DEEPSEEK_API_KEY`：填入真实 Key；留空时按 `LLM_PROVIDER=auto` 回退到本地模拟回答。
- `LLM_PROVIDER=auto`：有 Key 用 DeepSeek，没有则用 mock。
- `MINIO_*`、`DATABASE_URL`、`REDIS_URL` 保持默认即可，容器内通过服务名访问。

### 2. 启动后端与依赖

```bash
docker compose up -d --build
```

GPU 模式（需要 Docker Desktop GPU 直通）：

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

首次启动会拉取镜像、安装依赖、下载 BGE-M3 模型，耗时较长；`embedding` 第一次收到请求时才会加载模型。

### 3. 检查健康状态

```bash
curl.exe http://localhost:8000/health/ready
```

预期：

```json
{"status":"ok","components":{"database":"ok","redis":"ok","minio":"ok","embedding":"ok"}}
```

### 4. 启动前端

另开一个终端，在项目根目录执行：

```bash
cd web
npm install
npm run dev
```

访问 <http://localhost:3000>。

前端默认请求 `http://localhost:8000/api/v1`；如需修改，在 `web/.env.local` 设置 `NEXT_PUBLIC_API_BASE`。

## 端口

| 服务 | 宿主机端口 | 说明 |
|---|---|---|
| 前端 | 3000 | Next.js dev server |
| API | 8000 | FastAPI，文档在 `/docs` |
| Embedding | 8001 | BGE-M3 服务 |
| PostgreSQL | 5433 | 容器内 5432；避开本机其他项目占用 |
| Redis | 6380 | 容器内 6379 |
| MinIO API | 9010 | 容器内 9000 |
| MinIO 控制台 | 9011 | `minioadmin / minioadmin` |

容器之间仍使用 `postgres:5432`、`redis:6379`、`minio:9000` 通信，修改宿主机映射不影响服务间调用。

## 账号

种子脚本在 api 启动时自动执行；已存在账号会跳过。

| 用户名 | 密码 | 角色 |
|---|---|---|
| `leader` | `Leader@123` | 领导 |
| `employee1` | `Employee@123` | 员工 |
| `employee2` | `Employee@123` | 员工 |

## 常用命令

在项目根目录执行：

```bash
cd infra
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f embedding
docker compose restart api
docker compose down
docker compose down -v   # 删除数据卷，仅测试环境使用
```

重新执行迁移与种子：

```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m scripts.seed
```

## 配置说明

完整变量见 `infra/.env.example`，常用项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `auto` | `auto` / `deepseek` / `mock` |
| `CONVERSATION_HISTORY_TURNS` | 5 | 多轮上下文保留轮数 |
| `TOP_K` | 5 | 兼容保留，实际使用 `FINAL_K` |
| `CHUNK_TARGET` / `CHUNK_MAX` / `CHUNK_MIN` | 450 / 700 / 150 | 结构化切分的目标、上限、下限字符数 |
| `CHUNK_OVERLAP` | 60 | 段内句级切分重叠字符数 |
| `CANDIDATE_K` / `FUSED_K` / `FINAL_K` | 30 / 40 / 5 | 双路召回数、融合后候选数、最终引用数 |
| `HYBRID_ENABLED` | `true` | 稠密 + 关键词混合检索（RRF 融合） |
| `RERANK_ENABLED` / `RERANK_TOP_N` | `false` / 40 | 精排开关与精排候选数（CPU 环境建议关闭） |
| `RERANK_THRESHOLD` | `0` | 精排分数阈值；实测当前语料不适用，保持 0 |
| `REWRITE_ENABLED` | `true` | 多轮指代问题的检索改写 |
| `RERANK_TIMEOUT_SECONDS` | 30 | 精排超时，超时自动回退到融合排序 |
| `MAX_UPLOAD_MB` | 50 | 单文件上限 |
| `EMBEDDING_DEVICE` | `cpu` | 可改 `cuda`（需 GPU 镜像） |
| `COOKIE_SECURE` | `false` | 本机 HTTP 保持 false；HTTPS 部署时改 true |

## 评测系统

- 入口：侧边栏「评测」，仅领导与被授权员工可见；领导可在评测首页给员工开关权限。
- 支持数据集、用例、轮次维护，JSONL 导入导出，后台异步运行、进度和取消，汇总指标、逐轮结果、基线对比与 JSONL/CSV 导出。
- 运行不写入问答会话，不污染真实历史；同一数据集同时只允许一个运行。

生成初始草稿（需要配置 `DEEPSEEK_API_KEY`）：

```bash
docker compose exec api python -m scripts.generate_eval_drafts --single 30 --multi 10 --out /app/eval-drafts.jsonl
```

```bash
docker compose cp api:/app/eval-drafts.jsonl ../eval-drafts.jsonl
```

草稿不会直接入库，审核后在评测页通过「导入 JSONL」导入。设计与指标定义见 [docs/12-评测系统设计.md](docs/12-评测系统设计.md)。

## 数据边界

- 文档原文、分块向量、工单附件只存储在本机 PostgreSQL / MinIO。
- 只有“用户问题 + top-5 检索片段”发送给 DeepSeek。
- `.env`、模型文件、上传文件不提交到版本库。

## 测试与已知问题

- 按 [docs/08-首版测试手册.md](docs/08-首版测试手册.md) 逐项测试。
- 首版已知问题与已复现缺陷见 [docs/10-已知问题.md](docs/10-已知问题.md)。PDF NUL 字节（001）、DOCX MIME（002）、期望完成时间（004）、超长标题与附件名（005）、日期筛选时区（006）已修复；登录页预填账号、文档详情下载提示、问答 SSE 401 等问题当前未修复。
- 环境、依赖、端口、VS Code npm、Celery 事件循环等开发过程中实际遇到的问题见 [docs/11-开发过程问题记录.md](docs/11-开发过程问题记录.md)。
- 问题按统一模板记录：用例编号、前置条件、步骤、预期、实际、截图/日志、是否稳定复现。
