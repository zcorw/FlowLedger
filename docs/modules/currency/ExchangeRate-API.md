# ExchangeRate-API 手动拉取与入库说明
本说明改为“按需手动拉取汇率”，由页面触发或脚本手动执行，服务于货币模块（currency）。

## 目标
- 按当前资产中的货币作为 base，拉取 base→CNY 汇率并入库到 `currency.exchange_rates`。
- 避免定时任务带来的无效请求，前端手动触发即可完成更新。

## 触发方式
- 接口触发：`POST /v1/exchange-rates/sync?target=CNY`（target 可选，默认 CNY）。
- 命令触发：`cd api && python -m app.tasks.fetch_fx`。

## 拉取策略
- base 列表：从 `deposit.financial_products` 的“当前资产”货币中去重得到。
- Provider 调用：对每个 base 请求 `GET https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{base}.json`。
- 入库：仅写入 base→CNY 的当日汇率，使用 `INSERT ... ON CONFLICT DO UPDATE` 幂等更新。

## 失败与降级
- 请求失败：该 base 不入库，返回结果中记录 `missing`。
- 不影响其它 base 的入库。
