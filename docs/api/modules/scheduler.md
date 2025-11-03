# 定时任务模块 API 设计说明

## 1. 模块概述与边界
- 职责：任务、实例、提醒、回执；确认“完成”后自动创建消费
- 依赖：user（时区）、expense（自动记账）、currency（展示换算）

## 2. 资源模型
- Job：name/rule/first_run_at/advance/channel/status
- JobRun：job_id/period_key/scheduled_at/sent_at/status
- Confirmation：job_run_id/action/confirmed_at/idempotency_key

## 3. 端点一览
| 路径 | 方法 | 用途 | 鉴权/作用域 | 幂等 | 速率限制 | 备注 |
|---|---|---|---|---|---|---|
| /v1/jobs | POST | 创建任务 | write:scheduler | 幂等键 | 严格 | |
| /v1/jobs | GET | 任务列表 | read:scheduler | 是 | 标准 | |
| /v1/job-runs | GET | 到期实例 | read:scheduler | 是 | 标准 | 支持 from/to/status |
| /v1/confirmations | POST | 提交回执 | write:scheduler | 幂等键 | 严格 | 触发自动记账 |

## 4. 字段与验证规则
- action：complete/skip/snooze/cancel
- period_key：例如 YYYY-MM；scheduled_at/sent_at/confirmed_at 为 UTC

## 5. 错误与冲突场景
- 409 (job_id, period_key) 或 (job_run_id, idempotency_key) 冲突
- 422 规则非法或时间不合法

## 6. 示例交互
- GET /v1/job-runs?status=pending&to=2025-01-01T00:00:00Z
- POST /v1/confirmations 完成后自动创建消费

## 7. 监控指标
- due_backlog、reminder_send_success、callback_latency、auto_post_success

## 8. 变更与兼容
- 引入节假日排除与复杂日历保持字段可选

