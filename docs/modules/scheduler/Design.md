# 定时通知任务模块 详细设计

## 假设与澄清点
- 调度时间基于用户时区计算，落库时统一存 UTC。
- 每个任务在一个“周期窗口”仅允许一个有效实例；确认动作幂等。
- 默认通知渠道为 Telegram；后续可扩展其他渠道。
- 自动记账目前仅支持“消费”创建（Expense），未来可扩展到还款等。

### 1. 模块概述
- 职责：周期提醒、到期生成提醒事件、用户确认后自动创建消费记录；支持跳过/延期/取消当期。
- 依赖：用户（时区/权限）、货币（模板金额展示换算）、消费（创建记录）。
- 使用场景：用户创建任务、系统调度扫描、用户在 Bot 中确认。

### 2. 功能设计
- 功能清单
  | 编号 | 名称 | 说明 | 优先级 |
  |---|---|---|---|
  | S-01 | 任务管理 | 新增/启用/暂停/归档 | 高 |
  | S-02 | 调度规则 | 每日/每周/每月/自定义 Cron | 高 |
  | S-03 | 提前提醒 | T-提前量下发消息 | 中 |
  | S-04 | 确认处理 | 完成/跳过/稍后提醒/取消本期 | 高 |
  | S-05 | 自动记账 | 完成后创建消费（模板） | 高 |
  | S-06 | 错过补发 | catch-up、下期自动滚动 | 中 |
- 核心业务规则
  - 周期窗口键 period_key = f(task_id, window_start_end_by_timezone)。
  - 自动记账幂等：幂等键 = (task_id + period_key)。
  - 任务状态: 启用/暂停/归档；实例状态：待提醒/已提醒/已确认/已跳过/延期。
- 异常与补偿策略
  - 发送失败重试；长延迟告警；人工补发与任务恢复。
  - 确认重复回调：按幂等键拒绝重复入账。

### 3. 数据逻辑设计（概念层）
- 主要对象
  - ScheduleTask(id, user_id, name, description, rule, first_run_at, advance_minutes, channel, status)
  - ExpenseTemplate(task_id, amount, currency, category_id, merchant, account_id?, note, tags[])
  - ReminderEvent(id, task_id, period_key, scheduled_at, sent_at?, status)
  - ConfirmationEvent(id, task_id, period_key, action[complete/skip/snooze/cancel], confirmed_at, idempotency_key, payload)
- 对象关系
  - ScheduleTask 1—1 ExpenseTemplate；ScheduleTask 1—N ReminderEvent/ConfirmationEvent
- 跨模块数据流
  - 完成→创建 Expense（expense 模块）→返回结果→写确认事件。

### 4. 模块交互与流程
- 扫描到期任务→生成/更新 ReminderEvent→下发 Telegram 消息（按钮：完成/跳过/稍后/取消）→用户点击→回调携带 period_key 与 idempotency_key→后端校验→根据模板创建 Expense→返回结果并更新下期。

### 5. 接口说明（结构级，不含OpenAPI）
- 提供接口
  - create_task(), update_task(), pause_task(), resume_task(), archive_task()
  - list_due_tasks(now), handle_callback(task_id, period_key, action, idempotency_key)
- 被调用能力
  - expense.create_from_template(task_id, period_key)
- 权限控制与访问限制
  - 用户隔离；任务变更操作审计；回调防重放（签名/时效）。
- 幂等性与速率限制
  - 以 (task_id + period_key) 控制自动记账与回调处理幂等。

### 6. 日志与监控
- 监控指标：due_backlog、reminder_send_success、callback_latency、auto_post_success
- 关键日志点：task_id、period_key、action、result、idempotency_key

### 7. 测试与验收标准
- 测试范围：跨时区周期计算、错过补发、确认幂等、自动记账成功/失败回滚
- 验收标准：Given 周期到期 When 完成 Then 仅生成一条消费并更新下期
- Mock/隔离：模拟 Bot 回调、固定时区与时间窗口用例。

### 8. 模块扩展与未来优化方向
- 多渠道通知、复杂排除日历（节假日/工作日）、批量任务、预算联动与异常消费拦截（提醒后升级为告警）

