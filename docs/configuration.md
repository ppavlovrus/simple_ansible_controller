# Configuration Guide

## Overview

The LLM-Powered Ansible Controller uses a centralized configuration system that supports environment variables, configuration files, and runtime validation. This guide covers all configuration options and best practices.

## Configuration Sources

The system reads configuration from the following sources (in order of precedence):

1. **Environment Variables** (highest priority)
2. **Configuration File** (`src/.env`)
3. **Default Values** (lowest priority)

## Environment Variables

### LLM Configuration

| Variable | Default | Description | Required |
|----------|---------|-------------|----------|
| `LLM_PROVIDER` | `openai` | LLM provider: `openai` or `anthropic` | No |
| `OPENAI_API_KEY` | None | OpenAI API key | Yes (if using OpenAI) |
| `ANTHROPIC_API_KEY` | None | Anthropic API key | Yes (if using Anthropic) |
| `OPENAI_MODEL` | `gpt-4` | OpenAI model name | No |
| `ANTHROPIC_MODEL` | `claude-3-sonnet-20240229` | Anthropic model name | No |
| `MAX_TOKENS` | `2000` | Maximum tokens for LLM responses | No |
| `TEMPERATURE` | `0.3` | LLM creativity level (0.0-1.0) | No |

### Database Configuration

| Variable | Default | Description | Required |
|----------|---------|-------------|----------|
| `DATABASE_URL` | `postgresql://user123:password@db:5432/tasksdb` | PostgreSQL connection string | No |
| `POSTGRES_USER` | `user123` | PostgreSQL username | No |
| `POSTGRES_PASSWORD` | `password` | PostgreSQL password | No |
| `POSTGRES_DB` | `tasksdb` | PostgreSQL database name | No |
| `POSTGRES_HOST` | `db` | PostgreSQL host | No |
| `POSTGRES_PORT` | `5432` | PostgreSQL port | No |

### Redis Configuration

| Variable | Default | Description | Required |
|----------|---------|-------------|----------|
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string | No |
| `REDIS_HOST` | `redis` | Redis host | No |
| `REDIS_PORT` | `6379` | Redis port | No |
| `REDIS_DB` | `0` | Redis database number | No |

### Application Configuration

| Variable | Default | Description | Required |
|----------|---------|-------------|----------|
| `DEBUG` | `True` | Enable debug mode | No |
| `LOG_LEVEL` | `INFO` | Logging level | No |
| `DEFAULT_SAFETY_LEVEL` | `medium` | Default safety level | No |
| `API_HOST` | `0.0.0.0` | API server host | No |
| `API_PORT` | `80` | API server port | No |

## Configuration File

Create a `.env` file in the `src/` directory:

```bash
# Copy example configuration
cp src/env.example src/.env

# Edit configuration
nano src/.env
```

### Example Configuration File

```bash
# LLM Configuration
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-api-key-here
ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key-here
OPENAI_MODEL=gpt-4
ANTHROPIC_MODEL=claude-3-sonnet-20240229
MAX_TOKENS=2000
TEMPERATURE=0.3

# Database Configuration
DATABASE_URL=postgresql://user123:password@db:5432/tasksdb
POSTGRES_USER=user123
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=tasksdb
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Redis Configuration
REDIS_URL=redis://redis:6379/0
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Application Configuration
DEBUG=True
LOG_LEVEL=INFO
DEFAULT_SAFETY_LEVEL=medium
API_HOST=0.0.0.0
API_PORT=80
```

## Configuration Validation

The system automatically validates configuration on startup:

```python
from src.config import Config

# Validate configuration
errors = Config.validate()
if errors:
    print("Configuration errors:")
    for error in errors:
        print(f"  - {error}")
```

### Validation Rules

1. **LLM Provider**: Must be `openai` or `anthropic`
2. **API Keys**: Required for the selected provider
3. **Database URL**: Must be a valid PostgreSQL connection string
4. **Redis URL**: Must be a valid Redis connection string

## Configuration Classes

### Config Class

The main configuration class provides centralized access to all settings:

```python
from src.config import Config

# Access configuration values
llm_provider = Config.LLM_PROVIDER
api_key = Config.OPENAI_API_KEY
database_url = Config.DATABASE_URL

# Get LLM-specific configuration
llm_config = Config.get_llm_config()
# Returns: {
#     "provider": "openai",
#     "model": "gpt-4",
#     "max_tokens": 2000,
#     "temperature": 0.3,
#     "api_key": "sk-..."
# }
```

## Environment-Specific Configurations

### Development Environment

```bash
# .env.development
DEBUG=True
LOG_LEVEL=DEBUG
DEFAULT_SAFETY_LEVEL=low
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-test-key
```

### Production Environment

```bash
# .env.production
DEBUG=False
LOG_LEVEL=WARNING
DEFAULT_SAFETY_LEVEL=high
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-production-key
```

### Testing Environment

```bash
# .env.testing
DEBUG=True
LOG_LEVEL=DEBUG
DEFAULT_SAFETY_LEVEL=low
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-test-key
DATABASE_URL=postgresql://test:test@localhost:5433/testdb
```

## Docker Configuration

