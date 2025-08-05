# PlaybookGenerator Module

## Overview

The `PlaybookGenerator` class is the core component responsible for generating Ansible playbooks using Large Language Models (LLMs). It supports multiple LLM providers, includes comprehensive safety validation, and provides a robust interface for AI-powered infrastructure automation.

**File**: `src/llm/playbook_generator.py`

## Class Definition

```python
class PlaybookGenerator:
    """LLM-powered Ansible playbook generator"""
```

## Constructor

### `__init__(provider: str = "openai", api_key: Optional[str] = None)`

Initialize the PlaybookGenerator with specified LLM provider and API key.

**Parameters**:
- `provider` (str): LLM provider - "openai" or "anthropic" (default: "openai")
- `api_key` (Optional[str]): API key for the specified provider (default: None, reads from environment)

**Example**:
```python
# Initialize with OpenAI
generator = PlaybookGenerator(provider="openai", api_key="sk-...")

# Initialize with Anthropic
generator = PlaybookGenerator(provider="anthropic", api_key="sk-ant-...")

# Initialize with environment variable
generator = PlaybookGenerator(provider="openai")  # Uses OPENAI_API_KEY env var
```

## Core Methods

### `generate_playbook(request: Dict[str, Any]) -> Dict[str, Any]`

Main method for generating Ansible playbooks using LLM.

**Parameters**:
- `request` (Dict[str, Any]): Generation request containing:
  - `description` (str): Natural language description
  - `hosts` (str): Target hosts or host group
  - `additional_context` (str, optional): Additional requirements
  - `safety_level` (str, optional): Safety validation level

**Returns**:
- `Dict[str, Any]`: Generation result containing:
  - `playbook_content` (str): Generated YAML playbook
  - `is_valid` (bool): Validation status
  - `validation_errors` (List[str]): List of validation errors
  - `warnings` (List[str]): List of warnings
  - `safety_score` (float): Safety score (0-100)
  - `generation_metadata` (Dict): Generation metadata

**Example**:
```python
request = {
    "description": "Install nginx web server with SSL",
    "hosts": "web_servers",
    "additional_context": "Use Ubuntu 20.04, enable firewall",
    "safety_level": "medium"
}

result = generator.generate_playbook(request)

if result["is_valid"]:
    print("Generated playbook:", result["playbook_content"])
    print("Safety score:", result["safety_score"])
else:
    print("Errors:", result["validation_errors"])
```

## LLM Provider Methods

### `_generate_with_openai(prompt: str) -> str`

Generate playbook using OpenAI API.

**Parameters**:
- `prompt` (str): Formatted prompt for the LLM

**Returns**:
- `str`: Raw LLM response

**Implementation Details**:
- Uses GPT-4 model
- Configurable temperature (0.3) and max tokens (2000)
- Includes system message for Ansible expertise
- Handles API errors gracefully

### `_generate_with_anthropic(prompt: str) -> str`

Generate playbook using Anthropic API.

**Parameters**:
- `prompt` (str): Formatted prompt for the LLM

**Returns**:
- `str`: Raw LLM response

**Implementation Details**:
- Uses Claude-3-Sonnet model
- Configurable temperature (0.3) and max tokens (2000)
- Handles API errors gracefully

## Utility Methods

### `_extract_yaml_from_response(response: str) -> str`

Extract YAML content from LLM response, handling various response formats.

**Parameters**:
- `response` (str): Raw LLM response

**Returns**:
- `str`: Extracted YAML content

**Supported Formats**:
- ```yaml ... ``` (YAML code blocks)
- ``` ... ``` (Generic code blocks)
- Raw YAML content

**Example**:
```python
response = """
Here's your playbook:

```yaml
---
- name: Install nginx
  hosts: web_servers
  tasks:
    - name: Install nginx
      apt:
        name: nginx
        state: present
```
"""

yaml_content = generator._extract_yaml_from_response(response)
# Returns: "---\n- name: Install nginx\n  hosts: web_servers\n..."
```

