# 存款管理模块 详细设计

## 假设与澄清点
- 存款账户可对应银行/券商/平台；一账户绑定一种主货币。
- 账户间转账作为两条对向交易记录体现（或未来引入双重记账）。

### 1. 模块概述
- 职责：账户与余额管理、存取款记录、跨机构资产汇总。
- 依赖：货币模块（汇率换算）、用户模块（权限）。
- 使用场景：用户录入、导入、对账任务。

### 2. 功能设计
- 功能清单
  | 编号 | 名称 | 说明 | 优先级 |
  |---|---|---|---|
  | D-01 | 账户管理 | 新增/停用/标签/主货币 | 高 |
  | D-02 | 交易记录 | 存入/取出/转账（双向） | 高 |
  | D-03 | 余额快照 | T 日或月末快照 | 中 |
  | D-04 | 汇总报表 | 多币种资产统一计算 | 高 |
- 核心业务规则
  - 账户主货币固定；展示时按用户默认货币转换。
  - 转账：源账户负向、目标账户正向，幂等键防重放。
- 异常与补偿策略
  - 重复入账/对账差异：提供撤销/更正记录，保留审计。

### 3. 数据逻辑设计（概念层）
- 主要对象
  - Institution(id, name, type)
  - DepositAccount(id, user_id, institution_id, currency, status)
  - DepositTransaction(id, account_id, type[in/out/transfer], amount, currency, occurred_at)
  - BalanceSnapshot(account_id, amount, currency, as_of)
- 对象关系
  - Institution 1—N DepositAccount，DepositAccount 1—N DepositTransaction
- 跨模块数据流
  - 报表需调用汇率模块；与消费/借贷合并计算净资产。

### 4. 模块交互与流程
- 记账：Bot 输入→后端校验→写交易→更新余额（派生）→返回。
- 对账：导入记录→对齐账户→入库→生成差异与建议。

### 5. 接口说明（结构级，不含OpenAPI）
- 提供接口
  - create_account(), record_transaction(), transfer(), list_accounts()
- 权限控制与访问限制
  - 用户仅访问自己的账户；敏感字段审计。
- 幂等性与速率限制
  - 交易写入按 client_token 幂等；转账需两边一致性。

### 6. 日志与监控
- 监控指标：tx_write_latency、transfer_consistency、snapshot_freshness
- 关键日志点：account_id、tx_id、amount、currency、balance_after

### 7. 测试与验收标准
- 测试范围：跨币种账户展示、转账双向一致、撤销与更正
- 验收标准：Given 转账 When 记账 Then 两侧余额一致
- Mock/隔离：模拟导入数据源与并发场景，验证幂等。

### 8. 模块扩展与未来优化方向
- 引入双重记账、自动对账、外部数据源对接（Open Banking）

