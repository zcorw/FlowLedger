# F0 基线版本 配置与启动说明

> 目标：按 `codex_prompts/F0_baseline.prompt.txt` 提供最小可用 API 与基础设施的一次性配置、启动与验证指引。

## 文件总览

- 基础设施
  - `infra/docker-compose.yml`：PostgreSQL + API 服务（API 从 `api/Dockerfile` 构建）
- API 代码与镜像
  - `api/Dockerfile`：API 容器镜像构建文件
  - `api/requirements.txt`：依赖清单
  - `api/app/main.py`：FastAPI 应用，提供 `/healthz`
- 数据库迁移（占位）
  - `alembic.ini`、`alembic/env.py`、`alembic/versions/.gitkeep`
- 测试与 CI
  - `tests/test_healthz.py`、`pytest.ini`
  - `.github/workflows/ci.yml`：格式检查（ruff/black）+ 单测
- 环境变量
  - `.env.example`：示例环境，复制为 `.env` 使用

## 先决条件

- 已安装 Docker 与 Docker Compose v2
- 可选：Python 3.11+（本机直接运行单测时需要）

## 配置环境

1) 复制示例环境并编辑
   - `cp .env.example .env`
   - 核心变量说明：
     - `DATABASE_URL`（API/Alembic 使用）：默认 `postgresql://flow_ledger:flow_ledger@db:5432/flow_ledger`
     - `POSTGRES_DB|USER|PASSWORD|PG_PORT`：本地数据库与端口映射；默认无需修改
     - 其他变量（如 `BOT_TOKEN`、`API_BASE_URL`）可保留默认，后续接入时再配置

2) 目录结构确认
   - 确保上述“文件总览”中的路径存在；`infra/docker-compose.yml` 将从 `api/Dockerfile` 构建镜像

## 启动（Docker Compose）

- 构建并启动数据库 + API（在 `infra/` 目录下）
  - Bash/Zsh:
    - `cd infra && docker compose --env-file ../.env up -d --build`
  - PowerShell:
    - `cd infra; docker compose --env-file ../.env up -d --build`

- 验证 API 健康检查
  - 浏览器/命令行访问 `http://localhost:8000/healthz`
  - 期望响应：`{"ok": true}`

- 常用运维命令
  - 查看日志：`docker compose logs -f api`
  - 重建 API：`docker compose up -d --build api`
  - 关闭并清理：`docker compose down`（不删卷），`docker compose down -v`（删除卷，谨慎）

## 运行测试（本机）

- 安装依赖：`pip install -r api/requirements.txt`
- 运行单测：
  - Bash/Zsh：`PYTHONPATH=api pytest -q`
  - PowerShell：`$env:PYTHONPATH='api'; pytest -q`
- 覆盖内容：`tests/test_healthz.py` 断言 `/healthz` 返回 200 与 `{"ok": True}`

## Alembic（占位，无迁移）

- 说明：当前未定义模型/表，`alembic` 已初始化但不会执行任何迁移
- 可选命令（将来接入模型后使用）：
  - 生成迁移：`alembic revision -m "init"`
  - 应用迁移：`alembic upgrade head`
  - 环境变量：从 `.env` 加载 `DATABASE_URL`

## 常见问题

- 8000 端口占用：修改端口映射（编辑 `infra/docker-compose.yml` 的 `ports: 8000:8000`），或释放端口
- 连接数据库失败：确认 `db` 服务健康（`docker compose ps`），以及 `DATABASE_URL` 主机名为 `db`
- 测试导入失败：确保设置 `PYTHONPATH=api`（见“运行测试”）

## 后续工作（超出 F0 范围）

- 在 `api/app` 中加入实际业务模块与路由，完善 `alembic` 迁移
- 根据需要扩展 `infra/docker-compose.yml`（健康检查、资源限制）
- 接入 Telegram Bot、OCR、调度等模块，并在 `.env` 中完善对应变量

## 数据库初始化（一次性迁移作业）

- 目的：使用一次性 job 自动执行 `sql/schema/*.sql`，并在存在时加载 `sql/sample/*.sql` 示例数据。
- 命令：
  - `cd infra`
  - `docker compose --env-file ../.env run --rm db-migrate`
- 说明：
  - 作业依赖 `db` 健康检查通过后执行；
  - schema 脚本使用 `CREATE IF NOT EXISTS` 与触发器/索引幂等策略，重复执行安全；
  - 示例数据目录可选（不存在则跳过）。
- 常见问题：
  - 权限/连通性报错：检查 `.env` 中 `POSTGRES_*` 是否与 `db` 服务一致；
  - Windows 路径映射：确保在 `infra` 目录执行命令并带上 `--env-file ../.env`。
