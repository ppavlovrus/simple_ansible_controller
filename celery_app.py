from celery import Celery
from datetime import datetime
from models import TaskModel, SessionLocal, init_db
from task import Task
from sqlalchemy.orm import Session
import ansible_runner

app = Celery(
    "tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0"
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def save_task_to_db(task: Task, db: Session):
    db_task = TaskModel(
        playbook_path=task.playbook_path,
        inventory=task.inventory,
        run_time=task.run_time
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task

def load_tasks_from_db(db: Session):
    return db.query(TaskModel).all()

def restore_tasks_from_db():
    db = SessionLocal()
    tasks = load_tasks_from_db(db)
    for task in tasks:
        schedule_task(task)

@app.task
def run_playbook(task_id: int):
    db = SessionLocal()
    try:
        # Извлечение задачи из БД
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            return f"Task {task_id} not found in database"

        playbook_path = task.playbook_path
        inventory = task.inventory
        print(f"Playbook started: {playbook_path} with inventory: {inventory} at {datetime.now()}")

        # Запуск плейбука
        response = ansible_runner.run(private_data_dir='.', playbook=playbook_path, inventory=inventory)

        if response.rc == 0:
            result_message = f"Executed playbook: {playbook_path} successfully"
        else:
            result_message = f"Failed to execute playbook: {playbook_path}"

        # Удаление задачи из БД по завершении
        db.delete(task)
        db.commit()

        return result_message
    finally:
        db.close()


def schedule_task(task: Task):
    db_task = next(get_db())
    db = db_task.__next__()  # Получаем объект сессии
    db_task = TaskModel(
        playbook_path=task.playbook_path,
        inventory=task.inventory,
        run_time=task.run_time
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)  # Обновляем db_task, чтобы получить его ID

    # Планируем выполнение задачи по ID из БД
    result = run_playbook.apply_async(args=[db_task.id], eta=task.run_time)
    return result.id