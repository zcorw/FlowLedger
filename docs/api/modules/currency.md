# 货币模块 API 设计说明

## 1. 模块概述与边界
- 职责：货币清单、历史汇率、统一换算、快照导入
- 上游：外部汇率源；下游：消费/存款/借贷统计展示
- 安全：读为主。本阶段不区分普通用户与管理员（见第 9 节写接口说明），后续可引入 RBAC 收紧权限。

## 2. 资源模型
- Currency：主键 `code`（ISO 4217）
- ExchangeRate：主键 `(base, quote, date)`；维度：日期、币对
- ConvertRequest：金额换算请求（from、to、date）

## 3. 端点一览
| 路径 | 方法 | 用途 | 幂等 | 备注 |
|---|---|---|---|---|
| /v1/currencies | GET | 货币清单列表/搜索 | n/a | 支持分页/过滤 |
| /v1/currencies/{code} | GET | 货币详情 | n/a | 404 不存在 |
| /v1/exchange-rates | GET | 历史汇率查询 | n/a | 支持 base/quote/date 区间 |
| /v1/convert | POST | 金额换算 | 支持 | 请求体可批量 |

## 4. 字段与验证规则
- code：长度=3，A-Z；
- rate：>0，精度 NUMERIC(20,10)；
- 时间：`date`/`at` 使用 UTC ISO8601，不允许本地时区。

## 5. 错误与冲突场景
- 422 非法币种或日期
- 404 当日无汇率且禁止回退
- 429 高频批量换算
- 503 上游不可用（本地无可用缓存时）

## 6. 示例交互
- GET /v1/exchange-rates?base=USD&quote=CNY&date=2025-01-15
- POST /v1/convert 批量多笔金额

## 7. 监控指标
- rate_fetch_success、rate_freshness_seconds、convert_latency_ms

## 8. 变更与兼容
- 新增币种字段（如符号/名称本地化）按可选字段发布

## 9. 货币清单管理接口（当前阶段不区分权限）

说明：本阶段暂不区分“普通用户/管理员”，以下写接口对使用者统一开放；后续引入 RBAC 时可收紧为管理员专用（建议 Scope：`write:currency_admin`）。

- POST `/v1/currencies`
  - 用途：创建或幂等更新单个货币（Upsert）。
  - 幂等：以 `code` 为业务唯一键；支持 `Idempotency-Key` 请求头。
  - 请求体：`{ code, name, symbol?, scale }`（code=ISO4217，scale=0..6）
  - 响应：201（新建）或 200（更新）；422 校验失败；409 业务冲突（可选）。

- PATCH `/v1/currencies/{code}`
  - 用途：更新名称/符号/scale。
  - 请求体：`{ name? , symbol? , scale? }`
  - 响应：200；404 不存在。

- PUT `/v1/currencies/bulk`
  - 用途：批量导入/更新（Upsert）。
  - 请求体：数组（长度建议 ≤1000），每项同 POST 规则。
  - 响应：207 Multi-Status 或 200，返回逐项成功/失败明细。

- DELETE `/v1/currencies/{code}`（可选，不推荐）
  - 说明：存在外键引用风险，不建议物理删除；默认不提供删除接口。

- 列表/搜索补充（只读）
  - GET `/v1/currencies` 过滤：`code` 精确、`q`（name/symbol 模糊）、`page/page_size`、`sort=code,-name`。
  - GET `/v1/currencies/{code}` 404 不存在。

- 与 SQL 约束对齐
  - 表：`currency.currencies(code, name, symbol, scale, created_at, updated_at)`；
  - 约束：`code` 主键；`scale` 0..6；更新触发器自动刷新 `updated_at`。

