import pytest
from unittest.mock import Mock, patch
from src.llm.playbook_generator import PlaybookGenerator
from src.llm.template_manager import TemplateManager


class TestPlaybookGenerator:
    """Test cases for PlaybookGenerator"""
    
    def test_init_with_openai(self):
        """Test initialization with OpenAI provider"""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test_key'}):
            generator = PlaybookGenerator(provider="openai")
            assert generator.provider == "openai"
            assert generator.api_key == "test_key"
    
    def test_init_with_anthropic(self):
        """Test initialization with Anthropic provider"""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test_key'}):
            generator = PlaybookGenerator(provider="anthropic")
            assert generator.provider == "anthropic"
            assert generator.api_key == "test_key"
    
    def test_extract_yaml_from_response(self):
        """Test YAML extraction from LLM response"""
        generator = PlaybookGenerator()
        
        # Test with yaml markers
        response = "Here's your playbook:\n```yaml\n---\n- name: test\n  hosts: all\n```"
        result = generator._extract_yaml_from_response(response)
        assert "name: test" in result
        
        # Test with generic markers
        response = "Here's your playbook:\n```\n---\n- name: test\n  hosts: all\n```"
        result = generator._extract_yaml_from_response(response)
        assert "name: test" in result
        
        # Test without markers
        response = "---\n- name: test\n  hosts: all"
        result = generator._extract_yaml_from_response(response)
        assert "name: test" in result
    
    def test_validate_playbook_safe(self):
        """Test validation of safe playbook"""
        generator = PlaybookGenerator()
        playbook_content = """
---
- name: Install nginx
  hosts: web_servers
  tasks:
    - name: Install nginx
      apt:
        name: nginx
        state: present
"""
        result = generator._validate_playbook(playbook_content, "medium")
        assert result["is_valid"] is True
        assert result["safety_score"] > 50.0
    
    def test_validate_playbook_dangerous(self):
        """Test validation of dangerous playbook"""
        generator = PlaybookGenerator()
        playbook_content = """
---
- name: Dangerous playbook
  hosts: all
  tasks:
    - name: Remove everything
      shell: rm -rf /
"""
        result = generator._validate_playbook(playbook_content, "medium")
        assert result["is_valid"] is False
        assert "Dangerous pattern detected" in result["errors"][0]
    
    def test_validate_playbook_invalid_yaml(self):
        """Test validation of invalid YAML"""
        generator = PlaybookGenerator()
        playbook_content = "invalid: yaml: content: ["
        result = generator._validate_playbook(playbook_content, "medium")
        assert result["is_valid"] is False
        assert "YAML parsing error" in result["errors"][0]


class TestTemplateManager:
    """Test cases for TemplateManager"""
    
    def test_initialize_default_templates(self):
        """Test initialization of default templates"""
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        manager = TemplateManager(mock_db)
        manager.initialize_default_templates()
        
        # Verify that templates were added
        assert mock_db.add.call_count == 2  # Two default templates
        mock_db.commit.assert_called_once()
    
    def test_create_template(self):
        """Test template creation"""
        mock_db = Mock()
        manager = TemplateManager(mock_db)
        
        template_data = {
            "name": "Test Template",
            "description": "Test description",
            "template_content": "---\n- name: test\n  hosts: all",
            "variables_schema": {"type": "object"}
        }
        
        result = manager.create_template(template_data)
        
        assert result.name == "Test Template"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
    
    def test_validate_variables_valid(self):
        """Test variable validation with valid data"""
        mock_db = Mock()
        mock_template = Mock()
        mock_template.variables_schema = {
            "type": "object",
            "properties": {
                "hosts": {"type": "string"},
                "port": {"type": "integer"}
            },
            "required": ["hosts"]
        }
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_template
        
        manager = TemplateManager(mock_db)
        variables = {"hosts": "web_servers", "port": 80}
        
        result = manager.validate_variables(1, variables)
        assert result["valid"] is True
        assert len(result["errors"]) == 0
    
    def test_validate_variables_invalid(self):
        """Test variable validation with invalid data"""
        mock_db = Mock()
        mock_template = Mock()
        mock_template.variables_schema = {
            "type": "object",
            "properties": {
                "hosts": {"type": "string"}
            },
            "required": ["hosts"]
        }
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_template
        
        manager = TemplateManager(mock_db)
        variables = {"port": 80}  # Missing required 'hosts'
        
        result = manager.validate_variables(1, variables)
        assert result["valid"] is False
        assert "Required field missing: hosts" in result["errors"][0]


if __name__ == "__main__":
    pytest.main([__file__]) 