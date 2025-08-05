# Module Documentation

This section provides detailed documentation for all modules and functions in the LLM-Powered Ansible Controller.

## Module Structure

```
src/
├── llm/                          # LLM Integration Modules
│   ├── playbook_generator.py     # AI-powered playbook generation
│   └── template_manager.py       # Template management system
├── crud/                         # API Layer
│   └── api.py                   # FastAPI application and endpoints
├── db/                          # Database and Task Management
│   └── celery_app.py            # Celery task management
├── models/                      # Data Models
│   └── models.py                # SQLAlchemy models
├── tasks/                       # Task Definitions
│   └── task.py                  # Pydantic models
├── config.py                    # Configuration management
└── cli.py                       # Command-line interface
```

## Module Documentation

### LLM Integration Modules

- **[PlaybookGenerator](llm/playbook_generator.md)** - AI-powered playbook generation
- **[TemplateManager](llm/template_manager.md)** - Template management system

### API Layer

- **[FastAPI Application](crud/api.md)** - REST API endpoints and application

### Data Layer

- **[Database Models](models/models.md)** - SQLAlchemy data models
- **[Celery Integration](db/celery_app.md)** - Task queue and execution

### Task Management

- **[Task Models](tasks/task.md)** - Pydantic request/response models

### Configuration

- **[Configuration Management](config.md)** - Environment and settings management

### CLI Interface

- **[Command Line Interface](cli.md)** - CLI implementation and commands

## Quick Reference

### Core Functions

| Module | Function | Purpose |
|--------|----------|---------|
| `playbook_generator.py` | `generate_playbook()` | Generate playbooks using LLM |
| `playbook_generator.py` | `_validate_playbook()` | Validate generated playbooks |
| `template_manager.py` | `render_template()` | Render templates with variables |
| `template_manager.py` | `validate_variables()` | Validate template variables |
| `api.py` | `generate_playbook()` | API endpoint for playbook generation |
| `celery_app.py` | `run_playbook()` | Execute Ansible playbooks |
| `config.py` | `validate()` | Validate configuration |

### Data Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `TaskModel` | Store Ansible tasks | `playbook_path`, `inventory`, `run_time` |
| `PlaybookTemplate` | Store templates | `name`, `template_content`, `variables_schema` |
| `Task` | API request model | `description`, `hosts`, `inventory` |
| `PlaybookGenerationRequest` | LLM generation request | `description`, `safety_level` |

### Configuration Options

| Setting | Default | Purpose |
|---------|---------|---------|
| `LLM_PROVIDER` | `openai` | AI provider selection |
| `OPENAI_API_KEY` | None | OpenAI API key |
| `ANTHROPIC_API_KEY` | None | Anthropic API key |
| `DEFAULT_SAFETY_LEVEL` | `medium` | Default safety validation |
| `MAX_TOKENS` | `2000` | LLM response limit |
| `TEMPERATURE` | `0.3` | LLM creativity level |

## Development Guidelines

### Adding New Modules

1. **Create module file** in appropriate directory
2. **Add imports** to `__init__.py` files
3. **Update documentation** in this section
4. **Add tests** in `tests/` directory
5. **Update requirements** if needed

### Module Standards

- **Docstrings**: Use Google-style docstrings
- **Type Hints**: Include type annotations
- **Error Handling**: Comprehensive exception handling
- **Logging**: Use structured logging
- **Testing**: Unit tests for all functions

### Code Examples

```python
# Example module structure
"""
Module description.

This module provides functionality for...
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ExampleClass:
    """Example class description."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the class.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        logger.info("ExampleClass initialized")
    
    def example_method(self, param: str) -> Optional[str]:
        """Example method description.
        
        Args:
            param: Input parameter
            
        Returns:
            Processed result or None
            
        Raises:
            ValueError: If parameter is invalid
        """
        if not param:
            raise ValueError("Parameter cannot be empty")
        
        logger.debug(f"Processing parameter: {param}")
        return param.upper()
```

## Testing

Each module should have corresponding tests:

```python
# tests/test_example.py
import pytest
from unittest.mock import Mock, patch
from src.example_module import ExampleClass


class TestExampleClass:
    """Test cases for ExampleClass."""
    
    def test_init(self):
        """Test class initialization."""
        config = {"key": "value"}
        instance = ExampleClass(config)
        assert instance.config == config
    
    def test_example_method_valid(self):
        """Test method with valid input."""
        instance = ExampleClass({})
        result = instance.example_method("test")
        assert result == "TEST"
    
    def test_example_method_invalid(self):
        """Test method with invalid input."""
        instance = ExampleClass({})
        with pytest.raises(ValueError):
            instance.example_method("")
```

## Performance Considerations

### LLM Integration
- **Caching**: Cache LLM responses when possible
- **Rate Limiting**: Implement rate limiting for API calls
- **Async Processing**: Use async/await for I/O operations

### Database Operations
- **Connection Pooling**: Use connection pools
- **Batch Operations**: Batch database operations
- **Indexing**: Proper database indexing

### Template Rendering
- **Template Caching**: Cache compiled templates
- **Variable Validation**: Validate variables early
- **Memory Management**: Clean up large templates

## Security Considerations

### Input Validation
- **Sanitization**: Sanitize all inputs
- **Type Checking**: Validate data types
- **Size Limits**: Limit input sizes

### LLM Security
- **API Key Protection**: Secure API key storage
- **Response Validation**: Validate LLM responses
- **Dangerous Pattern Detection**: Block unsafe operations

### Database Security
- **SQL Injection**: Use parameterized queries
- **Access Control**: Implement proper access control
- **Data Encryption**: Encrypt sensitive data 