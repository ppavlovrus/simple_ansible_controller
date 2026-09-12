# LLM-Powered Ansible Controller Documentation

Welcome to the comprehensive documentation for the LLM-Powered Ansible Controller. This project combines traditional Ansible automation with cutting-edge Large Language Model (LLM) technology to enable natural language-driven infrastructure automation.

*Русская версия: [docs/ru/README.md](ru/README.md)*

## 📚 Documentation Structure

- **[Concept](concept.md)** - What the project is for: problem, consumers, target design, advantages and trade-offs
- **[Architecture Overview](architecture.md)** - System architecture and design patterns
- **[API Reference](api-reference.md)** - Complete REST API documentation
- **[CLI Reference](cli-reference.md)** - Command-line interface documentation
- **[Module Documentation](modules/)** - Detailed module and function documentation
- **[Configuration Guide](configuration.md)** - Environment and configuration setup
- **[Deployment Guide](deployment.md)** - Installation and deployment instructions
- **[Security Guide](security.md)** - Security considerations and best practices
- **[Examples](examples/)** - Usage examples and tutorials

## 🚀 Quick Start

1. **Setup Environment:**
   ```bash
   cp src/env.example src/.env
   # Edit src/.env with your API keys
   ```

2. **Build and Run:**
   ```bash
   make clean
   make build
   make run
   ```

3. **Generate Your First Playbook:**
   ```bash
   python src/cli.py generate \
     --description "Install nginx web server" \
     --hosts "web_servers" \
     --inventory "/app/ansible_playbooks/inventory"
   ```

## 🏗️ Project Structure

```
simple_ansible_controller/
├── src/                          # Main application source
│   ├── llm/                     # LLM integration modules
│   │   ├── playbook_generator.py # AI-powered playbook generation
│   │   └── template_manager.py   # Template management system
│   ├── crud/                    # API endpoints and CRUD operations
│   │   └── api.py              # FastAPI application
│   ├── db/                      # Database and task queue
│   │   └── celery_app.py       # Celery task management
│   ├── models/                  # Data models
│   │   └── models.py           # SQLAlchemy models
│   ├── tasks/                   # Task definitions
│   │   └── task.py             # Pydantic models
│   ├── config.py               # Configuration management
│   └── cli.py                  # Command-line interface
├── tests/                       # Test suite
├── docs/                        # Documentation
└── ansible_test_host/          # Test infrastructure
```

## 🔧 Core Components

### LLM Integration (`src/llm/`)
- **PlaybookGenerator**: AI-powered playbook generation using OpenAI/Anthropic
- **TemplateManager**: Jinja2 template system for reusable playbook patterns

### API Layer (`src/crud/`)
- **FastAPI Application**: REST API with automatic documentation
- **Endpoints**: Playbook generation, template management, task scheduling

### Data Layer (`src/models/`, `src/db/`)
- **SQLAlchemy Models**: Database schema for tasks and templates
- **Celery Integration**: Asynchronous task execution and scheduling

### Configuration (`src/config/`)
- **Environment Management**: Centralized configuration with validation
- **LLM Provider Support**: Multi-provider AI integration

## 🛡️ Safety Features

- **Dangerous Pattern Detection**: Blocks unsafe operations
- **Safety Levels**: Configurable validation strictness
- **YAML Validation**: Ensures generated playbooks are valid
- **Permission Checks**: Validates privilege escalation usage

## 📖 Next Steps

- Read the [Architecture Overview](architecture.md) to understand the system design
- Check the [API Reference](api-reference.md) for detailed endpoint documentation
- Explore [Examples](examples/) for practical usage scenarios
- Review [Security Guide](security.md) for best practices

## 🤝 Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines and contribution instructions.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details. 