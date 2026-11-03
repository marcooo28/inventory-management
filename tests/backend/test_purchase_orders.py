"""
Tests for purchase order endpoints and the PO fields on the backlog.
"""


def po_payload(backlog_item_id, **overrides):
    payload = {
        "backlog_item_id": backlog_item_id,
        "supplier_name": "Acme Parts",
        "quantity": 350,
        "unit_cost": 12.5,
        "expected_delivery_date": "2025-11-15",
        "notes": "Rush order",
    }
    payload.update(overrides)
    return payload


def first_backlog_id(client):
    backlog = client.get("/api/backlog").json()
    assert len(backlog) > 0
    return backlog[0]["id"]


class TestPurchaseOrderEndpoints:
    """Test suite for /api/purchase-orders."""

    def test_create_purchase_order(self, client):
        backlog_id = first_backlog_id(client)

        response = client.post("/api/purchase-orders", json=po_payload(backlog_id))
        assert response.status_code == 201

        po = response.json()
        assert po["id"].startswith("PO-")
        assert po["backlog_item_id"] == backlog_id
        assert po["supplier_name"] == "Acme Parts"
        assert po["quantity"] == 350
        assert po["unit_cost"] == 12.5
        assert po["expected_delivery_date"] == "2025-11-15"
        assert po["status"] == "Pending"
        assert "T" in po["created_date"]

    def test_get_purchase_order_by_backlog_item(self, client):
        backlog_id = first_backlog_id(client)
        created = client.post("/api/purchase-orders", json=po_payload(backlog_id)).json()

        response = client.get(f"/api/purchase-orders/{backlog_id}")
        assert response.status_code == 200
        assert response.json() == created

    def test_backlog_reports_purchase_order(self, client):
        backlog_id = first_backlog_id(client)
        created = client.post("/api/purchase-orders", json=po_payload(backlog_id)).json()

        backlog = {b["id"]: b for b in client.get("/api/backlog").json()}
        assert backlog[backlog_id]["has_purchase_order"] is True
        assert backlog[backlog_id]["purchase_order_id"] == created["id"]

        # Other items are untouched
        for item_id, item in backlog.items():
            if item_id != backlog_id:
                assert item["has_purchase_order"] is False
                assert item["purchase_order_id"] is None

    def test_second_purchase_order_for_same_item_rejected(self, client):
        backlog_id = first_backlog_id(client)
        client.post("/api/purchase-orders", json=po_payload(backlog_id))

        response = client.post("/api/purchase-orders", json=po_payload(backlog_id))
        assert response.status_code == 409

    def test_create_purchase_order_unknown_backlog_item(self, client):
        response = client.post("/api/purchase-orders", json=po_payload("nonexistent-999"))
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_nonexistent_purchase_order(self, client):
        response = client.get(f"/api/purchase-orders/{first_backlog_id(client)}")
        assert response.status_code == 404

    def test_create_purchase_order_rejects_invalid_input(self, client):
        backlog_id = first_backlog_id(client)
        invalid_overrides = [
            {"supplier_name": ""},
            {"quantity": 0},
            {"unit_cost": -1},
            {"expected_delivery_date": "soon"},
        ]
        for override in invalid_overrides:
            response = client.post("/api/purchase-orders", json=po_payload(backlog_id, **override))
            assert response.status_code == 422, override
