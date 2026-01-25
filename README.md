# Flow-Ledger

面向 Telegram 记账 Bot 的后端项目，包含 FastAPI API、Telegram 机器人、数据库脚本与运行文档。

## 目录结构
- `api/`：FastAPI 服务源码、Dockerfile、依赖清单。
- `bot/`：Telegram Bot 逻辑、Dockerfile。
- `infra/`：其他基础设施与部署相关配置。
- `sql/`：数据库 schema 与示例数据。
- `docs/`：用户指南、部署与接口文档。
- `tests/`：基础单元测试（健康检查）。
- `alembic/`、`alembic.ini`：迁移框架占位。
- `docker-compose.yml`：仓库根目录下的简化编排（挂载源码，方便调试容器）。
- `.env.example`：环境变量示例，复制为 `.env` 使用。

## 快速开始（Docker Compose）
1) 准备环境变量：`cp .env.example .env`，按需修改数据库、Bot、API_BASE_URL 等值。
2) 启动服务（推荐使用 `docker-compose.yml`，支持源码构建）：
   ```bash
   docker compose --env-file .env up -d --build
   ```
3) （可选）初始化数据库：`docker compose --env-file .env run --rm db-migrate`
4) 验证健康检查：访问 `http://localhost:8000/healthz` 期望返回 `{"ok": true}`
5) 常用运维：`docker compose logs -f api` 查看日志；`docker compose down` 关闭容器（`-v` 会清理数据卷，请谨慎）。

> 如果只想启动空跑容器调试挂载，可在仓库根目录使用 `docker compose --env-file .env up -d`（根目录的 compose 文件不构建镜像）。

## 开发与测试
- 本机安装依赖：`pip install -r api/requirements.txt`
- 运行单元测试：
  - PowerShell：`$env:PYTHONPATH='api'; pytest -q`
  - Bash/Zsh：`PYTHONPATH=api pytest -q`

## 数据库字段/DDL 变更
- 将需要的 `ALTER TABLE ... ADD COLUMN ...` 写入 `scripts/run_migration.sql`（建议使用 `ADD COLUMN IF NOT EXISTS` 方便重复执行）。
- 执行迁移（默认数据库服务名 `db`，读取 `.env` 中的 PG 配置）：
  - Linux/macOS：`docker compose --env-file .env exec -T db psql -U $POSTGRES_USER -d $POSTGRES_DB -f - < scripts/run_migration.sql`
  - Windows PowerShell：`Get-Content scripts\run_migration.sql | docker compose --env-file .env exec -T db psql -U $Env:POSTGRES_USER -d $Env:POSTGRES_DB -f -`
- 如列已存在，`IF NOT EXISTS` 可避免报错；执行后请同步更新 `sql/schema/*.sql` 或 Alembic 迁移，保持环境一致。

## 文档
- 用户指南：`docs/guide/telegram_bot.md`（Bot 使用）、`docs/guide/receipt_ocr.md`（OCR 记账）
- 环境/部署：`docs/deploy/f0_baseline_setup.md`
- API/SQL 说明：`docs/api/README.md`、`docs/sql/README.md`
