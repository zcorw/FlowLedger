# ExchangeRate-API 定时拉取与入库需求说明

本说明定义“每天在指定时间通过 ExchangeRate-API 拉取汇率并入库”的需求与实施要点，服务于货币管理模块（currency）。

## 目标
- 每日按指定时间（可配置）拉取清单内货币的当日汇率，保存到 `currency.exchange_rates`；
- 支持幂等、降级与观测性，避免重复入库与脏数据。

## 调度与配置
- 触发：由调度模块（scheduler）执行定时任务，统一使用 UTC；如需本地时区可由调度侧转换。
- 环境变量（建议）：
  - `FX_PROVIDER=exchangerate-api`
  - `EXCHANGE_RATE_API_KEY=<REQUIRED>`
  - `FX_SYNC_AT=09:00`（每日执行时间）
  - `FX_BASES=USD`（逗号分隔的基准货币列表，默认 USD）
  - `FX_TIMEOUT_MS=5000`、`FX_MAX_RETRIES=3`（指数退避）
  - `FX_ALLOW_FALLBACK=true`、`FX_MAX_STALE_DAYS=7`

## 拉取策略
- 清单：从 `currency.currencies` 读取货币代码集合 `codes`；
- Provider 调用：对每个 `base ∈ FX_BASES` 调用：
  - `GET https://v6.exchangerate-api.com/v6/<API_KEY>/latest/<base>`
  - 从响应的 `conversion_rates` 取出 `quote ∈ codes - {base}` 的比率；忽略 provider 不支持的币种；
- 请求合并：一次调用覆盖一个 `base` 的全量 `quote`，配额友好。

## 入库规则（PostgreSQL）
- 目标表：`currency.exchange_rates`
  - 字段：`base_code`, `quote_code`, `rate_date`（UTC 自然日）, `rate`（NUMERIC(20,10) > 0）, `source`, `created_at`, `updated_at`
  - 唯一键：`(base_code, quote_code, rate_date)`；更新触发器维护 `updated_at`
- 幂等策略：`INSERT ... ON CONFLICT DO UPDATE`；`source='exchangerate-api'`
- 日期对齐：以执行时的 UTC 日期作为 `rate_date`；如 provider 返回时间戳同日也可直接使用。

## 失败与降级
- 超时/5xx：按 `FX_MAX_RETRIES` 重试；仍失败则：
  - 若 `FX_ALLOW_FALLBACK=true` 且最近可用数据在 `FX_MAX_STALE_DAYS` 内，则保留旧值并打“stale”标记用于响应（不覆盖当日表）。
  - 记录失败明细（base/quote/错误码），不阻塞其他对写入。
- 部分缺失：对不支持的 `quote` 跳过并记录；
- 指标与日志：`rate_fetch_success`、`rate_freshness_seconds`、`convert_latency_ms`；结构化日志包含 `base/quote/source/error_code`。

## 可选：三角换汇
- 当 `A→B` 缺失，但存在 `A→USD` 与 `USD→B` 时，可派生 `A→B = (A→USD) × (USD→B)`；
- 入库时 `source='exchangerate-api:derived'`，可通过开关启用。

## 作业摘要
- 每次执行结束，输出：
  - 成功写入条数、跳过条数、不支持条数、失败条数；
  - 当次使用的 `base` 列表与清单大小；
  - 最大 `stale_days` 与是否触发降级。

## 与换算/查询的协作
- `GET /v1/exchange-rates` 与 `POST /v1/convert`：
  - 当日命中直接使用；
  - 当日缺失时按“最近可用且不超过 `FX_MAX_STALE_DAYS`”回退，响应中建议回显 `effective_date` 与 `stale/stale_days`。

