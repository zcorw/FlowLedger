# Telegram Bot 操作手册

## 1) 先决条件
- Telegram 上通过 @BotFather 申请到 `BOT_TOKEN`。
- 后端 API 可用，并能通过 `API_BASE_URL` 访问 `/v1/users`、`/v1/users/me`、`/v1/users/me/preferences`。
- `.env` 中至少配置：`BOT_TOKEN`、`API_BASE_URL`，可选：`DEFAULT_LANG`、`DEFAULT_TIMEZONE`、`DEFAULT_CURRENCY`、`WEBHOOK_URL`、`WEBHOOK_HOST`、`WEBHOOK_PORT`、`BOT_STATE_PATH`。

## 2) 本地运行（Polling）
- 启动步骤：
  ```bash
  cd bot
  python -m venv .venv && .\.venv\Scripts\activate  # *nix: source .venv/bin/activate
  pip install -r requirements.txt
  set BOT_TOKEN=xxx
  set API_BASE_URL=http://localhost:8000/v1  # API 含 /v1
  python -m main
  ```
- 默认以 long polling 模式运行，`Ctrl+C` 退出。
- 绑定缓存保存在 `BOT_STATE_PATH`（默认 `data/bot_state.json`）。

## 3) Docker Compose（dev）
- `.env` 填好 `BOT_TOKEN`，本地联调推荐 `API_BASE_URL=http://api:8000/v1`。
- 构建并启动 bot：
  ```bash
  cd infra
  docker compose up -d --build bot
  docker compose logs -f bot
  ```
- 数据卷：`botdata`（挂载到容器 `/app/data`），可持久化状态文件。

## 4) Webhook 模式
- 设置 `WEBHOOK_URL` 为外网可达的 HTTPS 地址（如 `https://bot.example.com/telegram`），Webhook path 取 URL 的 path。
- 可选：`WEBHOOK_HOST` 监听地址（默认 `0.0.0.0`），`WEBHOOK_PORT` 监听端口（默认 8081 或取自 URL）。
- 设置后启动时会跳过 polling，注册 webhook 并启动 aiohttp 服务。容器部署需把 `WEBHOOK_PORT` 暴露到反向代理/隧道。

## 5) 支持命令（最小可用）
- `/start` 初始化/创建账户并返回当前偏好。
- `/help` 查看命令列表。
- `/me` 查看 user_id、telegram_user_id 及偏好。
- `/link <token>` 使用 link_token 绑定已有账户。
- `/set currency <ISO4217>` 更新默认货币。
- `/set timezone <IANA>` 更新时区。
- `/set lang <BCP47>` 更新语言。
- `/cat_add <name>` 创建消费分类（POST /v1/categories，建议带 Idempotency-Key）。
- `/cat_list` 查看分类列表（GET /v1/categories）。
- `/exp_add <amount> <currency> <occurred_at> [category_id] [merchant] [note]` 记一笔消费（POST /v1/expenses，occurred_at 用 UTC ISO8601，amount 最多 6 位小数）。
- `/exp_list [from] [to] [page] [page_size]` 查看消费历史（GET /v1/expenses，按 occurred_at 倒序）。
> 以上四条为 L1 记账接口对应指令，需在 handlers/service 中补充解析并附带 X-User-Id 与随机 Idempotency-Key。

## 6) 常见操作与排障
- 查看日志：`docker compose logs -f bot` 或本地控制台输出。
- 停止/重启：`docker compose restart bot`；本地 `Ctrl+C` 后再 `python -m main`。
- 409 冲突：提示 Telegram 已绑定其他账户，需先在原账户侧解绑（目前最小版未提供 /unlink）。
- 422 校验失败：检查币种/时区/语言是否有效；API 侧会返回 detail。
- API 不通：确认 `API_BASE_URL` 是否含 `/v1`，以及容器内能解析 `api` 主机或外部地址。
