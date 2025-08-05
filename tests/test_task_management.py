import pytest
from fastapi.testclient import TestClient
from src.crud.api import app
from src.models.models import TaskModel, SessionLocal
from datetime import datetime

client = TestClient(app)


@pytest.fixture
def db_session():
    """Create a database session for testing"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def sample_task(db_session):
    """Create a sample task for testing"""
    task = TaskModel(
        playbook_path="/test/playbook.yml",
        inventory="/test/inventory",
        run_time=datetime.now(),
        is_generated=False,
        safety_validated=False
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def test_list_tasks_empty(db_session):
    """Test listing tasks when database is empty"""
    response = client.get("/tasks/")
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True
    assert data["tasks"] == []
    assert data["total_count"] == 0


def test_list_tasks_with_data(db_session, sample_task):
    """Test listing tasks with data in database"""
    response = client.get("/tasks/")
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True
    assert len(data["tasks"]) == 1
    assert data["total_count"] == 1
    
    task = data["tasks"][0]
    assert task["id"] == sample_task.id
    assert task["playbook_path"] == sample_task.playbook_path
    assert task["inventory"] == sample_task.inventory
    assert task["is_generated"] == sample_task.is_generated
    assert task["safety_validated"] == sample_task.safety_validated


def test_get_task_success(db_session, sample_task):
    """Test getting a specific task"""
    response = client.get(f"/tasks/{sample_task.id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True
    assert data["task"]["id"] == sample_task.id
    assert data["task"]["playbook_path"] == sample_task.playbook_path


def test_get_task_not_found(db_session):
    """Test getting a task that doesn't exist"""
    response = client.get("/tasks/999")
    assert response.status_code == 404
    
    data = response.json()
    assert "not found" in data["detail"].lower()


def test_list_tasks_with_generated_playbook(db_session):
    """Test listing tasks with LLM-generated playbook"""
    task = TaskModel(
        playbook_path="/tmp/generated_playbook.yml",
        inventory="/test/inventory",
        run_time=datetime.now(),
        is_generated=True,
        safety_validated=True,
        playbook_content="---\n- name: Test playbook\n  hosts: all",
        generation_metadata={
            "provider": "openai",
            "timestamp": "2024-01-01T12:00:00"
        },
        validation_errors=[]
    )
    db_session.add(task)
    db_session.commit()
    
    response = client.get("/tasks/")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data["tasks"]) == 1
    
    task_data = data["tasks"][0]
    assert task_data["is_generated"] is True
    assert task_data["safety_validated"] is True
    assert task_data["generation_metadata"]["provider"] == "openai"


def test_get_task_with_full_details(db_session):
    """Test getting task with all details including playbook content"""
    task = TaskModel(
        playbook_path="/tmp/generated_playbook.yml",
        inventory="/test/inventory",
        run_time=datetime.now(),
        is_generated=True,
        safety_validated=True,
        playbook_content="---\n- name: Test playbook\n  hosts: all\n  tasks:\n    - name: Test task\n      debug:\n        msg: 'Hello World'",
        generation_metadata={
            "provider": "openai",
            "timestamp": "2024-01-01T12:00:00"
        },
        validation_errors=[]
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    
    response = client.get(f"/tasks/{task.id}")
    assert response.status_code == 200
    
    data = response.json()
    task_data = data["task"]
    assert task_data["playbook_content"] is not None
    assert "Test playbook" in task_data["playbook_content"]
    assert task_data["generation_metadata"]["provider"] == "openai"


def test_list_tasks_multiple(db_session):
    """Test listing multiple tasks"""
    # Create multiple tasks
    tasks = []
    for i in range(3):
        task = TaskModel(
            playbook_path=f"/test/playbook_{i}.yml",
            inventory="/test/inventory",
            run_time=datetime.now(),
            is_generated=i % 2 == 0,  # Alternate between generated and not
            safety_validated=i % 2 == 0
        )
        db_session.add(task)
        tasks.append(task)
    
    db_session.commit()
    
    response = client.get("/tasks/")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data["tasks"]) == 3
    assert data["total_count"] == 3
    
    # Verify all tasks are returned
    task_ids = [task["id"] for task in data["tasks"]]
    expected_ids = [task.id for task in tasks]
    assert set(task_ids) == set(expected_ids)


def test_task_status_integration(db_session, sample_task):
    """Test that task status is included in response"""
    response = client.get("/tasks/")
    assert response.status_code == 200
    
    data = response.json()
    task = data["tasks"][0]
    
    # Status should be present (even if UNKNOWN)
    assert "status" in task
    assert isinstance(task["status"], str)


if __name__ == "__main__":
    pytest.main([__file__]) 