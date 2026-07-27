# Restocking Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Restocking" tab where a user sets a budget via a slider, sees budget-aware restock recommendations from demand forecast data, submits a purchase order, and sees that order appear in a new "Submitted Orders" section on the Orders tab with its delivery lead time.

**Architecture:** Demand-forecast data gains `unit_cost`/`lead_time_days` fields. The backend precomputes a priority order and cumulative-cost prefix array once at module load (data is static for the process lifetime), then answers each `GET /api/restocking/recommendations?budget=<int>` request with an O(log n) binary search instead of re-sorting/re-walking every time, cached via `lru_cache` since the slider only produces 101 distinct budget values. Submitted orders are stored in a new in-memory list, mirroring how the rest of this app's mock data behaves (resets on restart). The frontend is a new Vue view plus a small addition to the existing Orders view.

**Tech Stack:** FastAPI + Pydantic (backend), Vue 3 Composition API + Vue Router + Axios (frontend), pytest + FastAPI TestClient (backend tests).

## Global Constraints

- Backend stays a single file: all new models/routes go in `server/main.py` (no `models.py`/`services/` split — matches current architecture).
- No database, no auth changes — submitted orders are in-memory only (`docs/superpowers/specs/2026-07-27-restocking-tab-design.md`, "Out of Scope").
- Any `.vue` file created or modified MUST be delegated to the **vue-expert** subagent (project `CLAUDE.md` mandatory rule).
- No frontend test runner exists in this repo — frontend verification is manual, via the Playwright MCP tools against the running dev servers (`http://localhost:3000` / `http://localhost:8001`).
- Currency/locale handling must go through the existing `useI18n` composable (`currentCurrency`, `translateProductName`) — don't hardcode `$`.
- Budget is a whole-dollar `int` end-to-end (slider steps of $500) — keeps the backend `lru_cache` key exact.

---

### Task 1: Enrich demand forecast data with cost and lead time

**Files:**
- Modify: `server/data/demand_forecasts.json`
- Modify: `server/main.py` (the `DemandForecast` Pydantic model, currently around line 84)
- Test: `tests/backend/test_misc_endpoints.py` (append to `TestDemandEndpoints`)

**Interfaces:**
- Produces: every object in `demand_forecasts` (and every `DemandForecast` API response) now has `unit_cost: float` and `lead_time_days: int`, in addition to the existing `id`, `item_sku`, `item_name`, `current_demand`, `forecasted_demand`, `trend`, `period` fields.

- [ ] **Step 1: Write the failing test**

Append this method to the `TestDemandEndpoints` class in `tests/backend/test_misc_endpoints.py`:

```python
    def test_demand_forecast_has_cost_and_lead_time_fields(self, client):
        """Test that demand forecasts include unit_cost and lead_time_days for restocking."""
        response = client.get("/api/demand")
        data = response.json()

        for forecast in data:
            assert "unit_cost" in forecast
            assert isinstance(forecast["unit_cost"], (int, float))
            assert forecast["unit_cost"] > 0
            assert "lead_time_days" in forecast
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["lead_time_days"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && uv run pytest backend/test_misc_endpoints.py::TestDemandEndpoints::test_demand_forecast_has_cost_and_lead_time_fields -v`
Expected: FAIL — `KeyError` or `assert "unit_cost" in forecast` fails, since the field doesn't exist yet.

- [ ] **Step 3: Replace `server/data/demand_forecasts.json` with this content**

```json
[
  {
    "id": "1",
    "item_sku": "WDG-001",
    "item_name": "Industrial Widget Type A",
    "current_demand": 300,
    "forecasted_demand": 450,
    "trend": "increasing",
    "period": "Next 30 days",
    "unit_cost": 20.00,
    "lead_time_days": 10
  },
  {
    "id": "2",
    "item_sku": "BRG-102",
    "item_name": "Steel Bearing Assembly",
    "current_demand": 150,
    "forecasted_demand": 152,
    "trend": "stable",
    "period": "Next 30 days",
    "unit_cost": 15.00,
    "lead_time_days": 14
  },
  {
    "id": "3",
    "item_sku": "GSK-203",
    "item_name": "High-Temperature Gasket",
    "current_demand": 500,
    "forecasted_demand": 600,
    "trend": "increasing",
    "period": "Next 30 days",
    "unit_cost": 5.00,
    "lead_time_days": 7
  },
  {
    "id": "4",
    "item_sku": "MTR-304",
    "item_name": "Electric Motor 5HP",
    "current_demand": 50,
    "forecasted_demand": 35,
    "trend": "decreasing",
    "period": "Next 30 days",
    "unit_cost": 200.00,
    "lead_time_days": 21
  },
  {
    "id": "5",
    "item_sku": "FLT-405",
    "item_name": "Oil Filter Cartridge",
    "current_demand": 800,
    "forecasted_demand": 950,
    "trend": "increasing",
    "period": "Next 30 days",
    "unit_cost": 5.00,
    "lead_time_days": 5
  },
  {
    "id": "6",
    "item_sku": "VLV-506",
    "item_name": "Pressure Relief Valve",
    "current_demand": 120,
    "forecasted_demand": 121,
    "trend": "stable",
    "period": "Next 30 days",
    "unit_cost": 35.00,
    "lead_time_days": 12
  },
  {
    "id": "7",
    "item_sku": "PSU-501",
    "item_name": "5V 10A Switching Power Supply",
    "current_demand": 250,
    "forecasted_demand": 252,
    "trend": "stable",
    "period": "Next 30 days",
    "unit_cost": 20.00,
    "lead_time_days": 9
  },
  {
    "id": "8",
    "item_sku": "SNR-420",
    "item_name": "Temperature Sensor Module",
    "current_demand": 180,
    "forecasted_demand": 182,
    "trend": "stable",
    "period": "Next 30 days",
    "unit_cost": 25.00,
    "lead_time_days": 15
  },
  {
    "id": "9",
    "item_sku": "CTL-330",
    "item_name": "Logic Controller Board",
    "current_demand": 95,
    "forecasted_demand": 96,
    "trend": "stable",
    "period": "Next 30 days",
    "unit_cost": 50.00,
    "lead_time_days": 18
  }
]
```

