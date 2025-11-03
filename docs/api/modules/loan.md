# 借贷模块 API 设计说明

## 1. 模块概述与边界
- 职责：合同、还款计划、还款记录、余额与风险
- 依赖：user、currency；与 scheduler 可集成到期提醒

## 2. 资源模型
- Loan：principal/currency/rate/term/status
- RepaymentSchedule：period_no/due_date/principal/interest
- Repayment：paid_at/principal_paid/interest_paid/fee_paid

## 3. 端点一览
| 路径 | 方法 | 用途 | 鉴权/作用域 | 幂等 | 速率限制 | 备注 |
|---|---|---|---|---|---|---|
| /v1/loans | POST | 创建合同 | write:loan | 幂等键 | 严格 | |
| /v1/loans | GET | 合同列表 | read:loan | 是 | 标准 | |
| /v1/loans/{id} | GET | 合同详情 | read:loan | 是 | 标准 | |
| /v1/loans/{id}/schedule | GET | 还款计划 | read:loan | 是 | 标准 | |
| /v1/loans/{id}/repayments | POST | 记录还款 | write:loan | 幂等键 | 严格 | (loan,period) 幂等 |

## 4. 字段与验证规则
- principal >= 0；rate_value >= 0；term_months > 0
- status：active/closed/defaulted

## 5. 错误与冲突场景
- 409 重复 period_no 写入；422 金额/利率非法
- 404 贷款不存在

## 6. 示例交互
- GET /v1/loans/{id}/schedule
- POST /v1/loans/{id}/repayments 带幂等键

## 7. 监控指标
- schedule_gen_latency、repayment_write_latency、outstanding_accuracy

## 8. 变更与兼容
- 状态枚举扩展以 CHECK 约束实现，便于演进

