import os
import yaml
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from jinja2 import Template, Environment, FileSystemLoader
from sqlalchemy.orm import Session
from models.models import PlaybookTemplate
import logging

logger = logging.getLogger(__name__)


class TemplateManager:
    """Manage Jinja2 templates for Ansible playbook generation"""
    
    def __init__(self, db: Session):
        self.db = db
        self.env = Environment(loader=FileSystemLoader('.'))
        
        # Default templates
        self.default_templates = {
            "web_server": {
                "name": "Web Server Setup",
                "description": "Basic web server installation and configuration",
                "template_content": """
---
- name: Setup Web Server
  hosts: {{ hosts }}
  become: yes
  vars:
    web_server: {{ web_server | default('nginx') }}
    port: {{ port | default(80) }}
  
  tasks:
    - name: Update apt cache
      apt:
        update_cache: yes
      when: ansible_os_family == "Debian"
    
    - name: Install {{ web_server }}
      apt:
        name: "{{ web_server }}"
        state: present
      when: ansible_os_family == "Debian"
    
    - name: Start and enable {{ web_server }} service
      systemd:
        name: "{{ web_server }}"
        state: started
        enabled: yes
    
    - name: Configure firewall
      ufw:
        rule: allow
        port: "{{ port }}"
        proto: tcp
      when: ansible_os_family == "Debian"
""",
                "variables_schema": {
                    "type": "object",
                    "properties": {
                        "hosts": {"type": "string", "default": "web_servers"},
                        "web_server": {"type": "string", "enum": ["nginx", "apache2"], "default": "nginx"},
                        "port": {"type": "integer", "default": 80}
                    },
                    "required": ["hosts"]
                }
            },
            "database_server": {
                "name": "Database Server Setup",
                "description": "Database server installation and basic configuration",
                "template_content": """
---
- name: Setup Database Server
  hosts: {{ hosts }}
  become: yes
  vars:
    db_type: {{ db_type | default('postgresql') }}
    db_port: {{ db_port | default(5432) }}
  
  tasks:
    - name: Update apt cache
      apt:
        update_cache: yes
      when: ansible_os_family == "Debian"
    
    - name: Install {{ db_type }}
      apt:
        name: "{{ db_type }}"
        state: present
      when: ansible_os_family == "Debian"
    
    - name: Start and enable {{ db_type }} service
      systemd:
        name: "{{ db_type }}"
        state: started
        enabled: yes
    
    - name: Configure firewall for database
      ufw:
        rule: allow
        port: "{{ db_port }}"
        proto: tcp
      when: ansible_os_family == "Debian"
""",
                "variables_schema": {
                    "type": "object",
                    "properties": {
                        "hosts": {"type": "string", "default": "db_servers"},
                        "db_type": {"type": "string", "enum": ["postgresql", "mysql"], "default": "postgresql"},
                        "db_port": {"type": "integer", "default": 5432}
                    },
                    "required": ["hosts"]
                }
            }
        }
    
    def initialize_default_templates(self):
        """Initialize default templates in the database"""
        for template_key, template_data in self.default_templates.items():
            existing = self.db.query(PlaybookTemplate).filter(
                PlaybookTemplate.name == template_data["name"]
            ).first()
            
            if not existing:
                template = PlaybookTemplate(
                    name=template_data["name"],
                    description=template_data["description"],
                    template_content=template_data["template_content"],
                    variables_schema=template_data["variables_schema"],
                    created_at=datetime.now(),
                    is_active=True
                )
                self.db.add(template)
        
        self.db.commit()
        logger.info("Default templates initialized")
    
    def create_template(self, template_data: Dict[str, Any]) -> PlaybookTemplate:
        """Create a new template"""
        template = PlaybookTemplate(
            name=template_data["name"],
            description=template_data.get("description"),
            template_content=template_data["template_content"],
            variables_schema=template_data.get("variables_schema"),
            created_at=datetime.now(),
            is_active=True
        )
        
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        
        logger.info(f"Created template: {template.name}")
        return template
    
    def get_template(self, template_id: int) -> Optional[PlaybookTemplate]:
        """Get template by ID"""
        return self.db.query(PlaybookTemplate).filter(
            PlaybookTemplate.id == template_id,
            PlaybookTemplate.is_active == True
        ).first()
    
    def get_all_templates(self) -> List[PlaybookTemplate]:
        """Get all active templates"""
        return self.db.query(PlaybookTemplate).filter(
            PlaybookTemplate.is_active == True
        ).all()
    
    def update_template(self, template_id: int, template_data: Dict[str, Any]) -> Optional[PlaybookTemplate]:
        """Update an existing template"""
        template = self.get_template(template_id)
        if not template:
            return None
        
        for key, value in template_data.items():
            if hasattr(template, key):
                setattr(template, key, value)
        
        self.db.commit()
        self.db.refresh(template)
        
        logger.info(f"Updated template: {template.name}")
        return template
    
    def delete_template(self, template_id: int) -> bool:
        """Soft delete a template"""
        template = self.get_template(template_id)
        if not template:
            return False
        
        template.is_active = False
        self.db.commit()
        
        logger.info(f"Deleted template: {template.name}")
        return True
    
    def render_template(self, template_id: int, variables: Dict[str, Any]) -> str:
        """Render a template with variables"""
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")
        
        try:
            jinja_template = Template(template.template_content)
            return jinja_template.render(**variables)
        except Exception as e:
            logger.error(f"Template rendering error: {str(e)}")
            raise
    
    def validate_variables(self, template_id: int, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Validate variables against template schema"""
        template = self.get_template(template_id)
        if not template:
            return {"valid": False, "errors": ["Template not found"]}
        
        if not template.variables_schema:
            return {"valid": True, "errors": []}
        
        errors = []
        
        # Check required fields
        required_fields = template.variables_schema.get("required", [])
        for field in required_fields:
            if field not in variables:
                errors.append(f"Required field missing: {field}")
        
        # Check field types and constraints
        properties = template.variables_schema.get("properties", {})
        for field_name, field_value in variables.items():
            if field_name in properties:
                field_schema = properties[field_name]
                
                # Type validation
                expected_type = field_schema.get("type")
                if expected_type == "string" and not isinstance(field_value, str):
                    errors.append(f"Field {field_name} must be a string")
                elif expected_type == "integer" and not isinstance(field_value, int):
                    errors.append(f"Field {field_name} must be an integer")
                
                # Enum validation
                if "enum" in field_schema and field_value not in field_schema["enum"]:
                    errors.append(f"Field {field_name} must be one of: {field_schema['enum']}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        } 