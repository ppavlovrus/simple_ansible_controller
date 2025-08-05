# API Reference

## Overview

The LLM-Powered Ansible Controller provides a comprehensive REST API for managing Ansible playbooks, templates, and task execution. All endpoints return JSON responses and use standard HTTP status codes.

**Base URL**: `http://localhost:8000`

**API Documentation**: `http://localhost:8000/docs` (Swagger UI)

## Authentication

Currently, the API does not require authentication. In production environments, consider implementing:
- API key authentication
- OAuth 2.0
- JWT tokens

## Common Response Format

### Success Response
```json
{
  "success": true,
  "data": {...},
  "message": "Operation completed successfully"
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error description",
  "details": {...}
}
```

## Endpoints

### 1. Playbook Generation

#### POST `/generate-playbook/`

Generate an Ansible playbook using LLM from natural language description.

**Request Body**:
```json
{
  "description": "Install and configure nginx web server with SSL",
  "hosts": "web_servers",
  "inventory": "/app/ansible_playbooks/inventory",
  "run_time": "2024-11-01T12:00:00",
  "additional_context": "Use Ubuntu 20.04, enable firewall",
  "safety_level": "medium",
  "variables": {
    "ssl_cert_path": "/etc/ssl/certs/nginx.crt"
  }
}
```

**Parameters**:
- `description` (string, required): Natural language description of the playbook
- `hosts` (string, required): Target hosts or host group
- `inventory` (string, required): Path to inventory file
- `run_time` (datetime, required): When to execute the playbook
- `additional_context` (string, optional): Additional requirements or context
- `safety_level` (string, optional): Safety level - "low", "medium", "high" (default: "medium")
- `variables` (object, optional): Variables to pass to the playbook

**Response**:
```json
{
  "success": true,
  "task_id": "celery-task-uuid",
  "playbook_content": "---\n- name: Install nginx...",
  "safety_score": 85.0,
  "warnings": ["Play uses become - ensure this is necessary"],
  "message": "Playbook generated and scheduled successfully"
}
```

**Error Responses**:
- `400 Bad Request`: Invalid request parameters
- `500 Internal Server Error`: LLM generation failed

### 2. Traditional Task Management

#### POST `/add-task/`

Add a traditional Ansible playbook task (non-LLM generated).

**Request Body**:
```json
{
  "playbook_path": "/app/ansible_playbooks/example_playbook.yml",
  "inventory": "/app/ansible_playbooks/inventory",
  "run_time": "2024-11-01T12:00:00"
}
```

**Response**:
```json
{
  "task_id": "celery-task-uuid",
  "message": "Task added to the queue"
}
```

#### GET `/tasks/`

List all tasks in the database.

**Response**:
```json
{
  "success": true,
  "tasks": [
    {
      "id": 1,
      "playbook_path": "/app/ansible_playbooks/example_playbook.yml",
      "inventory": "/app/ansible_playbooks/inventory",
      "run_time": "2024-11-01T12:00:00",
      "is_generated": false,
      "safety_validated": false,
      "status": "PENDING",
      "generation_metadata": null,
      "validation_errors": null
    }
  ],
  "total_count": 1,
  "message": "Found 1 tasks"
}
```

#### GET `/tasks/{task_id}`

Get details of a specific task.

**Parameters**:
- `task_id` (integer, required): Task ID

**Response**:
```json
{
  "success": true,
  "task": {
    "id": 1,
    "playbook_path": "/app/ansible_playbooks/example_playbook.yml",
    "inventory": "/app/ansible_playbooks/inventory",
    "run_time": "2024-11-01T12:00:00",
    "playbook_content": "---\n- name: Example playbook...",
    "is_generated": true,
    "safety_validated": true,
    "status": "SUCCESS",
    "generation_metadata": {
      "provider": "openai",
      "timestamp": "2024-01-01T12:00:00"
    },
    "validation_errors": []
  },
  "message": "Task 1 details retrieved successfully"
}
```

**Error Responses**:
- `404 Not Found`: Task not found

#### DELETE `/remove-task/{task_id}`

Remove a scheduled task.

**Parameters**:
- `task_id` (string, required): Task ID to remove

**Response**:
```json
{
  "message": "Task {task_id} revoked"
}
```

**Error Responses**:
- `404 Not Found`: Task not found or cannot be revoked

#### POST `/clear-queue/`

Clear the task queue (placeholder endpoint).

**Response**:
```json
{
  "message": "Manual queue clearing not implemented in Celery"
}
```

### 3. Template Management

#### GET `/templates/`

List all available playbook templates.

**Response**:
```json
{
  "success": true,
  "templates": [
    {
      "id": 1,
      "name": "Web Server Setup",
      "description": "Basic web server installation and configuration",
      "created_at": "2024-01-01T12:00:00",
      "variables_schema": {
        "type": "object",
        "properties": {
          "hosts": {"type": "string", "default": "web_servers"},
          "web_server": {"type": "string", "enum": ["nginx", "apache2"]}
        }
      }
    }
  ]
}
```

#### POST `/templates/`

Create a new playbook template.

**Request Body**:
```json
{
  "name": "Custom Template",
  "description": "Custom playbook template",
  "template_content": "---\n- name: {{ playbook_name }}\n  hosts: {{ hosts }}",
  "variables_schema": {
    "type": "object",
    "properties": {
      "playbook_name": {"type": "string"},
      "hosts": {"type": "string"}
    },
    "required": ["playbook_name", "hosts"]
  }
}
```

