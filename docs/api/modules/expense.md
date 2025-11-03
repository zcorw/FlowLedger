# 消费模块 API 设计说明

## 1. 模块概述与边界
- 职责：消费记录、分类、统计
- 依赖：user、currency、deposit（支付账户引用）、scheduler（模板记账）

## 2. 资源模型
- Expense：金额/币种/分类/商户/账户/发生时间
- Category：层级或标签式分类

## 3. 端点一览
| 路径 | 方法 | 用途 | 鉴权/作用域 | 幂等 | 速率限制 | 备注 |
|---|---|---|---|---|---|---|
| /v1/expenses | POST | 创建消费 | write:expense | 幂等键 | 严格 | 支持 source_ref 幂等 |
| /v1/expenses | GET | 列表查询 | read:expense | 是 | 标准 | 分页/时间区间 |
| /v1/categories | GET | 分类列表 | read:expense | 是 | 标准 | |
| /v1/categories | POST | 新建分类 | write:expense | 幂等键 | 严格 | (user_id, name) 唯一 |

## 4. 字段与验证规则
- amount >= 0；currency 合法
- occurred_at：UTC；source_ref 可选

## 5. 错误与冲突场景
- 409 分类重名或 source_ref 冲突
- 422 金额为负或时间非法

## 6. 示例交互
- GET /v1/expenses?from=2025-01-01T00:00:00Z&to=2025-02-01T00:00:00Z&sort=-occurred_at
- POST /v1/expenses 带 Idempotency-Key

## 7. 监控指标
- expense_write_latency、dup_dropped_count、stats_latency

## 8. 变更与兼容
- 分类模型从树转标签的迁移策略（保持兼容）

