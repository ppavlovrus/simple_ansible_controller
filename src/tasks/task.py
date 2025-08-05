from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any


class Task(BaseModel):
    playbook_path: str
    inventory: str
    run_time: datetime
    playbook_content: Optional[str] = None
    is_generated: bool = False
    generation_metadata: Optional[Dict[str, Any]] = None

    def calculate_eta(self):
        return (self.run_time - datetime.now()).total_seconds()


class PlaybookGenerationRequest(BaseModel):
    description: str = Field(..., description="Natural language description of what the playbook should do")
    hosts: str = Field(..., description="Target hosts or host group")
    inventory: str = Field(..., description="Path to inventory file")
    run_time: datetime = Field(..., description="When to execute the playbook")
    additional_context: Optional[str] = Field(None, description="Additional context or requirements")
    template_id: Optional[int] = Field(None, description="Optional template ID to use as base")
    variables: Optional[Dict[str, Any]] = Field(None, description="Variables to pass to the playbook")
    safety_level: str = Field("medium", description="Safety level: low, medium, high")


class PlaybookTemplateRequest(BaseModel):
    name: str = Field(..., description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    template_content: str = Field(..., description="Jinja2 template content")
    variables_schema: Optional[Dict[str, Any]] = Field(None, description="JSON schema for variables")


class PlaybookValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    safety_score: float = 0.0
    recommendations: List[str] = []