### Docker Compose Environment

```yaml
# docker-compose.yml
version: '3.8'
services:
  web:
    build: ./src
    environment:
      - LLM_PROVIDER=${LLM_PROVIDER:-openai}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - DATABASE_URL=postgresql://user123:password@db:5432/tasksdb
      - REDIS_URL=redis://redis:6379/0
      - DEBUG=${DEBUG:-False}
    depends_on:
      - db
      - redis
```

### Environment File for Docker

```bash
# .env.docker
LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
DEBUG=False
LOG_LEVEL=INFO
```

## Security Configuration

### API Key Management

**Never commit API keys to version control:**

```bash
# .gitignore
.env
.env.local
.env.production
*.key
```

**Use secrets management:**

```bash
# Docker secrets
echo "your-api-key" | docker secret create openai_api_key -

# Kubernetes secrets
kubectl create secret generic llm-keys \
  --from-literal=openai-api-key=your-key \
  --from-literal=anthropic-api-key=your-key
```

### Database Security

```bash
# Use strong passwords
POSTGRES_PASSWORD=your-very-secure-password-here

# Enable SSL
DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require

# Use connection pooling
DATABASE_URL=postgresql://user:pass@host:5432/db?pool_size=20&max_overflow=30
```

### Redis Security

```bash
# Enable authentication
REDIS_URL=redis://:password@redis:6379/0

# Use SSL
REDIS_URL=rediss://:password@redis:6379/0

# Use connection pooling
REDIS_URL=redis://redis:6379/0?max_connections=20
```

## Configuration Best Practices

### 1. Environment Separation

- Use different configuration files for different environments
- Never use production credentials in development
- Use environment variables for sensitive data

### 2. Security

- Store API keys securely (environment variables, secrets management)
- Use strong passwords for databases
- Enable SSL/TLS for all connections
- Implement proper access controls

### 3. Performance

- Configure appropriate connection pool sizes
- Set reasonable timeouts
- Use caching where appropriate
- Monitor resource usage

### 4. Monitoring

- Enable structured logging
- Set appropriate log levels
- Monitor configuration changes
- Track API usage and costs

## Troubleshooting

### Common Configuration Issues

1. **Missing API Key**:
   ```
   Configuration errors:
     - OPENAI_API_KEY is required when LLM_PROVIDER is 'openai'
   ```
   **Solution**: Set the required API key environment variable

2. **Invalid Database URL**:
   ```
   Configuration errors:
     - Invalid DATABASE_URL format
   ```
   **Solution**: Check PostgreSQL connection string format

3. **Redis Connection Failed**:
   ```
   Configuration errors:
     - Cannot connect to Redis
   ```
   **Solution**: Verify Redis is running and accessible

### Configuration Validation

```python
# Test configuration validation
from src.config import Config

def test_config():
    errors = Config.validate()
    if errors:
        print("Configuration errors found:")
        for error in errors:
            print(f"  ❌ {error}")
        return False
    else:
        print("✅ Configuration is valid")
        return True

# Test LLM configuration
def test_llm_config():
    config = Config.get_llm_config()
    print(f"LLM Provider: {config['provider']}")
    print(f"Model: {config['model']}")
    print(f"API Key: {'Set' if config['api_key'] else 'Not set'}")
```

### Environment Variable Debugging

```bash
# Check environment variables
env | grep -E "(LLM|OPENAI|ANTHROPIC|DATABASE|REDIS)"

# Test configuration loading
python -c "
from src.config import Config
print(f'LLM Provider: {Config.LLM_PROVIDER}')
print(f'Database URL: {Config.DATABASE_URL}')
print(f'Debug Mode: {Config.DEBUG}')
"
```

## Advanced Configuration

### Custom LLM Providers

To add custom LLM providers:

```python
# src/config.py
class Config:
    # Add new provider
    CUSTOM_LLM_API_KEY: Optional[str] = os.getenv("CUSTOM_LLM_API_KEY")
    
    @classmethod
    def validate(cls) -> list:
        errors = []
        # Add validation for custom provider
        if cls.LLM_PROVIDER == "custom" and not cls.CUSTOM_LLM_API_KEY:
            errors.append("CUSTOM_LLM_API_KEY is required for custom provider")
        return errors
```

### Custom Safety Levels

```python
# Define custom safety levels
SAFETY_LEVELS = {
    "ultra": {
        "max_score": 100,
        "blocked_modules": ["shell", "command", "raw", "script"],
        "require_approval": True
    },
    "high": {
        "max_score": 90,
        "blocked_modules": ["shell", "command"],
        "require_approval": False
    },
    "medium": {
        "max_score": 70,
        "blocked_modules": [],
        "require_approval": False
    },
    "low": {
        "max_score": 50,
        "blocked_modules": [],
        "require_approval": False
    }
}
```

### Configuration Reloading

```python
# Hot reload configuration
import os
from src.config import Config

def reload_config():
    """Reload configuration from environment"""
    # Clear cached values
    Config._clear_cache()
    
    # Revalidate
    errors = Config.validate()
    if errors:
        raise ValueError(f"Configuration errors: {errors}")
    
    return True
``` 