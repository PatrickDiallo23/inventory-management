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
        assert order["order_number"].startswith("PO-2026-")
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
