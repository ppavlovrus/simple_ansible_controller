# CLI Reference

## Overview

The LLM-Powered Ansible Controller provides a comprehensive command-line interface (CLI) for interacting with the system. The CLI is built using Click and offers an intuitive way to generate playbooks, manage templates, and control task execution.

## Installation

The CLI is included with the main application. To use it:

```bash
# From the project root
python src/cli.py --help

# Or make it executable
chmod +x src/cli.py
./src/cli.py --help
```

## Global Options

All commands support these global options:

- `--api-url TEXT`: API base URL (default: http://localhost:8000)
- `--help`: Show help message and exit

## Commands

### 1. Playbook Generation

#### `generate`

Generate an Ansible playbook using LLM from natural language description.

**Usage**:
```bash
python src/cli.py generate [OPTIONS]
```

**Options**:
- `-d, --description TEXT`: Natural language description of the playbook (required)
- `-h, --hosts TEXT`: Target hosts or host group (default: "all")
- `-i, --inventory TEXT`: Path to inventory file (required)
- `-t, --run-time TEXT`: When to execute (default: 5 minutes from now)
- `-s, --safety-level [low|medium|high]`: Safety level (default: "medium")
- `--api-url TEXT`: API base URL (default: http://localhost:8000)
- `--dry-run`: Generate playbook without scheduling

**Examples**:

```bash
# Basic playbook generation
python src/cli.py generate \
  --description "Install nginx web server with SSL" \
  --hosts "web_servers" \
  --inventory "/app/ansible_playbooks/inventory"

# High safety level with dry run
python src/cli.py generate \
  --description "Configure firewall rules" \
  --hosts "all" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high \
  --dry-run

# Custom execution time
python src/cli.py generate \
  --description "Update system packages" \
  --hosts "servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --run-time "2024-11-01T15:30:00"
```

**Output Example**:
```
✅ Playbook generated successfully!
Task ID: celery-task-uuid-12345
Safety Score: 85.0
📅 Scheduled for: 2024-11-01T15:30:00

📄 Generated Playbook:
==================================================
---
- name: Install nginx web server with SSL
  hosts: web_servers
  become: yes
  tasks:
    - name: Update apt cache
      apt:
        update_cache: yes
    - name: Install nginx
      apt:
        name: nginx
        state: present
    - name: Start and enable nginx service
      systemd:
        name: nginx
        state: started
        enabled: yes
```

### 2. Template Management

#### `list-templates`

List all available playbook templates.

**Usage**:
```bash
python src/cli.py list-templates [OPTIONS]
```

**Options**:
- `--api-url TEXT`: API base URL (default: http://localhost:8000)

**Example**:
```bash
python src/cli.py list-templates
```

**Output Example**:
```
📋 Available Templates:
==================================================
ID: 1
Name: Web Server Setup
Description: Basic web server installation and configuration
Created: 2024-01-01T12:00:00
------------------------------
ID: 2
Name: Database Server Setup
Description: Database server installation and basic configuration
Created: 2024-01-01T12:00:00
------------------------------
```

#### `render-template`

Render a template with variables.

**Usage**:
```bash
python src/cli.py render-template [OPTIONS]
```

**Options**:
- `-t, --template-id INTEGER`: Template ID (required)
- `-v, --variables TEXT`: Variables as JSON string
- `--api-url TEXT`: API base URL (default: http://localhost:8000)

**Examples**:

```bash
# Render with variables
python src/cli.py render-template \
  --template-id 1 \
  --variables '{"hosts": "web_servers", "web_server": "nginx", "port": 80}'

# Render without variables (uses defaults)
python src/cli.py render-template --template-id 1
```

**Output Example**:
```
✅ Template rendered successfully!

📄 Rendered Playbook:
==================================================
---
- name: Setup Web Server
  hosts: web_servers
  become: yes
  vars:
    web_server: nginx
    port: 80
  
  tasks:
    - name: Update apt cache
      apt:
        update_cache: yes
      when: ansible_os_family == "Debian"
    
    - name: Install nginx
      apt:
        name: "nginx"
        state: present
      when: ansible_os_family == "Debian"
    
    - name: Start and enable nginx service
      systemd:
        name: "nginx"
        state: started
        enabled: yes
    
    - name: Configure firewall
      ufw:
        rule: allow
        port: "80"
        proto: tcp
      when: ansible_os_family == "Debian"
```

### 3. Task Management

#### `list-tasks`

List all scheduled tasks.

**Usage**:
```bash
python src/cli.py list-tasks [OPTIONS]
```

**Options**:
- `--api-url TEXT`: API base URL (default: http://localhost:8000)
- `-d, --detailed`: Show detailed task information

**Example**:
```bash
# List all tasks
python src/cli.py list-tasks

# List tasks with detailed information
python src/cli.py list-tasks --detailed
```

**Output Example**:
```
📋 Found 2 tasks:
============================================================
ID: 1
Status: PENDING
Playbook: /app/ansible_playbooks/example_playbook.yml
Inventory: /app/ansible_playbooks/inventory
Run Time: 2024-11-01T12:00:00
Generated: No
----------------------------------------
ID: 2
Status: SUCCESS
Playbook: /tmp/generated_playbook_123456.yml
Inventory: /app/ansible_playbooks/inventory
Run Time: 2024-11-01T13:00:00
Generated: Yes
LLM Provider: openai
Validation Errors: 0
Playbook Content: 1024 characters
----------------------------------------
```

#### `get-task`

Get detailed information about a specific task.

**Usage**:
```bash
python src/cli.py get-task [OPTIONS]
```

**Options**:
- `-t, --task-id INTEGER`: Task ID (required)
- `--api-url TEXT`: API base URL (default: http://localhost:8000)

**Example**:
```bash
python src/cli.py get-task --task-id 1
```

**Output Example**:
```
📋 Task 1 Details:
==================================================
ID: 1
Status: SUCCESS
Playbook: /app/ansible_playbooks/example_playbook.yml
Inventory: /app/ansible_playbooks/inventory
Run Time: 2024-11-01T12:00:00
Generated: Yes
Safety Validated: Yes
LLM Provider: openai
Generated At: 2024-01-01T12:00:00

📄 Playbook Content:
==============================
---
- name: Install nginx web server
  hosts: web_servers
  become: yes
  tasks:
    - name: Install nginx
      apt:
        name: nginx
        state: present
```

#### `remove-task`

Remove a scheduled task.

**Usage**:
```bash
python src/cli.py remove-task [OPTIONS]
```

**Options**:
- `-t, --task-id TEXT`: Task ID (required)
- `--api-url TEXT`: API base URL (default: http://localhost:8000)

**Example**:
```bash
python src/cli.py remove-task --task-id "celery-task-uuid-12345"
```

**Output Example**:
```
✅ Task celery-task-uuid-12345 revoked
```

### 4. System Status

#### `status`

Check API status and connectivity.

**Usage**:
```bash
python src/cli.py status [OPTIONS]
```

**Options**:
- `--api-url TEXT`: API base URL (default: http://localhost:8000)

**Example**:
```bash
python src/cli.py status
```

**Output Example**:
```
✅ API is running
```

**Error Output Example**:
```
❌ API is not accessible: Connection refused
```

## Configuration

### Environment Variables

The CLI respects these environment variables:

- `ANSIBLE_CONTROLLER_API_URL`: Default API URL
- `ANSIBLE_CONTROLLER_API_KEY`: API key for authentication (future)

### Configuration File

Create a configuration file at `~/.ansible-controller/config.yaml`:

```yaml
api:
  base_url: "http://localhost:8000"
  timeout: 30
  retries: 3

defaults:
  safety_level: "medium"
  inventory: "/app/ansible_playbooks/inventory"
  hosts: "all"

output:
  format: "text"  # text, json, yaml
  verbose: false
  color: true
```

## Error Handling

### Common Errors

1. **Connection Errors**:
   ```
   ❌ API request failed: Connection refused
   ```
   - Check if the API server is running
   - Verify the API URL is correct

2. **Validation Errors**:
   ```
   ❌ Template rendering failed!
     - Required field missing: hosts
   ```
   - Check required parameters
   - Verify variable types

3. **LLM Errors**:
   ```
   ❌ Playbook generation failed!
     - OPENAI_API_KEY is required
   ```
   - Configure API keys
   - Check LLM provider settings

### Debug Mode

Enable debug output by setting the `DEBUG` environment variable:

```bash
DEBUG=1 python src/cli.py generate --description "test"
```

## Examples

### Complete Workflow

```bash
# 1. Check system status
python src/cli.py status

# 2. List available templates
python src/cli.py list-templates

# 3. Generate a custom playbook
python src/cli.py generate \
  --description "Install Docker and configure firewall rules" \
  --hosts "docker_hosts" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high

# 4. Render a template for comparison
python src/cli.py render-template \
  --template-id 1 \
  --variables '{"hosts": "web_servers", "web_server": "apache2"}'

# 5. Remove a task if needed
python src/cli.py remove-task --task-id "celery-task-uuid-12345"
```

### Batch Operations

```bash
# Generate multiple playbooks
for service in nginx apache mysql redis; do
  python src/cli.py generate \
    --description "Install and configure $service" \
    --hosts "${service}_servers" \
    --inventory "/app/ansible_playbooks/inventory" \
    --run-time "$(date -d '+1 hour' -Iseconds)"
done
```

### Integration with Scripts

```bash
#!/bin/bash
# deploy.sh - Deploy application using LLM-generated playbooks

echo "Generating deployment playbook..."
RESULT=$(python src/cli.py generate \
  --description "Deploy application to production servers" \
  --hosts "production" \
  --inventory "/app/ansible_playbooks/inventory" \
  --dry-run)

if echo "$RESULT" | grep -q "✅ Playbook generated successfully"; then
    echo "Playbook generated successfully"
    TASK_ID=$(echo "$RESULT" | grep "Task ID:" | cut -d' ' -f3)
    echo "Task ID: $TASK_ID"
else
    echo "Failed to generate playbook"
    exit 1
fi
```

## Best Practices

### 1. Safety Levels

- Use `--safety-level high` for production environments
- Use `--dry-run` to preview generated playbooks
- Review generated content before execution

### 2. Descriptions

- Be specific and detailed in descriptions
- Include OS and version requirements
- Mention security considerations

### 3. Templates

- Use templates for common patterns
- Create custom templates for your environment
- Validate template variables before rendering

### 4. Error Handling

- Always check command exit codes
- Use debug mode for troubleshooting
- Monitor task execution status

## Troubleshooting

### Common Issues

1. **API Connection Issues**:
   ```bash
   # Check if API is running
   curl http://localhost:8000/health
   
   # Check Docker containers
   docker-compose ps
   ```

2. **LLM API Issues**:
   ```bash
   # Check environment variables
   echo $OPENAI_API_KEY
   
   # Test API key
   curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models
   ```

3. **Template Issues**:
   ```bash
   # List templates to verify IDs
   python src/cli.py list-templates
   
   # Check template content via API
   curl http://localhost:8000/templates/1
   ```

### Getting Help

```bash
# General help
python src/cli.py --help

# Command-specific help
python src/cli.py generate --help
python src/cli.py render-template --help
``` 