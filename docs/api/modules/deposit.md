# 存款模块 API 设计说明

## 1. 模块概述与边界
- 职责：机构、账户、余额时间序列
- 依赖：user 与 currency；统计/报表依赖账户与余额

## 2. 资源模型
- Institution：name、type（bank/broker/other）
- Account：user_id、institution_id、currency、status
- AccountBalance：account_id、amount、as_of

## 3. 端点一览
| 路径 | 方法 | 用途 | 鉴权/作用域 | 幂等 | 速率限制 | 备注 |
|---|---|---|---|---|---|---|
| /v1/institutions | GET | 机构列表 | read:deposit | 是 | 标准 | 可筛选 type |
| /v1/accounts | POST | 新建账户 | write:deposit | 幂等键 | 严格 | |
| /v1/accounts | GET | 账户列表 | read:deposit | 是 | 标准 | 分页/过滤 |
| /v1/accounts/{id}/balances | GET | 余额历史 | read:deposit | 是 | 标准 | 支持 from/to |
| /v1/accounts/{id}/balances | POST | 写入快照 | write:deposit | 幂等键 | 严格 | (id, as_of) 幂等 |

## 4. 字段与验证规则
- amount：NUMERIC(20,6)；as_of：UTC
- status：active/inactive；currency：ISO 4217

## 5. 错误与冲突场景
- 409 (account_id, as_of) 唯一冲突
- 422 账户或机构不存在

## 6. 示例交互
- GET /v1/accounts?page=1&page_size=20&filter[status]=active
- POST /v1/accounts/{id}/balances 写快照

## 7. 监控指标
- tx_write_latency、snapshot_freshness、balance_backlog

## 8. 变更与兼容
- 余额快照分区策略调整以向后兼容

