from fastapi import FastAPI, HTTPException
from celery.result import AsyncResult
from celery_app import schedule_task, app as celery_app, restore_tasks_from_db, save_task_to_db
from task import Task
from models import TaskModel, SessionLocal, init_db
from sqlalchemy.orm import Session
from fastapi import Depends
from sqlalchemy.exc import SQLAlchemyError

app = FastAPI()

init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
async def startup_event():
    restore_tasks_from_db()

@app.post("/add-task/")
async def add_task(task: Task, db: Session = Depends(get_db)):
    try:
        db_task = save_task_to_db(task, db)
        task_id = schedule_task(task)
        return {"task_id": task_id, "message": "Task added to the queue"}
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Failed to save task to the database")

@app.delete("/remove-task/{task_id}")
async def remove_task(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    if result.state == "PENDING" or result.state == "RECEIVED":
        result.revoke(terminate=True)
        return {"message": f"Task {task_id} revoked"}
    raise HTTPException(status_code=404, detail=f"Task {task_id} cannot be revoked")

@app.post("/clear-queue/")
async def clear_queue():
    # Note: Clearing the whole queue directly isn't straightforward in Celery.
    # This feature should ideally be controlled by managing task states.
    return {"message": "Manual queue clearing not implemented in Celery"}