- [ ] **Step 4: Update the `DemandForecast` model in `server/main.py`**

Find:

```python
class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str
```

Replace with:

```python
class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str
    unit_cost: float
    lead_time_days: int
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd tests && uv run pytest backend/test_misc_endpoints.py -v`
Expected: PASS — all `TestDemandEndpoints` tests pass, including the new one.

- [ ] **Step 6: Commit**

```bash
git add server/data/demand_forecasts.json server/main.py tests/backend/test_misc_endpoints.py
git commit -m "Add unit_cost and lead_time_days to demand forecast data"
```

---

### Task 2: Restocking recommendation engine + GET endpoint

**Files:**
- Modify: `server/main.py` (add imports, module-level precompute, `compute_restocking_recommendations`, and the `GET /api/restocking/recommendations` route)
- Create: `tests/backend/test_restocking.py`

**Interfaces:**
- Consumes: `demand_forecasts` (list of dicts from `mock_data.py`, each with `item_sku`, `item_name`, `current_demand`, `forecasted_demand`, `trend`, `unit_cost`, `lead_time_days` — from Task 1).
- Produces: module-level `RESTOCKING_PRIORITY_ORDER: list[dict]`, `RESTOCKING_PREFIX_COSTS: list[float]`; function `compute_restocking_recommendations(budget: int) -> dict` returning `{"items": [{"item_sku", "item_name", "trend", "forecasted_demand", "unit_cost", "lead_time_days", "recommended_quantity", "line_total"}, ...], "total_cost": float, "remaining_budget": float}`; route `GET /api/restocking/recommendations`.

- [ ] **Step 1: Write the failing tests**

Create `tests/backend/test_restocking.py`:

```python
"""
Tests for restocking recommendation and order endpoints.
"""
import pytest


class TestRestockingRecommendations:
    """Test suite for GET /api/restocking/recommendations."""

    def test_zero_budget_recommends_nothing(self, client):
        """Test that a zero budget results in no recommended quantities."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["total_cost"] == 0
        assert data["remaining_budget"] == 0
        assert len(data["items"]) == 9
        for item in data["items"]:
            assert item["recommended_quantity"] == 0

    def test_missing_budget_defaults_to_zero(self, client):
        """Test that omitting the budget param behaves like budget=0."""
        response = client.get("/api/restocking/recommendations")
        assert response.status_code == 200

        data = response.json()
        for item in data["items"]:
            assert item["recommended_quantity"] == 0

    def test_negative_budget_returns_400(self, client):
        """Test that a negative budget is rejected."""
        response = client.get("/api/restocking/recommendations?budget=-100")
        assert response.status_code == 400

    def test_increasing_trend_items_funded_before_others(self, client):
        """Test that a small budget only funds the top-priority increasing item."""
        # WDG-001 is the highest-priority increasing item (unit_cost=20.00).
        # $500 buys 25 units of it and nothing else.
        response = client.get("/api/restocking/recommendations?budget=500")
        data = response.json()
        items_by_sku = {item["item_sku"]: item for item in data["items"]}

        assert items_by_sku["WDG-001"]["recommended_quantity"] == 25
        for sku, item in items_by_sku.items():
            if sku != "WDG-001":
                assert item["recommended_quantity"] == 0

    def test_boundary_item_gets_partial_quantity(self, client):
        """Test that a mid-size budget fully funds some items and partially funds one."""
        response = client.get("/api/restocking/recommendations?budget=10000")
        data = response.json()

        # WDG-001 (full-fund cost 9000) should be fully funded; FLT-405 is next
        # in priority order (full-fund cost 4750) and should be partially funded
        # with the remaining $1000 at $5.00/unit = 200 units.
        items_by_sku = {item["item_sku"]: item for item in data["items"]}
        assert items_by_sku["WDG-001"]["recommended_quantity"] == 450
        assert items_by_sku["FLT-405"]["recommended_quantity"] == 200
        assert items_by_sku["GSK-203"]["recommended_quantity"] == 0

        assert data["total_cost"] <= 10000
        assert data["remaining_budget"] == round(10000 - data["total_cost"], 2)

    def test_large_budget_fully_funds_everything(self, client):
        """Test that the full $50,000 slider max funds every item's forecasted demand."""
        response = client.get("/api/restocking/recommendations?budget=50000")
        data = response.json()

        for item in data["items"]:
            assert item["recommended_quantity"] == item["forecasted_demand"]
        assert data["total_cost"] == 44655
        assert data["remaining_budget"] == round(50000 - 44655, 2)

    def test_line_totals_match_quantity_times_cost(self, client):
        """Test that each item's line_total is quantity * unit_cost."""
        response = client.get("/api/restocking/recommendations?budget=15000")
        data = response.json()

        for item in data["items"]:
            expected = round(item["recommended_quantity"] * item["unit_cost"], 2)
            assert abs(item["line_total"] - expected) < 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tests && uv run pytest backend/test_restocking.py -v`
Expected: FAIL — `404 Not Found` for all requests, since the route doesn't exist yet.

- [ ] **Step 3: Add imports to the top of `server/main.py`**

Find:

```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders
```

Replace with:

```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from functools import lru_cache
from bisect import bisect_right
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders
```

- [ ] **Step 4: Add the precompute and recommendation function**

