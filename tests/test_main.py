import pytest
from fastapi.testclient import TestClient
from app.main import app  # main FASTAPI app

client = TestClient(app)


@pytest.mark.asyncio
async def test_add_task():
    response = await client.post(
        "/add-task/",
        json={
            "playbook_path": "path/to/playbook.yml",
            "inventory": "path/to/inventory.ini",
            "run_time": "2023-11-11T10:00:00",
        },
    )
    assert response.status_code == 200
    assert "task_id" in response.json()
    assert response.json()["message"] == "Task added to the queue"


@pytest.mark.asyncio
async def test_remove_task():
    # Add task
    response = await client.post(
        "/add-task/",
        json={
            "playbook_path": "path/to/playbook.yml",
            "inventory": "path/to/inventory.ini",
            "run_time": "2023-11-11T10:00:00",
        },
    )
    task_id = response.json()["task_id"]


    delete_response = await client.delete(f"/remove-task/{task_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == f"Task {task_id} revoked"
