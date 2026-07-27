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
