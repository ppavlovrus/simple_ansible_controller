# Examples and Tutorials

This section provides practical examples and tutorials for using the LLM-Powered Ansible Controller.

## Quick Start Examples

### 1. Basic Playbook Generation

Generate a simple web server setup playbook:

```bash
# Using CLI
python src/cli.py generate \
  --description "Install nginx web server" \
  --hosts "web_servers" \
  --inventory "/app/ansible_playbooks/inventory"

# Using API
curl -X POST http://localhost:8000/generate-playbook/ \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Install nginx web server",
    "hosts": "web_servers",
    "inventory": "/app/ansible_playbooks/inventory",
    "run_time": "2024-11-01T12:00:00"
  }'
```

### 2. Task Management

List and manage scheduled tasks:

```bash
# List all tasks
python src/cli.py list-tasks

# List tasks with detailed information
python src/cli.py list-tasks --detailed

# Get details of a specific task
python src/cli.py get-task --task-id 1

# Remove a task
python src/cli.py remove-task --task-id "celery-task-uuid-12345"

# Using API
curl -X GET http://localhost:8000/tasks/
curl -X GET http://localhost:8000/tasks/1
curl -X DELETE http://localhost:8000/remove-task/celery-task-uuid-12345
```

**Expected Output**:
```yaml
---
- name: Install nginx web server
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

### 2. Database Server Setup

Generate a database server configuration:

```bash
python src/cli.py generate \
  --description "Install and configure PostgreSQL database server with SSL" \
  --hosts "db_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high
```

### 3. Security Hardening

Generate a security hardening playbook:

```bash
python src/cli.py generate \
  --description "Harden Ubuntu server security: configure firewall, disable root login, set up fail2ban" \
  --hosts "production_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high
```

## Template Examples

### 1. Using Built-in Templates

List available templates:
```bash
python src/cli.py list-templates
```

Render web server template:
```bash
python src/cli.py render-template \
  --template-id 1 \
  --variables '{"hosts": "web_servers", "web_server": "apache2", "port": 443}'
```

### 2. Creating Custom Templates

Create a custom template via API:

```bash
curl -X POST http://localhost:8000/templates/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Docker Host Setup",
    "description": "Setup Docker host with Docker Engine and Docker Compose",
    "template_content": "---\n- name: Setup Docker Host\n  hosts: {{ hosts }}\n  become: yes\n  tasks:\n    - name: Install Docker dependencies\n      apt:\n        name:\n          - apt-transport-https\n          - ca-certificates\n          - curl\n          - gnupg\n          - lsb-release\n        state: present\n    - name: Add Docker GPG key\n      apt_key:\n        url: https://download.docker.com/linux/ubuntu/gpg\n        state: present\n    - name: Add Docker repository\n      apt_repository:\n        repo: deb [arch=amd64] https://download.docker.com/linux/ubuntu {{ ansible_distribution_release }} stable\n        state: present\n    - name: Install Docker Engine\n      apt:\n        name: docker-ce\n        state: present\n    - name: Install Docker Compose\n      pip:\n        name: docker-compose\n        state: present\n    - name: Start and enable Docker service\n      systemd:\n        name: docker\n        state: started\n        enabled: yes\n    - name: Add user to docker group\n      user:\n        name: {{ docker_user | default(ansible_user) }}\n        groups: docker\n        append: yes",
    "variables_schema": {
      "type": "object",
      "properties": {
        "hosts": {"type": "string", "default": "docker_hosts"},
        "docker_user": {"type": "string"}
      },
      "required": ["hosts"]
    }
  }'
```

## Advanced Examples

### 1. Multi-Environment Deployment

Generate playbooks for different environments:

```bash
#!/bin/bash
# deploy.sh - Multi-environment deployment

ENVIRONMENTS=("development" "staging" "production")

for env in "${ENVIRONMENTS[@]}"; do
  echo "Generating deployment playbook for $env environment..."
  
  python src/cli.py generate \
    --description "Deploy application to $env environment with proper configuration" \
    --hosts "${env}_servers" \
    --inventory "/app/ansible_playbooks/inventory" \
    --safety-level "$([ "$env" = "production" ] && echo "high" || echo "medium")" \
    --run-time "$(date -d '+1 hour' -Iseconds)"
done
```

### 2. Batch Server Provisioning

Provision multiple server types:

```bash
#!/bin/bash
# provision.sh - Batch server provisioning

# Define server configurations
declare -A servers=(
  ["web"]="nginx apache2"
  ["db"]="postgresql mysql"
  ["cache"]="redis memcached"
  ["monitoring"]="prometheus grafana"
)

for server_type in "${!servers[@]}"; do
  services="${servers[$server_type]}"
  
  echo "Provisioning $server_type servers with services: $services"
  
  python src/cli.py generate \
    --description "Provision $server_type servers and install: $services" \
    --hosts "${server_type}_servers" \
    --inventory "/app/ansible_playbooks/inventory" \
    --additional-context "Use Ubuntu 20.04, configure firewall, set up monitoring"
done
```

### 3. Security Compliance

Generate compliance playbooks:

```bash
# PCI DSS Compliance
python src/cli.py generate \
  --description "Implement PCI DSS compliance measures: firewall rules, encryption, access controls, logging" \
  --hosts "pci_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high

# HIPAA Compliance
python src/cli.py generate \
  --description "Implement HIPAA compliance: data encryption, access controls, audit logging, backup procedures" \
  --hosts "hipaa_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high