### `_validate_playbook(playbook_content: str, safety_level: str = "medium") -> Dict[str, Any]`

Validate generated playbook for safety and correctness.

**Parameters**:
- `playbook_content` (str): YAML playbook content
- `safety_level` (str): Safety validation level - "low", "medium", "high"

**Returns**:
- `Dict[str, Any]`: Validation result containing:
  - `is_valid` (bool): Overall validation status
  - `errors` (List[str]): List of validation errors
  - `warnings` (List[str]): List of warnings
  - `safety_score` (float): Safety score (0-100)

**Validation Checks**:

1. **YAML Syntax**: Validates YAML structure
2. **Dangerous Patterns**: Detects unsafe operations:
   - `rm -rf`
   - `dd if=`
   - `mkfs`
   - `fdisk`
   - `parted`
   - `shutdown`
   - `reboot`
   - `halt`
   - `poweroff`
   - `init 0`
   - `init 6`

3. **Required Fields**: Validates playbook structure:
   - Must be a list of plays
   - Each play must have `hosts` and `tasks` fields
   - Proper YAML structure

4. **Safety Level Specific**:
   - **High**: Blocks `become`, `shell`, `command` modules
   - **Medium**: Warns about `become` usage
   - **Low**: Minimal restrictions

**Example**:
```python
playbook = """
---
- name: Install nginx
  hosts: web_servers
  become: yes
  tasks:
    - name: Install nginx
      apt:
        name: nginx
        state: present
"""

result = generator._validate_playbook(playbook, "medium")
# Returns: {"is_valid": True, "safety_score": 95.0, "warnings": ["Play uses become"]}
```

### `generate_from_template(template_content: str, variables: Dict[str, Any]) -> str`

Generate playbook from Jinja2 template (utility method).

**Parameters**:
- `template_content` (str): Jinja2 template content
- `variables` (Dict[str, Any]): Template variables

**Returns**:
- `str`: Rendered playbook content

**Example**:
```python
template = """
---
- name: {{ playbook_name }}
  hosts: {{ hosts }}
  tasks:
    - name: Install {{ package }}
      apt:
        name: {{ package }}
        state: present
"""

variables = {
    "playbook_name": "Install nginx",
    "hosts": "web_servers",
    "package": "nginx"
}

result = generator.generate_from_template(template, variables)
```

## Configuration

### Base Prompt Template

The generator uses a predefined prompt template:

```python
self.base_prompt = """
You are an expert Ansible playbook developer. Create a safe and well-structured Ansible playbook based on the following requirements:

DESCRIPTION: {description}
HOSTS: {hosts}
ADDITIONAL CONTEXT: {additional_context}

Requirements:
1. Use only safe, idempotent operations
2. Include proper error handling and validation
3. Use handlers for service restarts
4. Include proper task names and descriptions
5. Follow Ansible best practices
6. Avoid dangerous operations like rm -rf, dd, mkfs, etc.
7. Use become: yes only when necessary
8. Include proper variable usage where appropriate

Generate a complete, valid YAML playbook that can be executed immediately.
"""
```

### Safety Configuration

**Dangerous Patterns**:
```python
self.dangerous_patterns = [
    "rm -rf",
    "dd if=",
    "mkfs",
    "fdisk",
    "parted",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6"
]
```

**Safety Scoring**:
- Base score: 100.0
- Dangerous pattern: -20.0 points each
- Become usage: -5.0 points
- High safety violations: -30.0 points
- Shell/command modules (high safety): -10.0 points

## Error Handling

### LLM API Errors

```python
try:
    response = openai.ChatCompletion.create(...)
except Exception as e:
    logger.error(f"OpenAI API error: {str(e)}")
    raise
```

### Validation Errors

```python
try:
    playbook_data = yaml.safe_load(playbook_content)
except yaml.YAMLError as e:
    errors.append(f"YAML parsing error: {str(e)}")
    safety_score = 0.0
```