**Response**:
```json
{
  "success": true,
  "template_id": 2,
  "message": "Template 'Custom Template' created successfully"
}
```

#### GET `/templates/{template_id}`

Get details of a specific template.

**Parameters**:
- `template_id` (integer, required): Template ID

**Response**:
```json
{
  "success": true,
  "template": {
    "id": 1,
    "name": "Web Server Setup",
    "description": "Basic web server installation and configuration",
    "template_content": "---\n- name: Setup Web Server...",
    "variables_schema": {...},
    "created_at": "2024-01-01T12:00:00"
  }
}
```

#### POST `/templates/{template_id}/render`

Render a template with variables.

**Parameters**:
- `template_id` (integer, required): Template ID

**Request Body**:
```json
{
  "hosts": "web_servers",
  "web_server": "nginx",
  "port": 80
}
```

**Response**:
```json
{
  "success": true,
  "rendered_content": "---\n- name: Setup Web Server...",
  "message": "Template rendered successfully"
}
```

**Error Response** (validation failed):
```json
{
  "success": false,
  "errors": ["Required field missing: hosts"],
  "message": "Variable validation failed"
}
```

#### DELETE `/templates/{template_id}`

Delete a template (soft delete).

**Parameters**:
- `template_id` (integer, required): Template ID

**Response**:
```json
{
  "success": true,
  "message": "Template deleted successfully"
}
```

### 4. System Health

#### GET `/health`

Check system health and configuration status.

**Response**:
```json
{
  "status": "healthy",
  "config_errors": [],
  "llm_provider": "openai",
  "database_url": "db:5432/tasksdb"
}
```

**Error Response**:
```json
{
  "status": "unhealthy",
  "config_errors": ["OPENAI_API_KEY is required when LLM_PROVIDER is 'openai'"],
  "llm_provider": "openai",
  "database_url": "configured"
}
```

## Data Models

### PlaybookGenerationRequest

```python
class PlaybookGenerationRequest(BaseModel):
    description: str = Field(..., description="Natural language description")
    hosts: str = Field(..., description="Target hosts or host group")
    inventory: str = Field(..., description="Path to inventory file")
    run_time: datetime = Field(..., description="When to execute")
    additional_context: Optional[str] = Field(None, description="Additional context")
    template_id: Optional[int] = Field(None, description="Optional template ID")
    variables: Optional[Dict[str, Any]] = Field(None, description="Variables")
    safety_level: str = Field("medium", description="Safety level")
```

### Task

```python
class Task(BaseModel):
    playbook_path: str
    inventory: str
    run_time: datetime
    playbook_content: Optional[str] = None
    is_generated: bool = False
    generation_metadata: Optional[Dict[str, Any]] = None
```

### PlaybookTemplateRequest

```python
class PlaybookTemplateRequest(BaseModel):
    name: str = Field(..., description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    template_content: str = Field(..., description="Jinja2 template content")
    variables_schema: Optional[Dict[str, Any]] = Field(None, description="JSON schema")
```

## Error Codes

### HTTP Status Codes

- `200 OK`: Request successful
- `201 Created`: Resource created successfully
- `400 Bad Request`: Invalid request parameters
- `404 Not Found`: Resource not found
- `422 Unprocessable Entity`: Validation error
- `500 Internal Server Error`: Server error

### Common Error Messages

- `"Configuration errors: OPENAI_API_KEY is required"` - Missing API key
- `"Dangerous pattern detected: rm -rf"` - Safety validation failed
- `"YAML parsing error: ..."` - Invalid YAML content
- `"Template not found"` - Template ID doesn't exist
- `"Required field missing: hosts"` - Template variable validation failed

## Rate Limiting

Currently, no rate limiting is implemented. Consider implementing:
- Per-endpoint rate limits
- Per-user rate limits
- LLM API rate limiting

## Pagination

Template listing endpoints support pagination:

```json
{
  "success": true,
  "templates": [...],
  "pagination": {
    "page": 1,
    "per_page": 10,
    "total": 25,
    "pages": 3
  }
}
```

## WebSocket Support

Future enhancement: Real-time task status updates via WebSocket connections.

## API Versioning

Current version: v1

Versioning strategy: URL path versioning (`/api/v1/`)

## SDKs and Libraries

### Python Client Example

```python
import requests

class AnsibleControllerClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
    
    def generate_playbook(self, description, hosts, inventory, run_time):
        response = requests.post(f"{self.base_url}/generate-playbook/", json={
            "description": description,
            "hosts": hosts,
            "inventory": inventory,
            "run_time": run_time
        })
        return response.json()
    
    def list_templates(self):
        response = requests.get(f"{self.base_url}/templates/")
        return response.json()
```

### cURL Examples

```bash
# Generate a playbook
curl -X POST http://localhost:8000/generate-playbook/ \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Install nginx web server",
    "hosts": "web_servers",
    "inventory": "/app/ansible_playbooks/inventory",
    "run_time": "2024-11-01T12:00:00"
  }'

# List templates
curl -X GET http://localhost:8000/templates/

# Render template
curl -X POST http://localhost:8000/templates/1/render \
  -H "Content-Type: application/json" \
  -d '{"hosts": "web_servers", "web_server": "nginx"}'
``` 