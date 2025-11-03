# Flow-Ledger Telegram Bot 使用指南

> 目标：帮助最终用户通过 Telegram Bot 完成日常记账、查询和提醒操作，并给出基础的管理员部署与故障排查要点。

## 1. 开始使用

- 搜索并启动机器人：在 Telegram 中搜索你部署的机器人（示例：`@FlowLedgerBot`），点击 Start（或发送 `/start`）。
- 语言与欢迎信息：首次进入显示欢迎与语言选择（如 `zh-CN`/`en`），可随时通过 `/set lang zh-CN` 切换。
- 账号绑定：机器人基于 Telegram 账户识别用户。若需与既有账户绑定，使用 `/link <link_token>`（详见“账号绑定”）。

## 2. 账号与偏好

- `/me`：查看当前用户信息与偏好（默认货币、时区、语言）。
- `/link <link_token>`：绑定既有账户（若已绑定将返回冲突提示）。不带 `link_token` 时，按 Telegram 用户 ID 幂等创建/绑定。
- `/unlink`：解绑 Telegram（需要二次确认）。解绑后将无法再接收提醒与快速记账。
- `/set currency <ISO4217>`：设置默认货币，如 `/set currency CNY` 或 `/set currency USD`。
- `/set timezone <IANA>`：设置时区，如 `/set timezone Asia/Shanghai`。所有输入时间默认按该时区解析存储为 UTC。
- `/set lang <BCP47>`：设置语言，如 `/set lang zh-CN`。

说明：以上操作对应用户模块与偏好更新（见 API：`/v1/users/me`、`/v1/users/me/preferences`、`/v1/users/link-telegram`）。

## 3. 快速记账（消费/存款）

支持命令式与自然语法两种方式，所有金额精度严格保留为 DECIMAL，时间统一存储为 UTC。

基础命令：
- `/expense add <amount> <currency> [#category] [note...] [@yyyy-mm-dd HH:MM]`
  - 示例：`/expense add 35.8 CNY #food 星巴克拿铁 @2025-11-01 08:30`
  - 不填时间则使用当前时间（按你设置的时区）。
- `/deposit add <amount> <currency> to <account> [note...] [@yyyy-mm-dd]`
  - 示例：`/deposit add 5000 CNY to 招行工资卡 @2025-10-31`（记一笔入账/充值）。

自然语法（可直接发送消息）：
- `35.8 CNY 星巴克 #coffee @2025-11-01 08:30`
- `-120 USD uber #transport`（负号表示支出，可省略 `expense` 关键字）
- `+200 EUR 退款 #refund`（正号表示收入/入账）

确认与撤销：
- 机器人会回显解析结果并弹出确认按钮；确认后写入成功返回记录编号。
- `/undo` 撤销上一笔成功写入的消费/入账（时间窗口内）。

查询与管理：
- `/expenses [today|week|month|yyyy-mm] [#category]`：查询消费明细。
- `/deposits [today|week|month|yyyy-mm]`：查询入账明细。
- `/summary [today|week|month|yyyy-mm] [<currency>]`：概要汇总（按默认或指定货币）。

## 4. 账户与余额

- `/accounts`：列出账户与基础信息。
- `/account add <name> <currency> [institution]`：新增账户。
- `/balance set <account> <amount> <currency> [@yyyy-mm-dd]`：设置账户余额（期初/校正）。
- `/balance show <account> [period]`：查看余额时间序列（可按日/周/月）。

说明：账户余额用于净资产计算与时间序列分析，新增/校正会生成一条余额快照。

## 5. 货币与换算

- `/fx <from> <to> [@yyyy-mm-dd]`：查看某日汇率，如 `/fx USD CNY @2025-10-31`。
- `/convert <amount> <from> to <to> [@yyyy-mm-dd]`：金额换算，如 `/convert 100 USD to CNY`。
- `/currencies`：支持的货币清单。

说明：系统使用统一汇率源，支持历史汇率查询与快照。计算与展示按你设置的默认货币或命令参数决定。

## 6. 定时提醒与自动记账

- `/remind add <title> <amount?> <currency?> every <cron|rule> at <HH:MM> [#category]`：新增提醒。
  - 示例：`/remind add 房租 3000 CNY every monthly at 09:00 #rent`（每月 9:00 提醒）。
- `/remind list`：查看提醒/任务列表与状态。
- `/remind on <id>`、`/remind off <id>`：开启/关闭提醒。
- 回执交互：到点后机器人会推送提醒卡片，可一键“已支付/记录消费”。

