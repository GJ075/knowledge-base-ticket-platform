# 本地基础设施

## 启动

先复制环境变量：

```bash
cp .env.example .env
```

CPU 模式（默认，最稳）：

```bash
docker compose up -d --build
```

GPU 模式（RTX 4060，需要 Docker Desktop 的 GPU 直通）：

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

首次启动会拉取镜像、安装 Python 依赖、下载 BGE-M3 模型，耗时较长。

## 检查

```bash
curl.exe http://localhost:8000/health/ready
```

或在 PowerShell 中：

```powershell
Invoke-RestMethod http://localhost:8000/health/ready
```

API 文档：`http://localhost:8000/docs`  
MinIO 控制台：`http://localhost:9011`（minioadmin / minioadmin）

> 本机已有其他项目占用 5432 / 6379 / 9000 / 9001 时，本项目宿主机映射使用 5433 / 6380 / 9010 / 9011；容器内部端口不变，服务之间仍通过 `postgres:5432`、`redis:6379`、`minio:9000` 通信。

## 预置账号

| 用户名 | 密码 | 角色 |
|---|---|---|
| leader | Leader@123 | 领导 |
| employee1 | Employee@123 | 员工 |
| employee2 | Employee@123 | 员工 |

种子脚本在 api 启动时自动执行；已存在的账号会跳过。

## 常用命令

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f embedding
docker compose exec api alembic upgrade head
docker compose exec api python -m scripts.seed
docker compose down
docker compose down -v   # 删除所有数据，仅测试环境使用
```

## 说明

- MinIO 使用社区重建镜像 `alpine/minio:RELEASE.2025-10-15T17-29-55Z`，并设置 `user: "0:0"` 以写入数据卷。
- 桶名至少 3 个字符：`kb-documents`、`ticket-attachments`。
- 首次调用 `/embed` 时才加载 BGE-M3，第一次请求会明显变慢。
- 如果 GPU 直通失败，退回 CPU 模式即可，接口不变。
