# 货币模块 API 设计说明

## 1. 模块概述与边界
- 职责：货币清单、历史汇率、统一换算、快照导出
- 上游：外部汇率源；下游：消费/存款/借贷统计展示
- 安全：只读为主；管理接口（如导入）受限于管理员

## 2. 资源模型
- Currency：主键 `code`（ISO 4217）
- ExchangeRate：主键 `(base, quote, date)`，重要维度：日期、币对
- ConvertRequest：批量金额换算请求（from、to、at）

## 3. 端点一览
| 路径 | 方法 | 用途 | 鉴权/作用域 | 幂等 | 速率限制 | 备注 |
|---|---|---|---|---|---|---|
| /v1/currencies | GET | 列表/搜索 | read:currency | 是 | 标准 | 支持分页/过滤 |
| /v1/currencies/{code} | GET | 详情 | read:currency | 是 | 标准 | 404 不存在 |
| /v1/exchange-rates | GET | 历史汇率 | read:currency | 是 | 标准 | 支持 from/to |
| /v1/convert | POST | 批量换算 | read:currency | 幂等键 | 较严 | 请求体金额数组 |

## 4. 字段与验证规则
- code：长度 3、A-Z；rate：>0、精度 NUMERIC(20,10)
- 时间：`at`/`date` 为 UTC ISO8601；不允许本地时区

## 5. 错误与冲突场景
- 422 非法币种或日期；404 当日无汇率且禁止回退时
- 429 高频批量换算；503 上游不可用（回退缓存）

## 6. 示例交互
- GET /v1/exchange-rates?base=USD&quote=CNY&date=2025-01-15
- POST /v1/convert 批量多笔金额

## 7. 监控指标
- rate_fetch_success、rate_freshness_seconds、convert_latency_ms

## 8. 变更与兼容
- 新增币种字段（如符号/名称本地化）按可选字段发布

