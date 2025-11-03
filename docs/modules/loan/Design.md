# 借贷管理模块 详细设计

## 假设与澄清点
- 初期支持等额本息与等额本金；利率按月计；更复杂形态后续扩展。
- 借贷对象可为机构或个人；一笔借贷固定主货币。

### 1. 模块概述
- 职责：借贷合同、还款计划、还款记录、余额与风险视图。
- 依赖：用户、货币；可选依赖存款（还款资金来源）。
- 使用场景：用户录入合同/还款；调度生成到期提醒（可选）。

### 2. 功能设计
- 功能清单
  | 编号 | 名称 | 说明 | 优先级 |
  |---|---|---|---|
  | L-01 | 合同创建 | 金额、币种、利率、期限 | 高 |
  | L-02 | 还款计划 | 生成期数、到期日、本息拆分 | 高 |
  | L-03 | 记录还款 | 期次、本金/利息、费用 | 高 |
  | L-04 | 余额计算 | 截止日期未清余额 | 高 |
  | L-05 | 提前还款 | 局部或全部提前还款 | 中 |
- 核心业务规则
  - 还款计划生成以合同签订日/首次还款日为基准；允许时区偏移。
  - 历史汇率用于跨币种报表展示；主账保持合同币种。
- 异常与补偿策略
  - 金额差异与四舍五入误差：最后一期调整；支持更正/重算。

### 3. 数据逻辑设计（概念层）
- 主要对象
  - Loan(id, user_id, principal, currency, rate_type, rate_value, term_months, start_date)
  - RepaymentSchedule(loan_id, period_no, due_date, principal_due, interest_due)
  - Repayment(loan_id, period_no, principal_paid, interest_paid, paid_at)
  - Counterparty(id, name, type)
- 对象关系
- Loan 1—N RepaymentSchedule 1—N Repayment
- 跨模块数据流
  - 调度模块可根据计划生成提醒；报表汇总调用汇率。

### 4. 模块交互与流程
- 创建合同→生成计划→按期提醒（可选）→记录还款→更新余额。

### 5. 接口说明（结构级，不含OpenAPI）
- 提供接口
  - create_loan(), generate_schedule(), record_repayment(), get_outstanding()
- 权限控制与访问限制
  - 用户隔离；高频查询限流与缓存。
- 幂等性与速率限制
  - 还款录入按（loan_id+period_no+client_token）幂等。

### 6. 日志与监控
- 监控指标：schedule_gen_latency、repayment_write_latency、outstanding_accuracy
- 关键日志点：loan_id、period_no、amounts、method

### 7. 测试与验收标准
- 测试范围：等额本息/本金生成、最后一期差额调整、跨币种展示
- 验收标准：Given 合同 When 生成计划 Then 总额与规则一致
- Mock/隔离：固定汇率、模拟还款导入与异常。

### 8. 模块扩展与未来优化方向
- 浮动利率、罚息、费用模型、贷款重定价与重组

