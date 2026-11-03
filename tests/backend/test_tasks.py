"""
Tests for task endpoints (list, create, delete, toggle).
"""


def create_task(client, **overrides):
    payload = {"title": "Review Q4 stock levels", "priority": "high", "dueDate": "2025-10-08"}
    payload.update(overrides)
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == 201
    return response.json()


class TestTasksEndpoints:
    """Test suite for /api/tasks."""

    def test_get_tasks_starts_empty(self, client):
        response = client.get("/api/tasks")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_task(self, client):
        task = create_task(client, title="  Call supplier  ")

        assert task["id"].startswith("api-")
        # Title is trimmed and new tasks start pending
        assert task["title"] == "Call supplier"
        assert task["priority"] == "high"
        assert task["dueDate"] == "2025-10-08"
        assert task["status"] == "pending"

    def test_get_tasks_newest_first(self, client):
        first = create_task(client, title="First")
        second = create_task(client, title="Second")

        data = client.get("/api/tasks").json()
        assert [t["id"] for t in data] == [second["id"], first["id"]]

    def test_create_task_default_priority(self, client):
        response = client.post("/api/tasks", json={"title": "No priority", "dueDate": "2025-10-08"})
        assert response.status_code == 201
        assert response.json()["priority"] == "medium"

    def test_create_task_rejects_blank_title(self, client):
        response = client.post("/api/tasks", json={"title": "", "dueDate": "2025-10-08"})
        assert response.status_code == 422

    def test_create_task_rejects_invalid_priority(self, client):
        response = client.post(
            "/api/tasks", json={"title": "X", "priority": "urgent", "dueDate": "2025-10-08"}
        )
        assert response.status_code == 422

    def test_create_task_rejects_invalid_date(self, client):
        response = client.post("/api/tasks", json={"title": "X", "dueDate": "next week"})
        assert response.status_code == 422

    def test_toggle_task(self, client):
        task = create_task(client)

        response = client.patch(f"/api/tasks/{task['id']}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        # Toggling again flips it back
        response = client.patch(f"/api/tasks/{task['id']}")
        assert response.json()["status"] == "pending"

    def test_delete_task(self, client):
        task = create_task(client)

        response = client.delete(f"/api/tasks/{task['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == task["id"]
        assert client.get("/api/tasks").json() == []

    def test_deleted_task_id_not_reused(self, client):
        task = create_task(client)
        client.delete(f"/api/tasks/{task['id']}")

        assert create_task(client)["id"] != task["id"]

    def test_toggle_nonexistent_task(self, client):
        response = client.patch("/api/tasks/api-999999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_nonexistent_task(self, client):
        response = client.delete("/api/tasks/api-999999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