Add this after the `DemandForecast` model (after Task 1's edit) and before the `# API endpoints` comment:

```python
# Restocking recommendation engine
TREND_PRIORITY = {'increasing': 0, 'stable': 1, 'decreasing': 2}


def _build_restocking_priority_order():
    """Sort demand forecast items by restocking urgency: increasing trend
    first (ranked by demand gap, largest first), then stable, then
    decreasing. Computed once at module load since demand_forecasts is
    static for the process lifetime — avoids re-sorting on every request."""
    def sort_key(item):
        gap = item['forecasted_demand'] - item['current_demand']
        return (TREND_PRIORITY.get(item['trend'], 3), -gap)
    return sorted(demand_forecasts, key=sort_key)


RESTOCKING_PRIORITY_ORDER = _build_restocking_priority_order()


def _build_restocking_prefix_costs():
    """Cumulative cost to fully fund items 0..i (in priority order) at their
    full forecasted_demand quantity. Enables O(log n) budget lookups via
    binary search instead of re-walking the list on every request."""
    prefix = []
    running_total = 0.0
    for item in RESTOCKING_PRIORITY_ORDER:
        running_total += item['forecasted_demand'] * item['unit_cost']
        prefix.append(running_total)
    return prefix


RESTOCKING_PREFIX_COSTS = _build_restocking_prefix_costs()


@lru_cache(maxsize=None)
def compute_restocking_recommendations(budget: int) -> dict:
    """Return restock recommendations for a given whole-dollar budget.

    Items before the budget cutoff (found via binary search on the
    precomputed prefix-cost array) are recommended at full forecasted
    demand; the single boundary item gets a partial quantity; items after
    get zero. Cached because the budget slider only produces a small,
    fixed set of distinct values ($0-$50,000 in $500 steps).
    """
    cutoff_index = bisect_right(RESTOCKING_PREFIX_COSTS, budget)
    spent_before_cutoff = RESTOCKING_PREFIX_COSTS[cutoff_index - 1] if cutoff_index > 0 else 0.0
    remaining_after_cutoff = budget - spent_before_cutoff

    recommendations = []
    for i, item in enumerate(RESTOCKING_PRIORITY_ORDER):
        if i < cutoff_index:
            quantity = item['forecasted_demand']
        elif i == cutoff_index:
            quantity = int(remaining_after_cutoff // item['unit_cost']) if item['unit_cost'] > 0 else 0
        else:
            quantity = 0

        line_total = round(quantity * item['unit_cost'], 2)
        recommendations.append({
            'item_sku': item['item_sku'],
            'item_name': item['item_name'],
            'trend': item['trend'],
            'forecasted_demand': item['forecasted_demand'],
            'unit_cost': item['unit_cost'],
            'lead_time_days': item['lead_time_days'],
            'recommended_quantity': quantity,
            'line_total': line_total
        })

    total_cost = round(sum(r['line_total'] for r in recommendations), 2)
    remaining_budget = round(budget - total_cost, 2)
    return {
        'items': recommendations,
        'total_cost': total_cost,
        'remaining_budget': remaining_budget
    }
```

- [ ] **Step 5: Add the GET endpoint**

Add this near the other `/api/demand`-related routes (after the `get_demand_forecasts` endpoint):

```python
@app.get("/api/restocking/recommendations")
def get_restocking_recommendations(budget: int = 0):
    """Get budget-aware restock recommendations from demand forecast data."""
    if budget < 0:
        raise HTTPException(status_code=400, detail="budget must be non-negative")
    return compute_restocking_recommendations(budget)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd tests && uv run pytest backend/test_restocking.py -v`
Expected: PASS — all `TestRestockingRecommendations` tests pass.

- [ ] **Step 7: Commit**

```bash
git add server/main.py tests/backend/test_restocking.py
git commit -m "Add restocking recommendation engine and GET endpoint"
```

---

### Task 3: Submit and list restocking orders

**Files:**
- Modify: `server/main.py` (add request/response models, `submitted_restocking_orders` list, `POST`/`GET /api/restocking/orders` routes)
- Test: `tests/backend/test_restocking.py` (append `TestRestockingOrders`)

**Interfaces:**
- Consumes: `demand_forecasts` (for `lead_time_days` lookup by `item_sku`) — from Task 1.
- Produces: `submitted_restocking_orders: list[dict]`; Pydantic models `RestockingOrderItemRequest`, `CreateRestockingOrderRequest`, `RestockingOrderItem`, `RestockingOrder`; routes `POST /api/restocking/orders`, `GET /api/restocking/orders`. Each stored/returned order has shape `{"id", "order_number", "items": [{"item_sku", "item_name", "quantity", "unit_cost", "line_total"}], "total_cost", "lead_time_days", "created_date", "expected_delivery", "status"}`.

- [ ] **Step 1: Write the failing tests**

Append this class to `tests/backend/test_restocking.py`:

```python
class TestRestockingOrders:
    """Test suite for POST/GET /api/restocking/orders."""

    def test_create_order_success(self, client):
        """Test submitting a restocking order with valid items."""
        payload = {
            "budget": 5000,
            "items": [
                {"item_sku": "GSK-203", "item_name": "High-Temperature Gasket", "quantity": 100, "unit_cost": 5.0},
                {"item_sku": "FLT-405", "item_name": "Oil Filter Cartridge", "quantity": 50, "unit_cost": 5.0}
            ]
        }
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 200

        order = response.json()
        assert order["order_number"].startswith("PO-2025-")
        assert order["total_cost"] == 100 * 5.0 + 50 * 5.0
        assert order["status"] == "Submitted"
        assert order["lead_time_days"] == max(7, 5)  # GSK-203 lead=7, FLT-405 lead=5
        assert "T" in order["created_date"]
        assert "T" in order["expected_delivery"]
        assert len(order["items"]) == 2

    def test_create_order_empty_items_returns_400(self, client):
        """Test that submitting an order with no items is rejected."""
        response = client.post("/api/restocking/orders", json={"budget": 1000, "items": []})
        assert response.status_code == 400

    def test_create_order_non_positive_quantity_returns_400(self, client):
        """Test that a zero or negative quantity is rejected."""
        payload = {
            "budget": 1000,
            "items": [{"item_sku": "GSK-203", "item_name": "High-Temperature Gasket", "quantity": 0, "unit_cost": 5.0}]
        }
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 400

    def test_submitted_order_appears_in_list(self, client):
        """Test that a submitted order shows up in GET /api/restocking/orders."""
        payload = {
            "budget": 1000,
            "items": [{"item_sku": "VLV-506", "item_name": "Pressure Relief Valve", "quantity": 10, "unit_cost": 35.0}]
        }
        create_response = client.post("/api/restocking/orders", json=payload)
        created_order = create_response.json()

        list_response = client.get("/api/restocking/orders")
        assert list_response.status_code == 200

        orders = list_response.json()
        order_numbers = [o["order_number"] for o in orders]
        assert created_order["order_number"] in order_numbers
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tests && uv run pytest backend/test_restocking.py::TestRestockingOrders -v`
Expected: FAIL — `404 Not Found`, since the routes don't exist yet.

- [ ] **Step 3: Add request/response models to `server/main.py`**

Add these after the `CreatePurchaseOrderRequest` model:

```python
class RestockingOrderItemRequest(BaseModel):
    item_sku: str
    item_name: str
    quantity: int
    unit_cost: float


class CreateRestockingOrderRequest(BaseModel):
    budget: int
    items: List[RestockingOrderItemRequest]


class RestockingOrderItem(BaseModel):
    item_sku: str
    item_name: str
    quantity: int
    unit_cost: float
    line_total: float


class RestockingOrder(BaseModel):
    id: str
    order_number: str
    items: List[RestockingOrderItem]
    total_cost: float
    lead_time_days: int
    created_date: str
    expected_delivery: str
    status: str
```

- [ ] **Step 4: Add the in-memory store and endpoints**

Add this after the `get_restocking_recommendations` route (from Task 2):

```python
submitted_restocking_orders: List[dict] = []


@app.post("/api/restocking/orders", response_model=RestockingOrder)
def create_restocking_order(request: CreateRestockingOrderRequest):
    """Submit a restocking purchase order built from recommended items."""
    if not request.items:
        raise HTTPException(status_code=400, detail="items cannot be empty")
    if any(item.quantity <= 0 for item in request.items):
        raise HTTPException(status_code=400, detail="all item quantities must be positive")

    order_items = []
    for item in request.items:
        line_total = round(item.quantity * item.unit_cost, 2)
        order_items.append({
            'item_sku': item.item_sku,
            'item_name': item.item_name,
            'quantity': item.quantity,
            'unit_cost': item.unit_cost,
            'line_total': line_total
        })

    total_cost = round(sum(i['line_total'] for i in order_items), 2)

    ordered_skus = {item.item_sku for item in request.items}
    lead_times = [f['lead_time_days'] for f in demand_forecasts if f['item_sku'] in ordered_skus]
    lead_time_days = max(lead_times) if lead_times else 0

    created_date = datetime.now()
    expected_delivery = created_date + timedelta(days=lead_time_days)
    date_format = "%Y-%m-%dT%H:%M:%S"

    order = {
        'id': str(len(submitted_restocking_orders) + 1),
        'order_number': f"PO-2025-{len(submitted_restocking_orders) + 1:04d}",
        'items': order_items,
        'total_cost': total_cost,
        'lead_time_days': lead_time_days,
        'created_date': created_date.strftime(date_format),
        'expected_delivery': expected_delivery.strftime(date_format),
        'status': 'Submitted'
    }
    submitted_restocking_orders.append(order)
    return order


@app.get("/api/restocking/orders", response_model=List[RestockingOrder])
def get_restocking_orders():
    """List all submitted restocking orders."""
    return submitted_restocking_orders
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd tests && uv run pytest backend/test_restocking.py -v`
Expected: PASS — all tests in both `TestRestockingRecommendations` and `TestRestockingOrders` pass.

- [ ] **Step 6: Run the full backend test suite to check for regressions**

Run: `cd tests && uv run pytest -v`
Expected: PASS — all existing tests plus the new restocking tests pass.

- [ ] **Step 7: Commit**

```bash
git add server/main.py tests/backend/test_restocking.py
git commit -m "Add restocking order submission and listing endpoints"
```

---

### Task 4: Frontend API client methods

**Files:**
- Modify: `client/src/api.js`

**Interfaces:**
- Consumes: `GET /api/restocking/recommendations?budget=<int>`, `POST /api/restocking/orders`, `GET /api/restocking/orders` (from Tasks 2-3).
- Produces: `api.getRestockingRecommendations(budget)`, `api.createRestockingOrder(payload)`, `api.getRestockingOrders()` — consumed by Restocking.vue (Task 6) and Orders.vue (Task 7).

- [ ] **Step 1: Add the three methods to `client/src/api.js`**

Find the closing of the `api` object (the last method, `getPurchaseOrderByBacklogItem`, followed by the final `}`):

```javascript
  async getPurchaseOrderByBacklogItem(backlogItemId) {
    const response = await axios.get(`${API_BASE_URL}/purchase-orders/${backlogItemId}`)
    return response.data
  }
}
```

Replace with:

```javascript
  async getPurchaseOrderByBacklogItem(backlogItemId) {
    const response = await axios.get(`${API_BASE_URL}/purchase-orders/${backlogItemId}`)
    return response.data
  },

  async getRestockingRecommendations(budget) {
    const response = await axios.get(`${API_BASE_URL}/restocking/recommendations?budget=${budget}`)
    return response.data
  },

  async createRestockingOrder(payload) {
    const response = await axios.post(`${API_BASE_URL}/restocking/orders`, payload)
    return response.data
  },

  async getRestockingOrders() {
    const response = await axios.get(`${API_BASE_URL}/restocking/orders`)
    return response.data
  }
}
```

- [ ] **Step 2: Verify manually**

With both dev servers running (`server`: `uv run python main.py`, `client`: `npm run dev`), open `http://localhost:3000` in a browser, open the DevTools console, and run:

```javascript
const { api } = await import('/src/api.js')
await api.getRestockingRecommendations(10000)
```

Expected: an object with `items` (9 entries), `total_cost`, and `remaining_budget`.

- [ ] **Step 3: Commit**

```bash
git add client/src/api.js
git commit -m "Add restocking API client methods"
```

---

### Task 5: Locale keys for Restocking and Submitted Orders

**Files:**
- Modify: `client/src/locales/en.js`
- Modify: `client/src/locales/ja.js`

**Interfaces:**
- Produces: translation keys `nav.restocking`, `restocking.*`, `orders.submittedOrders.*`, `status.submitted` — consumed by Task 6 (Restocking.vue + nav), Task 7 (Orders.vue).

- [ ] **Step 1: Add `nav.restocking` to `client/src/locales/en.js`**

Find:

```javascript
  nav: {
    overview: 'Overview',
    inventory: 'Inventory',
    orders: 'Orders',
    finance: 'Finance',
    demandForecast: 'Demand Forecast',
    companyName: 'Catalyst Components',
    subtitle: 'Inventory Management System'
  },
```

Replace with:

```javascript
  nav: {
    overview: 'Overview',
    inventory: 'Inventory',
    orders: 'Orders',
    finance: 'Finance',
    demandForecast: 'Demand Forecast',
    restocking: 'Restocking',
    companyName: 'Catalyst Components',
    subtitle: 'Inventory Management System'
  },
```

- [ ] **Step 2: Add `orders.submittedOrders` to `client/src/locales/en.js`**

Find (the end of the `orders` block):

```javascript
  // Orders
  orders: {
    title: 'Orders',
    description: 'View and manage customer orders',
    allOrders: 'All Orders',
    totalOrders: 'Total Orders',
    totalRevenue: 'Total Revenue',
    avgOrderValue: 'Avg Order Value',
    onTimeDelivery: 'On-Time Delivery',
    itemsCount: '{count} items',
    quantity: 'Qty',
    table: {
      orderNumber: 'Order Number',
      orderId: 'Order ID',
      orderDate: 'Order Date',
      date: 'Date',
      customer: 'Customer',
      category: 'Category',
      warehouse: 'Warehouse',
      items: 'Items',
      value: 'Value',
      totalValue: 'Total Value',
      status: 'Status',
      expectedDelivery: 'Expected Delivery',
      actualDelivery: 'Actual Delivery'
    }
  },
```

Replace with:

```javascript
  // Orders
  orders: {
    title: 'Orders',
    description: 'View and manage customer orders',
    allOrders: 'All Orders',
    totalOrders: 'Total Orders',
    totalRevenue: 'Total Revenue',
    avgOrderValue: 'Avg Order Value',
    onTimeDelivery: 'On-Time Delivery',
    itemsCount: '{count} items',
    quantity: 'Qty',
    table: {
      orderNumber: 'Order Number',
      orderId: 'Order ID',
      orderDate: 'Order Date',
      date: 'Date',
      customer: 'Customer',
      category: 'Category',
      warehouse: 'Warehouse',
      items: 'Items',
      value: 'Value',
      totalValue: 'Total Value',
      status: 'Status',
      expectedDelivery: 'Expected Delivery',
      actualDelivery: 'Actual Delivery'
    },
    submittedOrders: {
      title: 'Submitted Orders',
      noOrders: 'No restocking orders submitted yet',
      table: {
        orderNumber: 'Order Number',
        items: 'Items',
        totalCost: 'Total Cost',
        submittedDate: 'Submitted Date',
        expectedDelivery: 'Expected Delivery',
        status: 'Status'
      }
    }
  },
```

- [ ] **Step 3: Add the `restocking` block to `client/src/locales/en.js`**

Find (the end of the `demand` block, right before `// Filters`):

```javascript
  // Filters
  filters: {
```

Replace with:

```javascript
  // Restocking
  restocking: {
    title: 'Restocking',
    description: 'Set a budget and get restock recommendations based on demand forecasts',
    budgetLabel: 'Available Budget',
    recommendationsTitle: 'Recommended Items',
    totalCost: 'Total Cost',
    remainingBudget: 'Remaining Budget',
    placeOrder: 'Place Order',
    orderSuccess: 'Order {orderNumber} submitted — expected delivery {date}',
    notFunded: 'Not funded at this budget',
    table: {
      sku: 'SKU',
      itemName: 'Item Name',
      trend: 'Trend',
      forecastedDemand: 'Forecasted Demand',
      recommendedQuantity: 'Recommended Qty',
      unitCost: 'Unit Cost',
      lineTotal: 'Line Total',
      leadTime: 'Lead Time (Days)'
    }
  },

  // Filters
  filters: {
```

- [ ] **Step 4: Add `status.submitted` to `client/src/locales/en.js`**

Find:

```javascript
  // Statuses
  status: {
    delivered: 'Delivered',
    shipped: 'Shipped',
    processing: 'Processing',
    backordered: 'Backordered',
    inStock: 'In Stock',
    lowStock: 'Low Stock',
    adequate: 'Adequate'
  },
```

Replace with:

```javascript
  // Statuses
  status: {
    delivered: 'Delivered',
    shipped: 'Shipped',
    processing: 'Processing',
    backordered: 'Backordered',
    submitted: 'Submitted',
    inStock: 'In Stock',
    lowStock: 'Low Stock',
    adequate: 'Adequate'
  },
```

- [ ] **Step 5: Add the matching Japanese keys to `client/src/locales/ja.js`**

Find:

```javascript
  nav: {
    overview: '概要',
    inventory: '在庫',
    orders: '注文',
    finance: '財務',
    demandForecast: '需要予測',
    companyName: '触媒コンポーネンツ',
    subtitle: '在庫管理システム'
  },
```

Replace with:

```javascript
  nav: {
    overview: '概要',
    inventory: '在庫',
    orders: '注文',
    finance: '財務',
    demandForecast: '需要予測',
    restocking: '補充',
    companyName: '触媒コンポーネンツ',
    subtitle: '在庫管理システム'
  },
```

Find:

```javascript
  // Orders
  orders: {
    title: '注文',
    description: '顧客注文の表示と管理',
    allOrders: 'すべての注文',
    totalOrders: '総注文数',
    totalRevenue: '総収益',
    avgOrderValue: '平均注文額',
    onTimeDelivery: '定時配達',
    itemsCount: '{count}件',
    quantity: '数量',
    table: {
      orderNumber: '注文番号',
      orderId: '注文ID',
      orderDate: '注文日',
      date: '日付',
      customer: '顧客',
      category: 'カテゴリ',
      warehouse: '倉庫',
      items: '品目',
      value: '価格',
      totalValue: '合計金額',
      status: 'ステータス',
      expectedDelivery: '予定配達日',
      actualDelivery: '実際の配達日'
    }
  },
```

Replace with:

```javascript
  // Orders
  orders: {
    title: '注文',
    description: '顧客注文の表示と管理',
    allOrders: 'すべての注文',
    totalOrders: '総注文数',
    totalRevenue: '総収益',
    avgOrderValue: '平均注文額',
    onTimeDelivery: '定時配達',
    itemsCount: '{count}件',
    quantity: '数量',
    table: {
      orderNumber: '注文番号',
      orderId: '注文ID',
      orderDate: '注文日',
      date: '日付',
      customer: '顧客',
      category: 'カテゴリ',
      warehouse: '倉庫',
      items: '品目',
      value: '価格',
      totalValue: '合計金額',
      status: 'ステータス',
      expectedDelivery: '予定配達日',
      actualDelivery: '実際の配達日'
    },
    submittedOrders: {
      title: '提出済み発注',
      noOrders: 'まだ補充発注は提出されていません',
      table: {
        orderNumber: '注文番号',
        items: '品目',
        totalCost: '合計金額',
        submittedDate: '提出日',
        expectedDelivery: '予定配達日',
        status: 'ステータス'
      }
    }
  },
```

Find the Japanese `demand` block's closing and the `filters` block's opening (mirroring the English structure — locate the line `  // Filters` in `ja.js`) and insert the `restocking` block immediately before it:

```javascript
  // Restocking
  restocking: {
    title: '補充',
    description: '予算を設定し、需要予測に基づく補充推奨を確認',
    budgetLabel: '利用可能な予算',
    recommendationsTitle: '推奨品目',
    totalCost: '合計金額',
    remainingBudget: '残り予算',
    placeOrder: '発注する',
    orderSuccess: '注文{orderNumber}を提出しました — 配達予定日 {date}',
    notFunded: 'この予算では対象外',
    table: {
      sku: 'SKU',
      itemName: '品目名',
      trend: '傾向',
      forecastedDemand: '予測需要',
      recommendedQuantity: '推奨数量',
      unitCost: '単価',
      lineTotal: '小計',
      leadTime: '納期（日）'
    }
  },

```

Find:

```javascript
  status: {
```

(in the Japanese status block) and view its `backordered` line to add `submitted` right after it, mirroring the English addition (same key, translated value `提出済み`).

- [ ] **Step 6: Verify manually**

Run: `grep -n "restocking" client/src/locales/en.js client/src/locales/ja.js`
Expected: matches in both files for `nav.restocking`, the `restocking` block, and `orders.submittedOrders`.

- [ ] **Step 7: Commit**

```bash
git add client/src/locales/en.js client/src/locales/ja.js
git commit -m "Add restocking and submitted-orders translation keys"
```

---

### Task 6: Restocking view, route, and nav tab

> **This task creates and modifies `.vue` files — per project `CLAUDE.md`, delegate this task to the vue-expert subagent.**

**Files:**
- Create: `client/src/views/Restocking.vue`
- Modify: `client/src/main.js` (register the route)
- Modify: `client/src/App.vue` (add the nav tab)

**Interfaces:**
- Consumes: `api.getRestockingRecommendations`, `api.createRestockingOrder` (Task 4); `t('restocking.*')`, `t('nav.restocking')`, `t('trends.*')`, `t('common.loading')` (Task 5); `useI18n()` (`t`, `currentCurrency`, `currentLocale`, `translateProductName`); global CSS classes `.card`, `.card-header`, `.card-title`, `.table-container`, `.badge` (+ `.badge.increasing/.stable/.decreasing`), `.loading`, `.error`, `.page-header` (all defined in `App.vue`).
- Produces: route `/restocking` rendering `Restocking.vue`; a reachable "Restocking" nav tab.

- [ ] **Step 1: Create `client/src/views/Restocking.vue`**

```vue
<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div class="card budget-card">
      <div class="card-header">
        <h3 class="card-title">{{ t('restocking.budgetLabel') }}</h3>
        <span class="budget-value">{{ currencySymbol }}{{ budget.toLocaleString() }}</span>
      </div>
      <input
        type="range"
        min="0"
        max="50000"
        step="500"
        v-model.number="budget"
        class="budget-slider"
      />
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="summary-bar">
        <div class="summary-item">
          <span class="summary-label">{{ t('restocking.totalCost') }}</span>
          <span class="summary-value">{{ currencySymbol }}{{ recommendations.total_cost.toLocaleString() }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">{{ t('restocking.remainingBudget') }}</span>
          <span class="summary-value">{{ currencySymbol }}{{ recommendations.remaining_budget.toLocaleString() }}</span>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendationsTitle') }}</h3>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.forecastedDemand') }}</th>
                <th>{{ t('restocking.table.recommendedQuantity') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in recommendations.items"
                :key="item.item_sku"
                :class="{ 'not-funded': item.recommended_quantity === 0 }"
              >
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>{{ translateProductName(item.item_name) }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td>{{ item.forecasted_demand }}</td>
                <td>
                  <strong v-if="item.recommended_quantity > 0">{{ item.recommended_quantity }}</strong>
                  <span v-else class="not-funded-label">{{ t('restocking.notFunded') }}</span>
                </td>
                <td>{{ currencySymbol }}{{ item.unit_cost.toFixed(2) }}</td>
                <td>{{ currencySymbol }}{{ item.line_total.toLocaleString() }}</td>
                <td>{{ item.lead_time_days }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="place-order-bar">
        <div v-if="orderConfirmation" class="order-confirmation">
          {{ t('restocking.orderSuccess', { orderNumber: orderConfirmation.order_number, date: formatDate(orderConfirmation.expected_delivery) }) }}
        </div>
        <div v-if="submitError" class="error">{{ submitError }}</div>
        <button
          class="place-order-button"
          :disabled="!canPlaceOrder || submitting"
          @click="placeOrder"
        >
          {{ submitting ? t('common.loading') : t('restocking.placeOrder') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale, translateProductName } = useI18n()

    const currencySymbol = computed(() => {
      return currentCurrency.value === 'JPY' ? '¥' : '$'
    })

    const budget = ref(10000)
    const loading = ref(true)
    const error = ref(null)
    const recommendations = ref({ items: [], total_cost: 0, remaining_budget: 0 })

    const submitting = ref(false)
    const submitError = ref(null)
    const orderConfirmation = ref(null)

    let debounceTimer = null
    let latestRequestId = 0

    const loadRecommendations = async () => {
      const requestId = ++latestRequestId
      try {
        loading.value = true
        error.value = null
        const data = await api.getRestockingRecommendations(budget.value)
        // Ignore this response if a newer request has already been fired
        // (guards against a slow response overwriting a fresher one).
        if (requestId === latestRequestId) {
          recommendations.value = data
        }
      } catch (err) {
        if (requestId === latestRequestId) {
          error.value = 'Failed to load recommendations: ' + err.message
        }
      } finally {
        if (requestId === latestRequestId) {
          loading.value = false
        }
      }
    }

    watch(budget, () => {
      orderConfirmation.value = null
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(loadRecommendations, 300)
    })

    const canPlaceOrder = computed(() => {
      return recommendations.value.items.some(item => item.recommended_quantity > 0)
    })

    const placeOrder = async () => {
      try {
        submitting.value = true
        submitError.value = null
        orderConfirmation.value = null

        const itemsToOrder = recommendations.value.items
          .filter(item => item.recommended_quantity > 0)
          .map(item => ({
            item_sku: item.item_sku,
            item_name: item.item_name,
            quantity: item.recommended_quantity,
            unit_cost: item.unit_cost
          }))

        const order = await api.createRestockingOrder({
          budget: budget.value,
          items: itemsToOrder
        })

        orderConfirmation.value = order
        await loadRecommendations()
      } catch (err) {
        submitError.value = 'Failed to submit order: ' + err.message
      } finally {
        submitting.value = false
      }
    }

    const formatDate = (dateString) => {
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return new Date(dateString).toLocaleDateString(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      })
    }

    onMounted(loadRecommendations)
    onUnmounted(() => {
      if (debounceTimer) clearTimeout(debounceTimer)
    })

    return {
      t,
      budget,
      loading,
      error,
      recommendations,
      currencySymbol,
      translateProductName,
      canPlaceOrder,
      submitting,
      submitError,
      orderConfirmation,
      placeOrder,
      formatDate
    }
  }
}
</script>

<style scoped>
.budget-card {
  margin-bottom: 1.5rem;
}

.budget-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.budget-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  margin-top: 0.5rem;
  accent-color: #2563eb;
}

.summary-bar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.summary-item {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.summary-label {
  font-size: 0.813rem;
  color: #64748b;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.summary-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

tr.not-funded {
  opacity: 0.5;
}

.not-funded-label {
  color: #94a3b8;
  font-style: italic;
  font-size: 0.85rem;
}

.place-order-bar {
  margin-top: 1.5rem;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.75rem;
}

.order-confirmation {
  align-self: stretch;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  font-size: 0.9rem;
}

.place-order-button {
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 8px;
  padding: 0.75rem 1.75rem;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.place-order-button:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-button:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}
</style>
```

- [ ] **Step 2: Register the route in `client/src/main.js`**

Find:

```javascript
import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Dashboard from './views/Dashboard.vue'
import Inventory from './views/Inventory.vue'
import Orders from './views/Orders.vue'
import Demand from './views/Demand.vue'
import Spending from './views/Spending.vue'
import Reports from './views/Reports.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/inventory', component: Inventory },
    { path: '/orders', component: Orders },
    { path: '/demand', component: Demand },
    { path: '/spending', component: Spending },
    { path: '/reports', component: Reports }
  ]
})
```

Replace with:

```javascript
import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Dashboard from './views/Dashboard.vue'
import Inventory from './views/Inventory.vue'
import Orders from './views/Orders.vue'
import Demand from './views/Demand.vue'
import Spending from './views/Spending.vue'
import Reports from './views/Reports.vue'
import Restocking from './views/Restocking.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/inventory', component: Inventory },
    { path: '/orders', component: Orders },
    { path: '/demand', component: Demand },
    { path: '/spending', component: Spending },
    { path: '/restocking', component: Restocking },
    { path: '/reports', component: Reports }
  ]
})
```

- [ ] **Step 3: Add the nav tab in `client/src/App.vue`**

Find:

```vue
          <router-link to="/demand" :class="{ active: $route.path === '/demand' }">
            {{ t('nav.demandForecast') }}
          </router-link>
          <router-link to="/reports" :class="{ active: $route.path === '/reports' }">
```

Replace with:

```vue
          <router-link to="/demand" :class="{ active: $route.path === '/demand' }">
            {{ t('nav.demandForecast') }}
          </router-link>
          <router-link to="/restocking" :class="{ active: $route.path === '/restocking' }">
            {{ t('nav.restocking') }}
          </router-link>
          <router-link to="/reports" :class="{ active: $route.path === '/reports' }">
```

- [ ] **Step 4: Verify manually**

With both dev servers running, navigate to `http://localhost:3000/restocking`:
- The "Restocking" tab appears in the nav and is highlighted active.
- The budget slider defaults to $10,000 and the recommendations table populates.
- Dragging the slider updates recommendations after ~300ms; items past the budget cutoff show "Not funded at this budget".
- Clicking "Place Order" shows a success message with an order number and expected delivery date, and the button becomes disabled again until the budget changes.

- [ ] **Step 5: Commit**

```bash
git add client/src/views/Restocking.vue client/src/main.js client/src/App.vue
git commit -m "Add Restocking tab with budget slider and recommendations"
```

---

### Task 7: Submitted Orders section on the Orders tab

> **This task modifies a `.vue` file — per project `CLAUDE.md`, delegate this task to the vue-expert subagent.**

**Files:**
- Modify: `client/src/views/Orders.vue`

**Interfaces:**
- Consumes: `api.getRestockingOrders()` (Task 4); `t('orders.submittedOrders.*')`, `t('status.submitted')` (Task 5).

- [ ] **Step 1: Add the Submitted Orders card to the template**

Find (the closing of the "All Orders" card, immediately before the two closing `</div>` tags that end `v-else` and `.orders`):

```vue
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
```

Replace with:

```vue
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card submitted-orders-card">
        <div class="card-header">
          <h3 class="card-title">{{ t('orders.submittedOrders.title') }} ({{ submittedOrders.length }})</h3>
        </div>
        <div v-if="submittedOrdersLoading" class="loading">{{ t('common.loading') }}</div>
        <div v-else-if="submittedOrdersError" class="error">{{ submittedOrdersError }}</div>
        <div v-else-if="submittedOrders.length === 0" class="empty-state">
          {{ t('orders.submittedOrders.noOrders') }}
        </div>
        <div v-else class="table-container">
          <table class="orders-table submitted-orders-table">
            <thead>
              <tr>
                <th class="col-order-number">{{ t('orders.submittedOrders.table.orderNumber') }}</th>
                <th class="col-items">{{ t('orders.submittedOrders.table.items') }}</th>
                <th class="col-value">{{ t('orders.submittedOrders.table.totalCost') }}</th>
                <th class="col-date">{{ t('orders.submittedOrders.table.submittedDate') }}</th>
                <th class="col-date">{{ t('orders.submittedOrders.table.expectedDelivery') }}</th>
                <th class="col-status">{{ t('orders.submittedOrders.table.status') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="order in submittedOrders" :key="order.id">
                <td class="col-order-number"><strong>{{ order.order_number }}</strong></td>
                <td class="col-items">
                  <details class="items-details">
                    <summary class="items-summary">
                      {{ t('orders.itemsCount', { count: order.items.length }) }}
                    </summary>
                    <div class="items-dropdown">
                      <div v-for="(item, idx) in order.items" :key="idx" class="item-entry">
                        <span class="item-name">{{ translateProductName(item.item_name) }}</span>
                        <span class="item-meta">{{ t('orders.quantity') }}: {{ item.quantity }} @ {{ currencySymbol }}{{ item.unit_cost }}</span>
                      </div>
                    </div>
                  </details>
                </td>
                <td class="col-value"><strong>{{ currencySymbol }}{{ order.total_cost.toLocaleString() }}</strong></td>
                <td class="col-date">{{ formatDate(order.created_date) }}</td>
                <td class="col-date">{{ formatDate(order.expected_delivery) }}</td>
                <td class="col-status">
                  <span class="badge info">{{ t('status.submitted') }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Add the load logic and state to the script**

Find:

```javascript
    const loading = ref(true)
    const error = ref(null)
    const orders = ref([])
```

Replace with:

```javascript
    const loading = ref(true)
    const error = ref(null)
    const orders = ref([])

    const submittedOrders = ref([])
    const submittedOrdersLoading = ref(true)
    const submittedOrdersError = ref(null)
```

Find:

```javascript
    onMounted(loadOrders)

    return {
      t,
      loading,
      error,
      orders,
      getOrdersByStatus,
      getOrderStatusClass,
      formatDate,
      currencySymbol,
      translateProductName,
      translateCustomerName
    }
```

Replace with:

```javascript
    const loadSubmittedOrders = async () => {
      try {
        submittedOrdersLoading.value = true
        submittedOrdersError.value = null
        submittedOrders.value = await api.getRestockingOrders()
      } catch (err) {
        submittedOrdersError.value = 'Failed to load submitted orders: ' + err.message
      } finally {
        submittedOrdersLoading.value = false
      }
    }

    onMounted(() => {
      loadOrders()
      loadSubmittedOrders()
    })

    return {
      t,
      loading,
      error,
      orders,
      getOrdersByStatus,
      getOrderStatusClass,
      formatDate,
      currencySymbol,
      translateProductName,
      translateCustomerName,
      submittedOrders,
      submittedOrdersLoading,
      submittedOrdersError
    }
```

- [ ] **Step 3: Add spacing for the new card in the style block**

Find:

```css
/* Fixed table layout to prevent column shifting */
.orders-table {
  table-layout: fixed;
  width: 100%;
}
```

Replace with:

```css
.submitted-orders-card {
  margin-top: 1.5rem;
}

/* Fixed table layout to prevent column shifting */
.orders-table {
  table-layout: fixed;
  width: 100%;
}
```

- [ ] **Step 4: Verify manually**

1. Navigate to `http://localhost:3000/restocking`, set a budget, and click "Place Order".
2. Navigate to `http://localhost:3000/orders`.
3. Confirm a new "Submitted Orders" card appears below "All Orders", showing the order number, item count, total cost, submitted date, expected delivery date, and a "Submitted" status badge.

- [ ] **Step 5: Commit**

```bash
git add client/src/views/Orders.vue
git commit -m "Add Submitted Orders section to the Orders tab"
```

---

### Task 8: End-to-end verification

**Files:** None (verification only).

- [ ] **Step 1: Start both dev servers**

Run: `/start` (or manually: `cd server && uv run python main.py`, and in another terminal `cd client && npm run dev`).

- [ ] **Step 2: Run the full backend test suite**

Run: `cd tests && uv run pytest -v`
Expected: PASS — all tests, including `test_restocking.py` and the updated `test_misc_endpoints.py`.

- [ ] **Step 3: Drive the full user flow with the Playwright MCP tools**

1. Navigate to `http://localhost:3000/restocking`.
2. Take a snapshot to confirm the budget slider, recommendations table, and "Place Order" button render.
3. Drag the slider to a low value (e.g. $1,000) and confirm most items show "Not funded at this budget".
4. Drag the slider to $50,000 and confirm every item shows its full `forecasted_demand` as the recommended quantity.
5. Set the slider to a mid-range value (e.g. $15,000), click "Place Order", and confirm the success message shows an order number and expected delivery date.
6. Navigate to `http://localhost:3000/orders` and confirm the "Submitted Orders" section shows the new order with the correct total cost and expected delivery date.
7. Switch the language to Japanese (via the existing language switcher) and confirm the Restocking tab and Submitted Orders section render translated labels without falling back to raw keys.

- [ ] **Step 4: Report results**

No commit for this task — it's verification only. If any step fails, return to the relevant task above and fix it before considering the feature complete.
