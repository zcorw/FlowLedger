# 消费管理模块 详细设计

## 假设与澄清点
- 消费记录为正值金额，方向为“支出”；退款以负值或单独类型表示。
- 可选商户、类别与标签；支持附加账户引用（支付来源）。

### 1. 模块概述
- 职责：消费记录、分类与商户管理、分析与报表、与调度联动。
- 依赖：用户、货币、存款（支付账户引用）、调度（自动记账）。
- 使用场景：用户录入、导入；调度确认后自动创建。

### 2. 功能设计
- 功能清单
  | 编号 | 名称 | 说明 | 优先级 |
  |---|---|---|---|
  | E-01 | 记录消费 | 金额/币种/类别/商户/账户/备注 | 高 |
  | E-02 | 分类管理 | 树形或标签化类别 | 中 |
  | E-03 | 商户管理 | 归一化商户信息 | 中 |
  | E-04 | 分摊/合并 | 多人/多账户分摊 | 低 |
  | E-05 | 报表 | 分类/时间/商户多维分析 | 中 |
- 核心业务规则
  - 金额 DECIMAL(20,6)；展示货币=用户默认货币（按历史汇率）。
  - 允许从“模板”快速创建（与调度模块复用）。
- 异常与补偿策略
  - 重复录入：client_token 幂等；支持撤销/更正。

### 3. 数据逻辑设计（概念层）
- 主要对象
  - Expense(id, user_id, amount, currency, category_id, merchant_id, paid_account_id?, occurred_at, note, tags[])
  - Category(id, name, parent_id?)
  - Merchant(id, name, normalized_name)
- 对象关系
  - Expense N—1 Category/Merchant；可引用支付账户（存款模块）。
- 跨模块数据流
  - 调度模块根据模板创建 Expense；报表调用汇率转换与用户偏好。

### 4. 模块交互与流程
- 用户通过 Bot 录入→后端校验→创建 Expense→返回摘要。
- 调度确认→后端读取模板→创建 Expense→回写确认结果。

### 5. 接口说明（结构级，不含OpenAPI）
- 提供接口
  - create_expense(), update_expense(), list_expenses(), stats_by_category()
- 权限控制与访问限制
  - 用户仅操作自身；敏感操作审计与限流。
- 幂等性与速率限制
  - `Idempotency-Key` 或 client_token；模板创建按（task_id+period_key）幂等。

### 6. 日志与监控
- 监控指标：expense_write_latency、dup_dropped_count、stats_latency
- 关键日志点：expense_id、amount、currency、category、source(template/manual)

### 7. 测试与验收标准
- 测试范围：历史汇率换算、模板记账幂等、退款/撤销
- 验收标准：Given 模板确认 When 创建 Then 产生单一消费
- Mock/隔离：隔离汇率模块（固定汇率）与调度回调。

### 8. 模块扩展与未来优化方向
- 自动分类（规则/ML）、预算与预警、收据识别（OCR）