### Generation Failures

Returns structured error response:
```python
return {
    "playbook_content": None,
    "is_valid": False,
    "validation_errors": [f"Generation failed: {str(e)}"],
    "warnings": [],
    "safety_score": 0.0,
    "generation_metadata": {
        "provider": self.provider,
        "timestamp": datetime.now().isoformat(),
        "error": str(e)
    }
}
```

## Usage Examples

### Basic Usage

```python
from src.llm.playbook_generator import PlaybookGenerator

# Initialize generator
generator = PlaybookGenerator(provider="openai")

# Generate playbook
request = {
    "description": "Install and configure nginx web server",
    "hosts": "web_servers",
    "additional_context": "Use Ubuntu 20.04",
    "safety_level": "medium"
}

result = generator.generate_playbook(request)

if result["is_valid"]:
    print("✅ Playbook generated successfully!")
    print(f"Safety Score: {result['safety_score']}")
    print(result["playbook_content"])
else:
    print("❌ Generation failed:")
    for error in result["validation_errors"]:
        print(f"  - {error}")
```

### High Safety Level

```python
request = {
    "description": "Configure firewall rules",
    "hosts": "all",
    "safety_level": "high"  # Strict validation
}

result = generator.generate_playbook(request)
# Will reject playbooks with become, shell, or command modules
```

### Error Handling

```python
try:
    result = generator.generate_playbook(request)
except Exception as e:
    print(f"Generation failed: {e}")
    # Handle specific error types
    if "API" in str(e):
        print("LLM API error - check API key and connectivity")
    elif "YAML" in str(e):
        print("YAML parsing error - check generated content")
```

## Testing

### Unit Tests

```python
import pytest
from unittest.mock import Mock, patch
from src.llm.playbook_generator import PlaybookGenerator

class TestPlaybookGenerator:
    def test_init_with_openai(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test_key'}):
            generator = PlaybookGenerator(provider="openai")
            assert generator.provider == "openai"
            assert generator.api_key == "test_key"
    
    def test_validate_playbook_safe(self):
        generator = PlaybookGenerator()
        playbook = """
        ---
        - name: Install nginx
          hosts: web_servers
          tasks:
            - name: Install nginx
              apt:
                name: nginx
                state: present
        """
        result = generator._validate_playbook(playbook, "medium")
        assert result["is_valid"] is True
        assert result["safety_score"] > 50.0
    
    def test_validate_playbook_dangerous(self):
        generator = PlaybookGenerator()
        playbook = """
        ---
        - name: Dangerous playbook
          hosts: all
          tasks:
            - name: Remove everything
              shell: rm -rf /
        """
        result = generator._validate_playbook(playbook, "medium")
        assert result["is_valid"] is False
        assert "Dangerous pattern detected" in result["errors"][0]
```

## Performance Considerations

### Caching

Consider implementing response caching for repeated requests:
```python
import hashlib
import json

def get_cache_key(request):
    return hashlib.md5(json.dumps(request, sort_keys=True).encode()).hexdigest()
```

### Rate Limiting

Implement rate limiting for LLM API calls:
```python
import time
from functools import wraps

def rate_limit(calls_per_minute=60):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Implement rate limiting logic
            time.sleep(60 / calls_per_minute)
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

### Async Processing

For high-throughput scenarios, consider async processing:
```python
import asyncio
import aiohttp

async def generate_playbook_async(self, request):
    # Async implementation
    pass
```

## Security Considerations

### Input Sanitization

- Validate all input parameters
- Sanitize natural language descriptions
- Limit input size and complexity

### API Key Security

- Store API keys securely (environment variables, secrets management)
- Rotate API keys regularly
- Monitor API usage and costs

### Response Validation

- Always validate LLM responses
- Check for malicious content
- Implement content filtering

### Access Control

- Implement proper authentication
- Log all generation requests
- Monitor for abuse patterns 