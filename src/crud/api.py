from fastapi import FastAPI, HTTPException, Depends
from celery.result import AsyncResult
from db.celery_app import (
    schedule_task,
    app as celery_app,
    restore_tasks_from_db,
    save_task_to_db,
)
from tasks.task import Task, PlaybookGenerationRequest, PlaybookTemplateRequest, PlaybookValidationResult
from models.models import SessionLocal, init_db
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from llm.playbook_generator import PlaybookGenerator
from llm.template_manager import TemplateManager
from config import Config
import os

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
        return {"task_id": task_id, "message": "Task added " "to the queue"}
    except SQLAlchemyError as e:
        print(e)
        raise HTTPException(
            status_code=500, detail="Failed to save task " "to the database"
        )


# Endpoint to remove a task
@app.delete("/remove-task/{task_id}")
async def remove_task(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    if result.state in ["PENDING", "RECEIVED"]:
        result.revoke(terminate=True)
        return {"message": f"Task {task_id} revoked"}
    # fmt: off
    raise HTTPException(status_code=404,
                        detail=f"Task {task_id} cannot be revoked")


# fmt: on


# Placeholder endpoint for clearing the queue
@app.post("/clear-queue/")
async def clear_queue():
    return {"message": "Manual queue clearing not " "implemented in Celery"}


# LLM-based playbook generation endpoint
@app.post("/generate-playbook/")
async def generate_playbook(request: PlaybookGenerationRequest, db: Session = Depends(get_db)):
    try:
        # Validate configuration
        config_errors = Config.validate()
        if config_errors:
            raise HTTPException(status_code=500, detail=f"Configuration errors: {', '.join(config_errors)}")
        
        # Initialize LLM generator
        llm_config = Config.get_llm_config()
        generator = PlaybookGenerator(provider=llm_config["provider"], api_key=llm_config["api_key"])
        
        # Generate playbook
        generation_result = generator.generate_playbook(request.dict())
        
        if not generation_result["is_valid"]:
            return {
                "success": False,
                "errors": generation_result["validation_errors"],
                "warnings": generation_result["warnings"],
                "safety_score": generation_result["safety_score"]
            }
        
        # Create task with generated playbook
        task = Task(
            playbook_path=f"/tmp/generated_playbook_{request.run_time.timestamp()}.yml",
            inventory=request.inventory,
            run_time=request.run_time,
            playbook_content=generation_result["playbook_content"],
            is_generated=True,
            generation_metadata=generation_result["generation_metadata"]
        )
        
        # Save and schedule task
        save_task_to_db(task, db)
        task_id = schedule_task(task, db)
        
        return {
            "success": True,
            "task_id": task_id,
            "playbook_content": generation_result["playbook_content"],
            "safety_score": generation_result["safety_score"],
            "warnings": generation_result["warnings"],
            "message": "Playbook generated and scheduled successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Playbook generation failed: {str(e)}")


# Template management endpoints
@app.post("/templates/")
async def create_template(request: PlaybookTemplateRequest, db: Session = Depends(get_db)):
    try:
        template_manager = TemplateManager(db)
        template = template_manager.create_template(request.dict())
        return {
            "success": True,
            "template_id": template.id,
            "message": f"Template '{template.name}' created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template creation failed: {str(e)}")


@app.get("/templates/")
async def list_templates(db: Session = Depends(get_db)):
    try:
        template_manager = TemplateManager(db)
        templates = template_manager.get_all_templates()
        return {
            "success": True,
            "templates": [
                {
                    "id": t.id,
                    "name": t.name,
                    "description": t.description,
                    "created_at": t.created_at.isoformat(),
                    "variables_schema": t.variables_schema
                }
                for t in templates
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}")


@app.get("/templates/{template_id}")
async def get_template(template_id: int, db: Session = Depends(get_db)):
    try:
        template_manager = TemplateManager(db)
        template = template_manager.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        return {
            "success": True,
            "template": {
                "id": template.id,
                "name": template.name,
                "description": template.description,
                "template_content": template.template_content,
                "variables_schema": template.variables_schema,
                "created_at": template.created_at.isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get template: {str(e)}")


@app.post("/templates/{template_id}/render")
async def render_template(template_id: int, variables: dict, db: Session = Depends(get_db)):
    try:
        template_manager = TemplateManager(db)
        
        # Validate variables
        validation = template_manager.validate_variables(template_id, variables)
        if not validation["valid"]:
            return {
                "success": False,
                "errors": validation["errors"],
                "message": "Variable validation failed"
            }
        
        # Render template
        rendered_content = template_manager.render_template(template_id, variables)
        
        return {
            "success": True,
            "rendered_content": rendered_content,
            "message": "Template rendered successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template rendering failed: {str(e)}")


@app.delete("/templates/{template_id}")
async def delete_template(template_id: int, db: Session = Depends(get_db)):
    try:
        template_manager = TemplateManager(db)
        success = template_manager.delete_template(template_id)
        if not success:
            raise HTTPException(status_code=404, detail="Template not found")
        
        return {
            "success": True,
            "message": "Template deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template deletion failed: {str(e)}")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    config_errors = Config.validate()
    return {
        "status": "healthy" if not config_errors else "unhealthy",
        "config_errors": config_errors,
        "llm_provider": Config.LLM_PROVIDER,
        "database_url": Config.DATABASE_URL.split("@")[1] if "@" in Config.DATABASE_URL else "configured"
    }


# Initialize default templates on startup
@app.on_event("startup")
async def initialize_templates():
    db = next(get_db())
    try:
        template_manager = TemplateManager(db)
        template_manager.initialize_default_templates()
    finally:
        db.close()
