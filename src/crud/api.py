from fastapi import FastAPI, HTTPException, Depends
from celery.result import AsyncResult
from db.celery_app import (
    schedule_task,
    app as celery_app,
    restore_tasks_from_db,
    save_task_to_db,
)
from tasks.task import Task
from models.models import SessionLocal, init_db
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

app = FastAPI()

init_db()

# Dependency for database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Restore tasks from the database on startup
@app.on_event("startup")
async def startup_event():
    db = next(get_db())
    try:
        restore_tasks_from_db(db)
    finally:
        db.close()

# Endpoint to add a task
@app.post("/add-task/")
async def add_task(task: Task, db: Session = Depends(get_db)):
    try:
        # Save the task to the database
        save_task_to_db(task, db)
        # Schedule the task using the saved task's ID
        task_id = schedule_task(task, db)
        return {"task_id": task_id, "message": "Task added to the queue"}
    except SQLAlchemyError as e:
        print(e)
        raise HTTPException(
            status_code=500, detail="Failed to save task to the database"
        )

# Endpoint to remove a task
@app.delete("/remove-task/{task_id}")
async def remove_task(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    if result.state in ["PENDING", "RECEIVED"]:
        result.revoke(terminate=True)
        return {"message": f"Task {task_id} revoked"}
    raise HTTPException(status_code=404, detail=f"Task {task_id} cannot be revoked")

# Placeholder endpoint for clearing the queue
@app.post("/clear-queue/")
async def clear_queue():
    return {"message": "Manual queue clearing not implemented in Celery"}