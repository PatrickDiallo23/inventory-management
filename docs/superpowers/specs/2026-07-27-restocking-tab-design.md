# Restocking Tab — Design

**Date:** 2026-07-27
**Status:** Approved for planning

## Summary

A new "Restocking" tab lets a user set a budget via a slider, see budget-aware restock recommendations drawn from the demand forecast data, and submit a purchase order for those recommendations. Submitted orders appear in a new "Submitted Orders" section on the existing Orders tab, showing delivery lead time.

## Problem / Context

The demand forecast (`server/data/demand_forecasts.json`, 9 items) currently has no cost data and only 1 of its 9 SKUs overlaps with `inventory.json`. There's no existing concept of a "purchase/restocking order" distinct from the customer-facing `orders` list — `purchase_orders.json` exists but is empty and tied to `backlog_item_id`, which doesn't fit this feature (demand-forecast-driven restocking isn't backlog-driven).

## Data Changes

`server/data/demand_forecasts.json` gains two fields per item (mock values, calibrated so that fully restocking every item's forecasted demand costs ~$44,655 total — comfortably under the $50,000 slider max, matching the rationale for that range):

| SKU | unit_cost | lead_time_days | forecasted_demand | full-fund cost |
|---|---|---|---|---|
| WDG-001 | 20.00 | 10 | 450 | 9,000 |
| BRG-102 | 15.00 | 14 | 152 | 2,280 |
| GSK-203 | 5.00 | 7 | 600 | 3,000 |
| MTR-304 | 200.00 | 21 | 35 | 7,000 |
| FLT-405 | 5.00 | 5 | 950 | 4,750 |
| VLV-506 | 35.00 | 12 | 121 | 4,235 |
| PSU-501 | 20.00 | 9 | 252 | 5,040 |
| SNR-420 | 25.00 | 15 | 182 | 4,550 |
| CTL-330 | 50.00 | 18 | 96 | 4,800 |

**Total full-fund cost: $44,655** — the $50,000 max leaves ~$5,345 of headroom, so the top of the slider funds every recommendation in full.

`DemandForecast` Pydantic model in `server/main.py` gains matching `unit_cost: float` and `lead_time_days: int` fields.

## Backend Design

### Recommendation algorithm

**Priority order (computed once, not per request):** since demand-forecast data is static for the process lifetime (loaded once at startup, same as the rest of `mock_data.py`), the urgency ranking is computed a single time at module load, not re-sorted on every request:

1. Sort all forecast items by urgency: `increasing` trend first (ordered by `forecasted_demand - current_demand` descending), then `stable`, then `decreasing`.
2. Build a cumulative-cost prefix array over this order: `prefix_cost[i]` = cost to fully fund items `0..i` at full `forecasted_demand` quantity (the target: stock enough to cover the whole forecast period).

**Per-request budget application (O(log n), not O(n)):** given a budget, binary-search (`bisect_right`) the prefix array for the cutoff index instead of walking the list summing as it goes:
- Items before the cutoff → full `recommended_quantity = forecasted_demand`.
- The single item at the cutoff → partial quantity = `remaining_budget // unit_cost`.
- Items after the cutoff → `recommended_quantity: 0` (shown, not hidden, so the user can see what didn't make the cut).

This keeps the expensive work (sorting) to a one-time cost regardless of whether the forecast table has 9 rows or 9,000, and turns each request into a binary search plus O(1) math on the boundary item.

**Discrete-budget caching:** the slider steps in $500 increments over $0–$50,000 (101 possible values), so `budget` is typed as `int` (whole dollars) on the endpoint — this keeps `functools.lru_cache` keys exact (avoids float key mismatches, e.g. `1000.0` vs `1000.0000001`, from JS-computed values). Revisiting a slider position (common when dragging back and forth) is then a cache hit, not a recompute.

### Endpoints

- `GET /api/restocking/recommendations?budget=<int>` — `budget` defaults to `0` if omitted (returns all items with `recommended_quantity: 0`); returns `400` if negative. Response: list of `{item_sku, item_name, trend, forecasted_demand, unit_cost, lead_time_days, recommended_quantity, line_total}` (always all 9 items, in priority order), plus `total_cost` and `remaining_budget`.
- `POST /api/restocking/orders` — body `{budget, items: [{item_sku, item_name, quantity, unit_cost}]}` (only items with `quantity > 0`). Returns `400` if `items` is empty or any quantity is non-positive. Server computes `total_cost`, generates a sequential order number `PO-2026-{count+1:04d}` (e.g. `PO-2026-0001`, count = current length of `submitted_restocking_orders`; year prefix matches the current calendar year rather than being hardcoded to a stale value), sets `lead_time_days` = max across included items, `created_date` = `datetime.now()` formatted as ISO without timezone (matching the existing `"2025-09-30T10:30:00"` style already used in `inventory.json`), `expected_delivery` = `created_date + timedelta(days=lead_time_days)` in the same format, `status = "Submitted"`. Appended to a new in-memory list `submitted_restocking_orders` (starts empty, resets on server restart — same lifecycle as the rest of this app's mock data).
- `GET /api/restocking/orders` — returns `submitted_restocking_orders`, consumed by the Orders tab.

No changes to the existing `orders` list or endpoints — restocking orders are purchase-side (factory → supplier), a distinct concept from the existing customer sales `orders`, and get their own list/endpoints.

## Frontend Design

**New route & nav tab:** `client/src/views/Restocking.vue`, registered at `/restocking` in `main.js`, with a new tab in `App.vue`'s `nav-tabs` (`t('nav.restocking')`, added to `en.js`/`ja.js`). No `useFilters` wiring — warehouse/category/status/month don't apply to demand-forecast data (same reasoning as why Inventory has no month filter).

**Budget slider:** native `<input type="range" min="0" max="50000" step="500">` bound to a local `budget` ref, value displayed as formatted currency. A `watch` on `budget` debounces ~300ms before calling `api.getRestockingRecommendations(budget)`. A monotonically increasing request token guards against a stale slow response overwriting a newer one.

**Recommendations table:** one row per forecast item — name, SKU, trend badge, forecasted demand, recommended quantity, unit cost, line total, lead time — plus a summary bar showing `total_cost` vs the selected budget and remaining budget. Items with `recommended_quantity: 0` are shown dimmed rather than hidden.

**Place Order button:** disabled when no item has `recommended_quantity > 0`. On click, posts the current recommendation set (filtered to `quantity > 0`) via `api.createRestockingOrder(...)`. On success, shows an inline confirmation (order number + expected delivery date) and resets the view.

**`Orders.vue` changes:** new "Submitted Orders" card below the existing "All Orders" table, fetched independently via `api.getRestockingOrders()` on mount (not tied to the customer-order filters). Columns: Order Number, Items (reusing the existing `<details>` expandable pattern), Total Cost, Submitted Date, Expected Delivery, Status badge ("Submitted").

**`api.js` additions:** `getRestockingRecommendations(budget)`, `createRestockingOrder(payload)`, `getRestockingOrders()`.

## Error Handling

- Backend: `budget` defaults to `0` if omitted; `400` if negative. `POST /api/restocking/orders` returns `400` for empty `items` or non-positive quantities — mirrors the existing `HTTPException` pattern in `main.py`.
- Frontend: Restocking.vue and the Orders.vue "Submitted Orders" section each get independent `loading`/`error` refs (not shared with the existing orders fetch), following the established `try/catch/finally` pattern used throughout the app. Errors render inline (`"Failed to load recommendations: " + err.message`).

## Testing

New `tests/backend/test_restocking.py` (per the `backend-api-test` skill's conventions), covering:
- Recommendations at `budget=0`, a partial budget (hits the boundary item), and a budget large enough to fully fund everything.
- Correct priority order (increasing-trend items funded before stable/decreasing).
- Boundary item gets the correct partial quantity; items past the cutoff get `0`.
- `POST /api/restocking/orders` produces a sequential order number, correct `total_cost`, and `expected_delivery = created_date + max(lead_time_days)`.
- `GET /api/restocking/orders` reflects previously submitted orders.

No frontend test runner exists in this repo (confirmed: no test script in `client/package.json`), so the UI flow (slider → recommendations → place order → appears in Orders tab) is verified manually via the Playwright MCP tools against the running dev servers, matching the project's existing convention.

## Out of Scope

- Manual editing/deselection of recommended items before placing the order (user submits exactly what's recommended).
- Persistence across server restarts (matches existing mock-data lifecycle — everything is in-memory).
- Linking restocking orders back to specific inventory items/warehouses (most demand-forecast SKUs don't exist in `inventory.json`).
