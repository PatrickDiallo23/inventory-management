# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Factory Inventory Management System Demo with GitHub integration - Full-stack application with Vue 3 frontend, Python FastAPI backend, and in-memory mock data (no database). Built for a Claude Code workshop.

> ⚠️ **This repository and any fork you create are PUBLIC.** Do not commit credentials, internal hostnames, or private registry URLs. `client/.npmrc` pins the public npm registry and `client/package-lock.json` is gitignored to prevent locally-configured registries from leaking into commits — leave both in place.

## Critical Tool Usage Rules

### Subagents
Use the Task tool with these specialized subagents for appropriate tasks:

- **vue-expert**: Use for Vue 3 frontend features, UI components, styling, and client-side functionality
  - Examples: Creating components, fixing reactivity issues, performance optimization, complex state management
  - **MANDATORY RULE: ANY time you need to create or significantly modify a .vue file, you MUST delegate to vue-expert**
  - Scope: `client/src/{views,components}/*.vue`, `client/src/composables/*.js`, `client/src/api.js`, `client/src/App.vue`, `client/src/main.js` only — it does not touch `server/`
- **code-reviewer**: Use after writing significant code to review quality and best practices
- **security-auditor**: Fast focused security pass on changed files only (secrets, XSS via `v-html`, missing input validation) — not a full audit
- **Explore**: Use for understanding codebase structure, searching for patterns, or answering questions about how components work
- **general-purpose**: Use for complex multi-step tasks or when other agents don't fit
- **git work**: Only run git add for staging, but **DON'T** commit the files

### Skills
- **backend-api-test** skill: Use when writing or modifying tests in `tests/backend` directory with pytest and FastAPI TestClient

### MCP Tools
- **ALWAYS use GitHub MCP tools** (`mcp__github__*`) for ALL GitHub operations
  - Exception: Local branches only - use `git checkout -b` instead of `mcp__github__create_branch`
- **ALWAYS use Playwright MCP tools** (`mcp__playwright__*`) for browser testing
  - Test against: `http://localhost:3000` (frontend), `http://localhost:8001` (API)

## Stack
- **Frontend**: Vue 3 + Composition API + Vite (port 3000)
- **Backend**: Python FastAPI (port 8001)
- **Data**: JSON files in `server/data/` loaded via `server/mock_data.py`
- **Package managers**: `uv` for Python (backend + tests share one `pyproject.toml`/`uv.lock` in `server/`), `npm` for the client

## Quick Start

```bash
# Backend (from server/)
uv sync
uv run python main.py

# Frontend (from client/)
npm install && npm run dev
```

`/start` (or `scripts/start.sh` on macOS/Linux) kills anything already on ports 3000/8001 and launches both servers in the background. `/stop` (or `scripts/stop.sh`) tears them down. On Windows, use `netstat -aon | findstr :PORT` + `taskkill /F /PID <pid>` instead of the shell scripts.

## Testing

Backend tests live in `tests/backend/` and share the `server/` virtual environment (run `uv sync` in `server/` first).

```bash
cd tests
uv run pytest -v                                              # all tests
uv run pytest backend/test_inventory.py -v                    # one file
uv run pytest backend/test_inventory.py::TestInventoryEndpoints -v                    # one class
uv run pytest backend/test_inventory.py::TestInventoryEndpoints::test_get_all_inventory -v  # one test
uv run pytest --cov=../server --cov-report=html               # with coverage
```

