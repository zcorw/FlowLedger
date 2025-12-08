# Flow-Ledger 文档总览

本目录汇总项目的用户指南、API 说明、SQL 设计、模块设计与部署运维文档，帮助你快速上手与持续迭代。

## 快速开始
- 本地/生产环境搭建：`docs/deploy/environment_setup.md`
- F0 基线（最小可用 API + 基础设施）：`docs/deploy/f0_baseline_setup.md`

## 用户指南
- Telegram Bot 使用指南：`docs/guide/telegram_bot.md`
- 收据上传（OCR）自动记账：`docs/guide/receipt_ocr.md`
- 获取 BOT_TOKEN（BotFather 操作）：`docs/guide/bot_token.md`

## API 说明
- 总览：`docs/api/README.md`
- 模块接口：
  - 货币（currency）：`docs/api/modules/currency.md`
  - 用户（user）：`docs/api/modules/user.md`
  - 存款（deposit）：`docs/api/modules/deposit.md`
  - 消费（expense）：`docs/api/modules/expense.md`
  - 借贷（loan）：`docs/api/modules/loan.md`
  - 定时任务（scheduler）：`docs/api/modules/scheduler.md`

## SQL 说明（PostgreSQL 12+）
- 总览与规范：`docs/sql/README.md`
- 模块 DDL 与说明：
  - 货币 schema：`docs/sql/modules/currency.sql.md`
  - 用户 schema：`docs/sql/modules/user.sql.md`
  - 存款 schema：`docs/sql/modules/deposit.sql.md`
  - 消费 schema：`docs/sql/modules/expense.sql.md`
  - 借贷 schema：`docs/sql/modules/loan.sql.md`
  - 定时任务 schema：`docs/sql/modules/scheduler.sql.md`

## 模块设计（Design）
- 货币：`docs/modules/currency/Design.md`
  - ExchangeRate-API 定时拉取说明：`docs/modules/currency/ExchangeRate-API.md`
- 用户：`docs/modules/user/Design.md`
- 存款：`docs/modules/deposit/Design.md`
- 消费：`docs/modules/expense/Design.md`
- 借贷：`docs/modules/loan/Design.md`
- 定时任务：`docs/modules/scheduler/Design.md`

## 约定与原则（摘）
- 技术栈：Python（FastAPI）、PostgreSQL 12+、Docker、Telegram Bot
- 金额与时间：金额使用 DECIMAL（避免浮点），时间统一 UTC 存储，展示按用户时区
- 一致性与幂等：关键写操作支持 `Idempotency-Key`；触发/任务按业务幂等键去重
- 观测性与安全：结构化日志、指标与追踪；最小权限、加密传输、备份与灾备

如需新增文档或更新导航，请保持上述结构与命名一致，便于快速定位模块与资源。
