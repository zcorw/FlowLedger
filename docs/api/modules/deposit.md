# 存款/资产模块 API 说明

## 1. 概览
- 职责：管理用户绑定的金融机构、机构下的金融产品，以及产品余额快照。
- 依赖：用户身份（`"user".users`），币种（`currency.currencies`）。产品金额与余额快照通过触发器保持同步。

## 2. 资源模型
- Institution：`id`，`user_id`，`name`，`type`(`bank|broker|other`)，`created_at/updated_at`。同一用户下 `name` 唯一。
- FinancialProduct：`id`，`institution_id`，`name`，`product_type`(`deposit|investment|securities|other`)，`currency`，`status`(`active|inactive|closed`)，`risk_level`(`flexible|stable|high_risk`)，`amount`(最新金额快照)，`created_at/updated_at`。
- ProductBalance：`id`，`product_id`，`amount`，`as_of`(快照时间)，`created_at/updated_at`。(`product_id`,`as_of`) 唯一，金额非负。最新 `as_of` 会同步到产品的 `amount`。

## 3. 接口一览
| 路径 | 方法 | 作用 | 权限 | 备注 |
| --- | --- | --- | --- | --- |
| /v1/institutions | GET | 列表当前用户的机构 | read:deposit | 支持按 `type` 过滤、分页 |
| /v1/institutions | POST | 创建机构 | write:deposit | `name` 去重于当前用户 |
| /v1/institutions/{id} | PATCH | 更新机构名称/类型 | write:deposit | 仅当前用户可操作 |
| /v1/products | GET | 列出金融产品 | read:deposit | 过滤：`institution_id`、`product_type`、`status`、`risk_level`；分页 |
| /v1/products | POST | 创建金融产品 | write:deposit | 绑定已有机构；初始 `amount` 可传或默认 0 |
| /v1/products/{id} | PATCH | 更新状态/风险/名称/类型 | write:deposit | `amount` 通常由快照同步，避免直接改写 |
| /v1/products/{id}/balances | GET | 查询产品余额历史 | read:deposit | 支持 `from`/`to` 过滤时间范围 |
| /v1/products/{id}/balances | POST | 写入余额快照 | write:deposit | (`product_id`,`as_of`) 幂等；最新快照自动同步到产品金额 |

## 4. 请求参数与校验
- 公共分页：`page>=1`，`page_size` 默认 20，最大 200。
- Institution
  - `name`：非空，长度 1..128，同用户唯一。
  - `type`：`bank|broker|other`。
- FinancialProduct
  - `institution_id`：必须存在且归属当前用户。
  - `product_type`：`deposit|investment|securities|other`。
  - `currency`：ISO 4217，必须存在于 `currency.currencies`。
  - `status`：`active|inactive|closed`；`risk_level`：`flexible|stable|high_risk`。
  - `amount`：NUMERIC(20,6)，>=0（若提供）。
- ProductBalance
  - `amount`：NUMERIC(20,6) >=0。
  - `as_of`：TIMESTAMPTZ，表示快照时间点；与 `product_id` 组合唯一。

## 5. 错误与幂等
- 404：机构/产品不存在或不属于当前用户。
- 409：(`product_id`,`as_of`) 冲突；机构名重复。
- 422：字段校验失败（类型、状态、币种不存在等）。
- 幂等：余额快照以 (`product_id`,`as_of`) 保证幂等；可配合 Idempotency-Key 做请求级幂等。

## 6. 示例
```http
POST /v1/institutions
{ "name": "My Bank", "type": "bank" }

POST /v1/products
{ "institution_id": 1, "name": "活期储蓄", "product_type": "deposit", "currency": "CNY", "risk_level": "flexible" }

POST /v1/products/1/balances
{ "amount": "12345.67", "as_of": "2025-01-08T12:00:00Z" }

GET /v1/products/1/balances?from=2025-01-01T00:00:00Z&to=2025-01-31T23:59:59Z
```

## 7. 监控与一致性
- 关键指标：`balance_write_latency`、`balance_snapshot_freshness`、`product_amount_drift`（产品表与最新快照差异，应为 0）。
- 触发器在同一事务内同步最新快照到 `financial_products.amount`，避免手工更新该字段导致漂移。

## 8. 迁移与数据修复提示
- 迁移时需为历史快照回填 `amount` 初值，并用最新 `as_of` 重新同步产品金额。
- 并发写入同一产品的快照时，确保 `as_of` 单调或接受同时间戳的自然幂等覆盖。
