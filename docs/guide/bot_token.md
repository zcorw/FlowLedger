# 获取 Telegram BOT_TOKEN 指南

本文介绍如何通过 BotFather 创建机器人并获取/管理 `BOT_TOKEN`，并给出命令配置与安全建议。

## 一、创建机器人并获取 Token

1) 在 Telegram 搜索并打开 `@BotFather`，点击 Start。
2) 发送 `/newbot`，按提示依次输入：
   - 机器人显示名（可包含空格，如 `Flow Ledger`）。
   - 机器人用户名（必须以 `_bot` 结尾，如 `flow_ledger_bot`）。
3) BotFather 将返回一段 `HTTP API token`，形如：
   - `123456789:AA...`（请务必妥善保管，不要公开）。
4) 在项目根目录复制并编辑环境文件：
   - `cp .env.example .env`
   - 在 `.env` 中设置：`BOT_TOKEN=你从BotFather获取的Token`

验证：在 Telegram 打开 `t.me/<你的机器人用户名>`，发送 `/start` 应能收到欢迎消息（在你接入 Bot 代码后）。

## 二、常用管理操作（BotFather）

- 重置 Token：
  - `/revoke`（或：`/mybots` → 选择机器人 → Bot Settings → Edit Token → Revoke & Generate new`）。
  - 旋转后需同步更新部署环境中的 `BOT_TOKEN`。
- 设置命令清单（建议）：
  - `/setcommands` → 选择机器人 → 发送多行命令清单，示例：
    ```
    start - Start the bot
    help - Show help
    me - Show my profile
    link - Link existing account
    unlink - Unlink telegram
    set - Set preferences
    expense - Add an expense
    deposit - Add a deposit
    expenses - List expenses
    deposits - List deposits
    summary - Summary view
    accounts - List accounts
    balance - Balance ops
    fx - Exchange rate
    convert - Convert currency
    remind - Reminders
    stats - Statistics
    export - Export CSV
    ```
  - 说明：BotFather 命令名不支持空格，复杂子命令在交互中提示填写参数即可。
- 私聊/群聊隐私模式：
  - `/setprivacy` → Enable（默认建议启用，群聊仅接收以 `/` 开头的命令）。
  - 若需要在群聊接收自然语言（不推荐），可 Disable，但务必结合白名单/权限控制与限流。

## 三、Webhook 与轮询（概览）

- 轮询（Polling）：
  - 便于本地开发或内网运行；无需公网地址。
- Webhook（生产推荐）：
  - 需公网可达的 HTTPS 地址；配置 `WEBHOOK_URL` 并在服务启动时设置。
  - 通过反向代理（如 Nginx/Caddy）将 `/telegram/webhook` 转发至 Bot 服务。

## 四、安全与合规

- 切勿把 `BOT_TOKEN` 提交到代码仓库或日志；在生产使用 Secret 管理；
- 严格最小权限与最小暴露：API 使用内网地址，Webhook 仅暴露必要路径；
- 定期轮换 Token（`/revoke`）并验证旧 Token 已失效；
- 对敏感日志做脱敏；为写操作设置幂等键，避免重复提交。

## 五、常见问题

- 无法接收消息：确认 Token 正确、服务已启动、网络可达；Webhook 模式检查证书/反代；
- 命令不显示：更新了 `/setcommands` 后稍等片刻或重启客户端；
- 误泄露 Token：立即通过 `/revoke` 旋转 Token，并尽快在所有环境中更新。

