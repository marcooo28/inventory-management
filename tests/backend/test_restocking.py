"""
Tests for restocking endpoints (recommendations and submitted orders).
"""
import pytest


def get_recommendations(client, budget):
    response = client.get(f"/api/restocking/recommendations?budget={budget}")
    assert response.status_code == 200
    return response.json()


class TestRestockingRecommendations:
    """Test suite for GET /api/restocking/recommendations."""

    def test_zero_budget_recommends_nothing(self, client):
        data = get_recommendations(client, 0)

        assert data["items"] == []
        assert data["total_cost"] == 0
        assert data["remaining_budget"] == 0
        assert data["max_lead_time_days"] == 0
        # full_cost does not depend on the budget
        assert data["full_cost"] > 0

    def test_items_stay_within_budget(self, client):
        data = get_recommendations(client, 3000)

        assert len(data["items"]) > 0
        assert data["total_cost"] <= 3000
        assert data["remaining_budget"] == pytest.approx(3000 - data["total_cost"], abs=0.01)

    def test_items_ranked_by_demand_gap(self, client):
        data = get_recommendations(client, 3000)

        gaps = [item["demand_gap"] for item in data["items"]]
        assert gaps == sorted(gaps, reverse=True)

    def test_decreasing_trend_never_recommended(self, client):
        data = get_recommendations(client, 1_000_000)

        assert all(item["trend"] != "decreasing" for item in data["items"])
        assert all(item["demand_gap"] > 0 for item in data["items"])

    def test_large_budget_funds_every_positive_gap(self, client):
        data = get_recommendations(client, 1_000_000)
        forecasts = client.get("/api/demand").json()

        expected_skus = {
            f["item_sku"] for f in forecasts
            if f["forecasted_demand"] > f["current_demand"]
        }
        assert {item["sku"] for item in data["items"]} == expected_skus
        assert data["total_cost"] == pytest.approx(data["full_cost"], abs=0.01)

    def test_item_that_does_not_fit_is_skipped_not_fatal(self, client):
        # Cheapest line is about 980 (GSK-203). A budget below every line
        # funds nothing, while one just above it funds at least that line.
        assert get_recommendations(client, 10)["items"] == []
        assert len(get_recommendations(client, 1000)["items"]) >= 1

    def test_max_lead_time_matches_items(self, client):
        data = get_recommendations(client, 3000)

        assert data["max_lead_time_days"] == max(i["lead_time_days"] for i in data["items"])

    def test_negative_budget_rejected(self, client):
        response = client.get("/api/restocking/recommendations?budget=-1")
        assert response.status_code == 422

    def test_missing_budget_rejected(self, client):
        response = client.get("/api/restocking/recommendations")
        assert response.status_code == 422


class TestRestockingOrders:
    """Test suite for POST/GET /api/restocking/orders."""

    def test_no_orders_initially(self, client):
        response = client.get("/api/restocking/orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_place_order_and_list_it(self, client):
        recs = get_recommendations(client, 3000)
        payload = {
            "budget": 3000,
            "items": [{"sku": i["sku"], "quantity": i["quantity"]} for i in recs["items"]],
        }

        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"].startswith("RST-")
        assert order["status"] == "Submitted"
        assert order["total_value"] == pytest.approx(recs["total_cost"], abs=0.01)
        assert order["lead_time_days"] == recs["max_lead_time_days"]
        assert len(order["items"]) == len(recs["items"])

        listed = client.get("/api/restocking/orders").json()
        assert [o["id"] for o in listed] == [order["id"]]

    def test_expected_delivery_is_lead_time_after_submission(self, client):
        from datetime import datetime, timedelta

        response = client.post("/api/restocking/orders", json={
            "budget": 1000,
            "items": [{"sku": "GSK-203", "quantity": 100}],
        })
        order = response.json()

        submitted = datetime.fromisoformat(order["submitted_at"])
        expected = datetime.fromisoformat(order["expected_delivery"])
        assert expected - submitted == timedelta(days=order["lead_time_days"])
        assert order["lead_time_days"] == 10

    def test_lead_time_is_longest_item(self, client):
        # FLT-405 has a 5 day lead time, BRG-102 has 14
        response = client.post("/api/restocking/orders", json={
            "budget": 5000,
            "items": [
                {"sku": "FLT-405", "quantity": 10},
                {"sku": "BRG-102", "quantity": 2},
            ],
        })

        assert response.status_code == 201
        assert response.json()["lead_time_days"] == 14

    def test_orders_listed_newest_first(self, client):
        for sku in ["FLT-405", "GSK-203"]:
            client.post("/api/restocking/orders", json={
                "budget": 1000, "items": [{"sku": sku, "quantity": 1}],
            })

        listed = client.get("/api/restocking/orders").json()
        assert [o["items"][0]["sku"] for o in listed] == ["GSK-203", "FLT-405"]
        assert listed[0]["order_number"] != listed[1]["order_number"]

    def test_unknown_sku_returns_400(self, client):
        response = client.post("/api/restocking/orders", json={
            "budget": 1000, "items": [{"sku": "NOPE-999", "quantity": 1}],
        })

        assert response.status_code == 400
        assert "NOPE-999" in response.json()["detail"]

    def test_over_budget_returns_400(self, client):
        # 100 x 9.80 = 980 > 500
        response = client.post("/api/restocking/orders", json={
            "budget": 500, "items": [{"sku": "GSK-203", "quantity": 100}],
        })

        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()
        assert client.get("/api/restocking/orders").json() == []

    def test_empty_items_rejected(self, client):
        response = client.post("/api/restocking/orders", json={"budget": 1000, "items": []})
        assert response.status_code == 422

    @pytest.mark.parametrize("quantity", [0, -5])
    def test_non_positive_quantity_rejected(self, client, quantity):
        response = client.post("/api/restocking/orders", json={
            "budget": 1000, "items": [{"sku": "GSK-203", "quantity": quantity}],
        })
        assert response.status_code == 422

    def test_client_supplied_price_is_ignored(self, client):
        response = client.post("/api/restocking/orders", json={
            "budget": 1000,
            "items": [{"sku": "GSK-203", "quantity": 10, "unit_cost": 0.01}],
        })

        assert response.status_code == 201
        order = response.json()
        # Server price 9.80, not the 0.01 the client sent
        assert order["items"][0]["unit_cost"] == 9.8
        assert order["total_value"] == pytest.approx(98.0)

    def test_existing_orders_unaffected(self, client):
        before = len(client.get("/api/orders").json())
        summary_before = client.get("/api/dashboard/summary").json()

        client.post("/api/restocking/orders", json={
            "budget": 1000, "items": [{"sku": "GSK-203", "quantity": 10}],
        })

        assert len(client.get("/api/orders").json()) == before
        assert client.get("/api/dashboard/summary").json() == summary_before
