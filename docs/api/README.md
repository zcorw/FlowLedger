# Flow-Ledger API 说明书总览

## 项目与目标
Flow-Ledger 提供面向个人的多币种资产管理 API。核心场景涵盖：货币与汇率、用户/偏好、存款账户与余额、消费记录与分类、借贷合同与还款、定时任务与回执（自动记账）。

- 技术与风格：后端 Python（FastAPI/Flask）+ Docker；DB 为 PostgreSQL；前端交互为 Telegram Bot
- 全局规则：金额以 DECIMAL 精度表示；时间统一 UTC，ISO 8601 格式；REST + OpenAPI 3.1

## 模块边界与资源
- 货币（currency）：货币清单、历史汇率、统一换算、快照导出
- 用户（user）：注册/登录、偏好（默认货币、时区）、Telegram 绑定
- 存款（deposit）：机构、账户、余额时间序列
- 消费（expense）：消费记录 CRUD、分类、统计
- 借贷（loan）：合同、计划、还款、余额
- 定时任务（scheduler）：任务、实例、提醒、回执（自动记账触发）

## 全局 API 规范
- 路径与方法：REST 风格，`/v1/...` 前缀；资源名使用复数；语义化 HTTP 方法
- 鉴权：OAuth2 Bearer（JWT）
  - flows：`authorization_code`（交互式），`client_credentials`（服务间）
  - 作用域示例：`read:expense`、`write:loan`、`read:currency`、`write:scheduler`
- 幂等：所有非幂等写操作支持 `Idempotency-Key` 请求头；服务端基于业务唯一键或请求摘要去重并在响应头回显
- 分页：
  - 页码分页：`page`、`page_size`；响应返回 `total`, `page`, `page_size`, `has_next`
  - 游标分页：`cursor` 可选；长表推荐
- 过滤与排序：`filter[字段]=值`、`sort=field1,-field2`；时间区间：`from`/`to`（UTC，ISO8601）
- 金额/货币：`amount`（字符串或数值，保留精度）、`currency`（ISO 4217）
- 时间：所有 `datetime` 使用 `format: date-time`（UTC）
- 错误模型：统一 `code`（字符串）/`message`/`details`（任意 JSON）；HTTP 状态码与业务错误码双层治理
- 速率限制：响应头 `X-RateLimit-Limit`、`X-RateLimit-Remaining`、`X-RateLimit-Reset`
- 可观测性：`X-Request-Id` 透传；结构化错误；关键操作记录审计（登录、记账、借贷变更、定时回执）
- 兼容性：版本化路径 `/v1`；新增字段默认可选；严格避免破坏性删除
- 国际化：金额/货币/时区严格标准化；多语言字段仅在必要处暴露，优先标准化枚举

## 需求映射（示例）
| 需求 | 模块 | 核心资源/端点 |
|---|---|---|
| 多币种与统一换算、历史汇率 | currency | GET /currencies, GET /exchange-rates, POST /convert |
| 用户为中心、偏好/时区 | user | GET /users/me, PATCH /users/me/preferences, POST /users/link-telegram |
| 存款账户与余额历史 | deposit | POST /accounts, GET /accounts/{id}/balances |
| 消费记录与统计 | expense | POST /expenses, GET /expenses/stats |
| 借贷计划与台账 | loan | GET /loans/{id}/schedule, POST /loans/{id}/repayments |
| 定时提醒与自动记账 | scheduler | POST /jobs, GET /job-runs, POST /confirmations |

## 安全与权限矩阵（示例）
| Scope | 端点（节选） | 角色（示例） |
|---|---|---|
| read:currency | GET /v1/currencies, GET /v1/exchange-rates | 所有 |
| write:expense | POST /v1/expenses | 用户 |
| read:deposit | GET /v1/accounts, GET /v1/accounts/{id}/balances | 用户 |
| write:loan | POST /v1/loans, POST /v1/loans/{id}/repayments | 用户 |
| write:scheduler | POST /v1/jobs, POST /v1/confirmations | 用户或系统任务 |

## 错误码总表（示例）
- 400 invalid_request 参数格式错误或缺失
- 401 unauthorized 鉴权失败或 token 过期
- 403 forbidden 无访问该资源的权限
- 404 not_found 资源不存在
- 409 conflict 幂等冲突或业务唯一性冲突
- 422 unprocessable_entity 校验失败（金额/日期/状态不合法）
- 429 rate_limited 触达限额
- 5xx server_error 服务异常

## 可观测性与调试
- 始终传入/回显 `X-Request-Id`，用于链路追踪
- 幂等重放：同一 `Idempotency-Key` 在业务窗口内允许重放读取上次结果
- 安全红线：禁止在错误详情中返回敏感数据；采用最小化日志策略

## 自测清单
- OpenAPI 3.1 校验通过（spectral/openapi-cli）
- 示例请求具备幂等头与 UTC 时间
- 速率限制头正常回显
- 金额精度与货币代码符合规范

