# LLM-Powered Ansible Controller

A modern Ansible automation platform that uses Large Language Models (LLMs) to generate Ansible playbooks from natural language descriptions. This project combines the power of AI with traditional infrastructure automation.

## Features

- 🤖 **AI-Powered Playbook Generation**: Generate Ansible playbooks using natural language descriptions
- 🛡️ **Safety Validation**: Built-in safety checks to prevent dangerous operations
- 📋 **Template System**: Reusable Jinja2 templates for common automation patterns
- 🔄 **Task Scheduling**: Schedule playbook execution with Celery
- 📊 **Task Management**: List, view, and manage scheduled tasks
- 🌐 **REST API**: Full REST API for integration with other tools
- 💻 **CLI Interface**: Command-line interface for easy interaction
- 🐳 **Docker Support**: Containerized deployment with Docker Compose

## Supported LLM Providers

- OpenAI GPT-4
- Anthropic Claude
- Extensible for other providers

## Quick Start

### Prerequisites

- Docker and Docker Compose
- OpenAI API key or Anthropic API key

### Setup

1. **Clone and build the project:**
   ```bash
   make clean
   make build
   ```

2. **Configure environment variables:**
   ```bash
   cp src/env.example src/.env
   # Edit src/.env with your API keys
   ```

3. **Start the application:**
   ```bash
   make run
   ```

4. **Access the API:**
   - API Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/status

## Usage Examples

### Generate a Playbook via API

```bash
curl -X POST http://localhost:8000/generate-playbook/ \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Install and configure nginx web server with SSL",
    "hosts": "web_servers",
    "inventory": "/app/ansible_playbooks/inventory",
    "run_time": "2024-11-01T12:00:00",
    "safety_level": "medium"
  }'
```

### Use the CLI

```bash
# Generate a playbook
python src/cli.py generate \
  --description "Install Docker and configure firewall" \
  --hosts "docker_hosts" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high

# List available templates
python src/cli.py list-templates

# Render a template
python src/cli.py render-template \
  --template-id 1 \
  --variables '{"hosts": "web_servers", "web_server": "nginx"}'
```

### Use Make Commands

```bash
# Generate a web server playbook
make generate-playbook

# List templates
make list-templates

# Render a template
make render-template
```

## Safety Features

The system includes multiple safety mechanisms:

- **Dangerous Pattern Detection**: Blocks operations like `rm -rf`, `dd`, `mkfs`
- **Safety Levels**: Configure validation strictness (low/medium/high)
- **YAML Validation**: Ensures generated playbooks are valid
- **Permission Checks**: Validates `become` usage and shell commands

## Project Architecture

- **FastAPI**: REST API framework
- **Celery**: Task queue and scheduling
- **PostgreSQL**: Database for tasks and templates
- **Redis**: Message broker for Celery
- **Ansible Runner**: Playbook execution engine
- **LLM Integration**: OpenAI/Anthropic API integration
- **Jinja2**: Template rendering engine

## API Endpoints

- `POST /generate-playbook/` - Generate playbook with LLM
- `POST /add-task/` - Add traditional playbook task
- `DELETE /remove-task/{task_id}` - Remove scheduled task
- `GET /templates/` - List available templates
- `POST /templates/` - Create new template
- `GET /templates/{id}` - Get template details
- `POST /templates/{id}/render` - Render template with variables
- `DELETE /templates/{id}` - Delete template

## Development

```bash
# Run tests
make test

# Lint code
make lint

# Format code
make format

# Check everything
make check
```

## Environment Variables

- `LLM_PROVIDER`: LLM provider (openai/anthropic)
- `OPENAI_API_KEY`: OpenAI API key
- `ANTHROPIC_API_KEY`: Anthropic API key
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string