说明：提醒的默认推送渠道为 Telegram，任务与实例可在历史中查询，关键字段含 `channel=telegram`。

## 7. 导出与统计

- `/stats [period] [#category]`：消费统计（分类、标签、趋势）。
- `/export csv [period]`：导出 CSV（机器人将回传文件）。

## 8. 常见问题（FAQ）

- 时间与时区：若未设置时区，系统会默认使用 `UTC`。建议通过 `/set timezone Asia/Shanghai` 设置后再记账。
- 幂等与重复提交：网络抖动导致重复点击确认时，服务端会按业务唯一键/幂等键去重。
- 冲突 409：重复绑定同一 Telegram 账户或目标记录唯一性冲突时，机器人会给出冲突提示与解决建议。
- 校验 422：金额、日期、货币或语法不合法时，返回具体的字段校验错误并给出正确示例。
- 速率限制：高频操作会触达限额，稍后重试或放缓操作节奏。

## 9. 隐私与安全

- 数据最小化：仅存储与记账相关的必要信息。
- 传输安全：客户端与服务端均使用 TLS；机器人不回显敏感信息。
- 账号控制：可随时 `/unlink` 解绑或 `/set lang`、`/set timezone` 调整偏好。

## 10. 故障排查（用户侧）

- 无响应或超时：检查网络状态，稍后重试；若持续失败，请联系管理员。
- 命令无效：发送 `/help` 获取当前支持的命令与示例。
- 记录缺失：使用 `/expenses` 或 `/deposits` 按时间过滤；确认是否已撤销或过滤条件不匹配。

## 11. 管理员部署速览（选读）

> 若你负责部署/运维机器人，以下为最小可行步骤（与后端 API、PostgreSQL 协同）。

- 创建 Bot：在 Telegram 中联系 `@BotFather`，创建机器人并获取 `BOT_TOKEN`。
- 运行方式：
  - 轮询（Polling）：适合快速本地/小规模部署。
  - Webhook：生产推荐，需公网可达 URL 与证书（或可信反向代理）。
- 必要环境变量（示例）：
  - `BOT_TOKEN`：BotFather 下发的 token。
  - `API_BASE_URL`：后端 API 根路径，如 `https://api.example.com/v1`。
  - `DEFAULT_LANG`、`DEFAULT_TIMEZONE`、`DEFAULT_CURRENCY`：缺省偏好。
  - `WEBHOOK_URL`（可选）：启用 webhook 时配置。
  - `LOG_LEVEL`、`REDIS_URL`（可选）：日志与会话/限流存储。
- 部署示例（Docker，伪示例）：
  - `docker run -e BOT_TOKEN=xxx -e API_BASE_URL=https://api.example.com/v1 ghcr.io/yourorg/flow-ledger-bot:latest`
- 与后端对齐：
  - 用户绑定：`POST /v1/users/link-telegram`，支持 `link_token` 与基于 `telegram_user_id` 的幂等绑定。
  - 偏好更新：`PATCH /v1/users/me/preferences`。
  - 汇率/货币：`GET /v1/currencies`、`GET /v1/exchange-rates`、`POST /v1/convert`。
  - 记账与查询：对应 `expense`、`deposit`、`loan`、`scheduler` 模块的 CRUD/查询端点。
- 可靠性：
  - 幂等等幂：为所有写操作设置 `Idempotency-Key`；失败重试需可安全重放。
  - 观测性：透传/记录 `X-Request-Id`，区分用户维度日志与错误分级。
  - 速率/限流：对 command 与自然语法解析各自限流，避免滥用。

## 12. 命令速查表

- `/start` 欢迎与初始化
- `/help` 帮助与示例
- `/me` 查看账户与偏好
- `/link <token>` 绑定既有账户
- `/unlink` 解绑 Telegram
- `/set currency <ISO4217>` 设置默认货币
- `/set timezone <IANA>` 设置默认时区
- `/set lang <BCP47>` 设置语言
- `/expense add ...` 记一笔消费
- `/deposit add ...` 记一笔入账/充值
- `<自然语法>` 直接发消息快速记账
- `/expenses ...` 消费查询
- `/deposits ...` 入账查询
- `/summary ...` 汇总视图
- `/accounts` 查看账户
- `/balance set/show ...` 余额管理
- `/fx ...`、`/convert ...` 汇率与换算
- `/remind add/list/on/off ...` 定时提醒
- `/stats ...` 统计
- `/export csv ...` 导出

—— 以上内容覆盖大多数日常记账与查询需求；如需扩展（如借贷、预算、共享账本），可在同一交互范式下新增命令与卡片式确认。