Test files actually present: `test_inventory.py`, `test_dashboard.py`, `test_misc_endpoints.py` (demand/backlog/spending/root), `conftest.py` (the `client` fixture wraps `server/main.py`'s FastAPI app via `TestClient`). Note: `tests/README.md` and the `backend-api-test` skill both reference a `test_orders.py` that does not exist in the repo — there is no dedicated orders test file or `TestOrdersEndpoints` class yet.

There is no frontend test suite (no test runner configured in `client/package.json`) — verify UI changes with the Playwright MCP tools instead.

Production build: `cd client && npm run build` (output: `client/dist/`).

## Architecture

**Request flow**: Vue view → composable (`useFilters`) builds query params → `client/src/api.js` (axios) → FastAPI route in `server/main.py` → `apply_filters`/`filter_by_month` helpers filter the in-memory lists from `server/mock_data.py` → Pydantic `response_model` validates/serializes → Vue computed properties derive display data from the raw refs.

**Composables are singletons, not per-component state.** `useFilters`, `useAuth`, and `useI18n` each define their `ref()`/`computed()` state at module scope (outside the exported function), so every component importing them shares one instance — calling `useFilters()` twice does not create two independent filter states. Keep this in mind before adding local state inside these files.

**i18n system** (`client/src/composables/useI18n.js` + `client/src/locales/{en,ja}.js`): locale persisted to `localStorage['app-locale']`, currency derived from locale (`ja` → JPY, else USD), with helper translators for product names, customer names, and warehouse/city names (`translateProductName`, `translateCustomerName`, `translateWarehouse`) — these aren't generic string keys, they look up fixed maps per-locale. `useAuth`'s mock user (including task list) is also generated per-locale via `useI18n`.

**Backend is a single file** (`server/main.py`) — no `models.py`/`services/` split despite what `server/CLAUDE.md`'s "Module Structure for Growth" section shows as an aspirational future layout; all Pydantic models and routes currently live together in `main.py`.

**`client/src/api.js` has more methods than the backend implements.** `getTasks`, `createTask`, `deleteTask`, `toggleTask`, `createPurchaseOrder`, and `getPurchaseOrderByBacklogItem` call endpoints (`/api/tasks`, `/api/purchase-orders`) that don't exist in `server/main.py` — only `purchase_orders.json` is loaded and read (to compute `has_purchase_order` on backlog items via `GET /api/backlog`). Check `main.py` before assuming an `api.js` method is backed by a real endpoint.

**Reports endpoints** (`GET /api/reports/quarterly`, `GET /api/reports/monthly-trends`) compute quarter/month aggregates from `orders` on every request — they don't accept filters and aren't listed under `client/src/views` filter wiring; used by `Reports.vue`.

## Key Patterns

**Filter System**: 4 filters (Time Period, Warehouse, Category, Order Status) apply to all data via query params
**Data Flow**: Vue filters → `client/src/api.js` → FastAPI → In-memory filtering → Pydantic validation → Computed properties
**Reactivity**: Raw data in refs (`allOrders`, `inventoryItems`), derived data in computed properties

## API Endpoints
- `GET /api/inventory`, `GET /api/inventory/{id}` - Filters: warehouse, category
- `GET /api/orders`, `GET /api/orders/{id}` - Filters: warehouse, category, status, month
- `GET /api/dashboard/summary` - All filters
- `GET /api/demand`, `/api/backlog` - No filters
- `GET /api/spending/summary|monthly|categories|transactions` - No filters
- `GET /api/reports/quarterly`, `/api/reports/monthly-trends` - No filters

## Common Issues
1. Use unique keys in v-for (not `index`) - use `sku`, `month`, etc.
2. Validate dates before `.getMonth()` calls
3. Update Pydantic models when changing JSON data structure
4. Inventory filters don't support month (no time dimension)
5. Revenue goals: $800K/month single, $9.6M YTD all months

## File Locations
- Views: `client/src/views/*.vue`
- API Client: `client/src/api.js`
- Backend: `server/main.py`, `server/mock_data.py`
- Data: `server/data/*.json`
- Styles: `client/src/App.vue`

## Design System
- Colors: Slate/gray (#0f172a, #64748b, #e2e8f0)
- Status: green/blue/yellow/red
- Charts: Custom SVG, CSS Grid for layouts
- No emojis in UI
