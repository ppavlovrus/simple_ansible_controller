import os
import yaml
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import openai
import anthropic
from jinja2 import Template
import logging

logger = logging.getLogger(__name__)


class PlaybookGenerator:
    """LLM-powered Ansible playbook generator"""
    
    def __init__(self, provider: str = "openai", api_key: Optional[str] = None):
        self.provider = provider
        self.api_key = api_key or os.getenv(f"{provider.upper()}_API_KEY")
        
        if provider == "openai":
            openai.api_key = self.api_key
        elif provider == "anthropic":
            self.client = anthropic.Anthropic(api_key=self.api_key)
        
        # Safety patterns to avoid dangerous operations
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
        
        # Base prompt template for playbook generation
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

    def generate_playbook(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an Ansible playbook using LLM"""
        try:
            # Prepare the prompt
            prompt = self.base_prompt.format(
                description=request.get("description", ""),
                hosts=request.get("hosts", "all"),
                additional_context=request.get("additional_context", "")
            )
            
            # Generate playbook content using LLM
            if self.provider == "openai":
                playbook_content = self._generate_with_openai(prompt)
            elif self.provider == "anthropic":
                playbook_content = self._generate_with_anthropic(prompt)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
            
            # Validate and clean the generated content
            playbook_content = self._extract_yaml_from_response(playbook_content)
            
            # Validate the playbook
            validation_result = self._validate_playbook(playbook_content, request.get("safety_level", "medium"))
            
            # Prepare response
            result = {
                "playbook_content": playbook_content,
                "is_valid": validation_result["is_valid"],
                "validation_errors": validation_result.get("errors", []),
                "warnings": validation_result.get("warnings", []),
                "safety_score": validation_result.get("safety_score", 0.0),
                "generation_metadata": {
                    "provider": self.provider,
                    "timestamp": datetime.now().isoformat(),
                    "request": request
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating playbook: {str(e)}")
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

    def _generate_with_openai(self, prompt: str) -> str:
        """Generate playbook using OpenAI API"""
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert Ansible playbook developer. Generate only valid YAML playbooks."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            raise

    def _generate_with_anthropic(self, prompt: str) -> str:
        """Generate playbook using Anthropic API"""
        try:
            response = self.client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=2000,
                temperature=0.3,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API error: {str(e)}")
            raise

    def _extract_yaml_from_response(self, response: str) -> str:
        """Extract YAML content from LLM response"""
        # Try to find YAML content between ```yaml and ``` markers
        if "```yaml" in response:
            start = response.find("```yaml") + 7
            end = response.find("```", start)
            if end != -1:
                return response[start:end].strip()
        
        # Try to find YAML content between ``` and ``` markers
        if "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            if end != -1:
                return response[start:end].strip()
        
        # If no markers found, return the whole response
        return response.strip()

    def _validate_playbook(self, playbook_content: str, safety_level: str = "medium") -> Dict[str, Any]:
        """Validate generated playbook for safety and correctness"""
        errors = []
        warnings = []
        safety_score = 100.0
        
        try:
            # Parse YAML
            playbook_data = yaml.safe_load(playbook_content)
            
            if not playbook_data:
                errors.append("Empty or invalid YAML content")
                return {"is_valid": False, "errors": errors, "warnings": warnings, "safety_score": 0.0}
            
            # Check for dangerous patterns
            playbook_str = str(playbook_data).lower()
            for pattern in self.dangerous_patterns:
                if pattern in playbook_str:
                    errors.append(f"Dangerous pattern detected: {pattern}")
                    safety_score -= 20.0
            
            # Check for required fields
            if not isinstance(playbook_data, list):
                errors.append("Playbook must be a list of plays")
            else:
                for i, play in enumerate(playbook_data):
                    if not isinstance(play, dict):
                        errors.append(f"Play {i} must be a dictionary")
                        continue
                    
                    if "hosts" not in play:
                        errors.append(f"Play {i} missing 'hosts' field")
                    
                    if "tasks" not in play:
                        errors.append(f"Play {i} missing 'tasks' field")
                    
                    # Check for become usage
                    if play.get("become", False):
                        warnings.append(f"Play {i} uses become - ensure this is necessary")
                        safety_score -= 5.0
            
            # Safety level specific checks
            if safety_level == "high":
                if "become" in playbook_str:
                    errors.append("High safety level: become operations not allowed")
                    safety_score -= 30.0
                
                if "shell" in playbook_str or "command" in playbook_str:
                    warnings.append("High safety level: shell/command modules detected")
                    safety_score -= 10.0
            
        except yaml.YAMLError as e:
            errors.append(f"YAML parsing error: {str(e)}")
            safety_score = 0.0
        
        is_valid = len(errors) == 0 and safety_score > 50.0
        
        return {
            "is_valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "safety_score": max(0.0, safety_score)
        }

    def generate_from_template(self, template_content: str, variables: Dict[str, Any]) -> str:
        """Generate playbook from Jinja2 template"""
        try:
            template = Template(template_content)
            return template.render(**variables)
        except Exception as e:
            logger.error(f"Template rendering error: {str(e)}")
            raise 