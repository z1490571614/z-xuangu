# T0 Simulation Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily simulation backtest for `default_auction_t0_limit_lgbm` that buys up to the model's top 2 picks per day, keeps at most 4 positions, sells on daily close conditions, and displays results on a new page.

**Architecture:** Add focused ORM tables for runs, daily equity, and trades. Add a service that predicts from `default_auction_training_sample`, prices from `stock_daily_data`, simulates positions, persists results, and exposes API endpoints under `/api/v1/backtest/t0-simulation`. Add a Vue route and page for running and viewing backtests.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, pytest, Vue 3, Vite.

---

### Task 1: Backend Models And Service

**Files:**
- Create: `backend/models/t0_simulation_backtest.py`
- Modify: `backend/models/__init__.py`
- Create: `backend/services/model_engine/t0_simulation_backtest_service.py`
- Test: `tests/backend/unit/test_t0_simulation_backtest_service.py`

- [ ] Write failing tests for top2 buy, max 4 holdings, open/close pricing, take-profit/stop-loss/max-holding sells, and no fake price fallback.
- [ ] Implement ORM models and register them.
- [ ] Implement request dataclass, create/list/get/run service functions.
- [ ] Run `pytest tests/backend/unit/test_t0_simulation_backtest_service.py -q`.

### Task 2: API

**Files:**
- Modify: `backend/api/backtest.py`
- Test: `tests/backend/unit/test_t0_simulation_backtest_api.py`

- [ ] Write failing API tests for create/list/detail and validation.
- [ ] Add request schema and endpoints.
- [ ] Run `pytest tests/backend/unit/test_t0_simulation_backtest_api.py -q`.

### Task 3: Frontend Page

**Files:**
- Create: `frontend/src/views/T0SimulationBacktest.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/App.vue`

- [ ] Add route `/backtest/t0-simulation`.
- [ ] Add nav entry `日线模拟回测`.
- [ ] Build a page with controls, summary cards, daily equity table, and trade table.
- [ ] Run `cd frontend && npm run build`.

### Task 4: Verification

**Files:**
- All changed files

- [ ] Run `pytest tests/backend/unit/test_t0_simulation_backtest_service.py tests/backend/unit/test_t0_simulation_backtest_api.py -q`.
- [ ] Run focused model/backtest tests.
- [ ] Run `cd frontend && npm run build`.
- [ ] Check `git diff --check`.