```

## Complete Workflow Example

### End-to-End Task Management

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

# 4. List all tasks to see what's scheduled
python src/cli.py list-tasks

# 5. Get details of a specific task
python src/cli.py get-task --task-id 1

# 6. Render a template for comparison
python src/cli.py render-template \
  --template-id 1 \
  --variables '{"hosts": "web_servers", "web_server": "apache2"}'

# 7. Remove a task if needed
python src/cli.py remove-task --task-id "celery-task-uuid-12345"
```

## Integration Examples

### 1. CI/CD Pipeline Integration

GitHub Actions workflow:

```yaml
# .github/workflows/deploy.yml
name: Deploy with LLM-Generated Playbooks

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Generate deployment playbook
        run: |
          python src/cli.py generate \
            --description "Deploy application version ${{ github.sha }} to production" \
            --hosts "production" \
            --inventory "/app/ansible_playbooks/inventory" \
            --safety-level high \
            --dry-run
      
      - name: Execute deployment
        if: success()
        run: |
          python src/cli.py generate \
            --description "Deploy application version ${{ github.sha }} to production" \
            --hosts "production" \
            --inventory "/app/ansible_playbooks/inventory" \
            --safety-level high
```

### 2. Monitoring Integration

Generate monitoring setup:

```bash
# Prometheus + Grafana setup
python src/cli.py generate \
  --description "Install and configure Prometheus monitoring stack with Grafana dashboard" \
  --hosts "monitoring_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --additional-context "Configure node_exporter, alertmanager, and basic dashboards"

# ELK Stack setup
python src/cli.py generate \
  --description "Install and configure ELK stack (Elasticsearch, Logstash, Kibana) for log aggregation" \
  --hosts "logging_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --additional-context "Configure log shipping from application servers"
```

### 3. Kubernetes Integration

Generate Kubernetes cluster setup:

```bash
# Single-node Kubernetes
python src/cli.py generate \
  --description "Install single-node Kubernetes cluster with Docker runtime" \
  --hosts "k8s_master" \
  --inventory "/app/ansible_playbooks/inventory" \
  --additional-context "Use kubeadm, configure networking with Calico"

# Multi-node Kubernetes
python src/cli.py generate \
  --description "Install multi-node Kubernetes cluster with master and worker nodes" \
  --hosts "k8s_cluster" \
  --inventory "/app/ansible_playbooks/inventory" \
  --additional-context "Use kubeadm, configure HA master, add worker nodes"
```

## Troubleshooting Examples

### 1. Debugging Generation Issues

```bash
# Enable debug mode
DEBUG=1 python src/cli.py generate \
  --description "Install nginx" \
  --hosts "web_servers" \
  --inventory "/app/ansible_playbooks/inventory"

# Check API status
python src/cli.py status

# Validate configuration
python -c "
from src.config import Config
errors = Config.validate()
print('Configuration errors:', errors)
"
```

### 2. Handling Safety Validation

```bash
# Test with low safety level
python src/cli.py generate \
  --description "System maintenance tasks" \
  --hosts "maintenance_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level low

# Review generated playbook before execution
python src/cli.py generate \
  --description "System maintenance tasks" \
  --hosts "maintenance_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --dry-run
```

### 3. Template Variable Validation

```bash
# Test template with invalid variables
python src/cli.py render-template \
  --template-id 1 \
  --variables '{"port": "invalid_port"}'  # Should fail validation

# Test template with valid variables
python src/cli.py render-template \
  --template-id 1 \
  --variables '{"hosts": "web_servers", "web_server": "nginx", "port": 80}'
```

## Best Practices Examples

### 1. Production Deployment

```bash
# Production deployment with high safety
python src/cli.py generate \
  --description "Deploy application to production with zero-downtime deployment" \
  --hosts "production" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high \
  --additional-context "Use blue-green deployment, health checks, rollback capability"

# Review before execution
python src/cli.py generate \
  --description "Deploy application to production" \
  --hosts "production" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high \
  --dry-run
```

### 2. Disaster Recovery

```bash
# Backup and restore procedures
python src/cli.py generate \
  --description "Implement disaster recovery procedures: automated backups, restore testing, monitoring" \
  --hosts "dr_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high

# Failover procedures
python src/cli.py generate \
  --description "Implement failover procedures for high availability" \
  --hosts "ha_cluster" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high
```

### 3. Compliance and Auditing

```bash
# Audit trail setup
python src/cli.py generate \
  --description "Setup comprehensive audit logging and monitoring" \
  --hosts "audit_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high

# Compliance reporting
python src/cli.py generate \
  --description "Generate compliance reports and automated checks" \
  --hosts "compliance_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high
```

## Performance Examples

### 1. High-Performance Web Server

```bash
python src/cli.py generate \
  --description "Configure high-performance nginx web server with caching, compression, and load balancing" \
  --hosts "web_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --additional-context "Optimize for high traffic, enable gzip, configure caching headers"
```

### 2. Database Optimization

```bash
python src/cli.py generate \
  --description "Optimize PostgreSQL database for high performance and scalability" \
  --hosts "db_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --additional-context "Configure connection pooling, query optimization, monitoring"
```

### 3. Caching Layer

```bash
python src/cli.py generate \
  --description "Setup Redis caching layer with clustering and persistence" \
  --hosts "cache_servers" \
  --inventory "/app/ansible_playbooks/inventory" \
  --additional-context "Configure Redis cluster, enable persistence, setup monitoring"
```

These examples demonstrate the versatility and power of the LLM-Powered Ansible Controller for various infrastructure automation scenarios. 