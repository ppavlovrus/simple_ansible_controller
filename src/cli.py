#!/usr/bin/env python3
"""
CLI interface for LLM-powered Ansible Controller
"""

import click
import requests
import json
import yaml
from datetime import datetime, timedelta
from typing import Dict, Any


@click.group()
def cli():
    """LLM-powered Ansible Controller CLI"""
    pass


@cli.command()
@click.option('--description', '-d', required=True, help='Natural language description of the playbook')
@click.option('--hosts', '-h', default='all', help='Target hosts or host group')
@click.option('--inventory', '-i', required=True, help='Path to inventory file')
@click.option('--run-time', '-t', help='When to execute (default: 5 minutes from now)')
@click.option('--safety-level', '-s', default='medium', type=click.Choice(['low', 'medium', 'high']), help='Safety level')
@click.option('--api-url', default='http://localhost:8000', help='API base URL')
@click.option('--dry-run', is_flag=True, help='Generate playbook without scheduling')
def generate(description, hosts, inventory, run_time, safety_level, api_url, dry_run):
    """Generate an Ansible playbook using LLM"""
    
    if not run_time:
        run_time = (datetime.now() + timedelta(minutes=5)).isoformat()
    
    request_data = {
        "description": description,
        "hosts": hosts,
        "inventory": inventory,
        "run_time": run_time,
        "safety_level": safety_level
    }
    
    try:
        response = requests.post(f"{api_url}/generate-playbook/", json=request_data)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("success"):
            click.echo("✅ Playbook generated successfully!")
            click.echo(f"Task ID: {result['task_id']}")
            click.echo(f"Safety Score: {result['safety_score']}")
            
            if result.get("warnings"):
                click.echo("⚠️  Warnings:")
                for warning in result["warnings"]:
                    click.echo(f"  - {warning}")
            
            if not dry_run:
                click.echo(f"📅 Scheduled for: {run_time}")
            else:
                click.echo("🔍 Dry run - playbook not scheduled")
            
            click.echo("\n📄 Generated Playbook:")
            click.echo("=" * 50)
            click.echo(result["playbook_content"])
            
        else:
            click.echo("❌ Playbook generation failed!")
            if result.get("errors"):
                for error in result["errors"]:
                    click.echo(f"  - {error}")
    
    except requests.exceptions.RequestException as e:
        click.echo(f"❌ API request failed: {e}")
    except Exception as e:
        click.echo(f"❌ Error: {e}")


@cli.command()
@click.option('--api-url', default='http://localhost:8000', help='API base URL')
def list_templates(api_url):
    """List available playbook templates"""
    
    try:
        response = requests.get(f"{api_url}/templates/")
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("success"):
            templates = result["templates"]
            if templates:
                click.echo("📋 Available Templates:")
                click.echo("=" * 50)
                for template in templates:
                    click.echo(f"ID: {template['id']}")
                    click.echo(f"Name: {template['name']}")
                    click.echo(f"Description: {template['description']}")
                    click.echo(f"Created: {template['created_at']}")
                    click.echo("-" * 30)
            else:
                click.echo("No templates found")
        else:
            click.echo("❌ Failed to list templates")
    
    except requests.exceptions.RequestException as e:
        click.echo(f"❌ API request failed: {e}")


@cli.command()
@click.option('--template-id', '-t', required=True, type=int, help='Template ID')
@click.option('--variables', '-v', help='Variables as JSON string')
@click.option('--api-url', default='http://localhost:8000', help='API base URL')
def render_template(template_id, variables, api_url):
    """Render a template with variables"""
    
    try:
        vars_dict = json.loads(variables) if variables else {}
        
        response = requests.post(f"{api_url}/templates/{template_id}/render", json=vars_dict)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("success"):
            click.echo("✅ Template rendered successfully!")
            click.echo("\n📄 Rendered Playbook:")
            click.echo("=" * 50)
            click.echo(result["rendered_content"])
        else:
            click.echo("❌ Template rendering failed!")
            if result.get("errors"):
                for error in result["errors"]:
                    click.echo(f"  - {error}")
    
    except json.JSONDecodeError:
        click.echo("❌ Invalid JSON in variables")
    except requests.exceptions.RequestException as e:
        click.echo(f"❌ API request failed: {e}")


@cli.command()
@click.option('--task-id', '-t', required=True, help='Task ID')
@click.option('--api-url', default='http://localhost:8000', help='API base URL')
def remove_task(task_id, api_url):
    """Remove a scheduled task"""
    
    try:
        response = requests.delete(f"{api_url}/remove-task/{task_id}")
        response.raise_for_status()
        
        result = response.json()
        click.echo(f"✅ {result['message']}")
    
    except requests.exceptions.RequestException as e:
        click.echo(f"❌ API request failed: {e}")


@cli.command()
@click.option('--api-url', default='http://localhost:8000', help='API base URL')
@click.option('--detailed', '-d', is_flag=True, help='Show detailed task information')
def list_tasks(api_url, detailed):
    """List all scheduled tasks"""
    
    try:
        response = requests.get(f"{api_url}/tasks/")
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("success"):
            tasks = result["tasks"]
            if tasks:
                click.echo(f"📋 Found {len(tasks)} tasks:")
                click.echo("=" * 60)
                for task in tasks:
                    click.echo(f"ID: {task['id']}")
                    click.echo(f"Status: {task['status']}")
                    click.echo(f"Playbook: {task['playbook_path']}")
                    click.echo(f"Inventory: {task['inventory']}")
                    click.echo(f"Run Time: {task['run_time']}")
                    click.echo(f"Generated: {'Yes' if task['is_generated'] else 'No'}")
                    
                    if detailed:
                        if task.get('generation_metadata'):
                            click.echo(f"LLM Provider: {task['generation_metadata'].get('provider', 'N/A')}")
                        if task.get('validation_errors'):
                            click.echo(f"Validation Errors: {len(task['validation_errors'])}")
                        if task.get('playbook_content'):
                            click.echo(f"Playbook Content: {len(task['playbook_content'])} characters")
                    
                    click.echo("-" * 40)
            else:
                click.echo("No tasks found")
        else:
            click.echo("❌ Failed to list tasks")
    
    except requests.exceptions.RequestException as e:
        click.echo(f"❌ API request failed: {e}")


@cli.command()
@click.option('--task-id', '-t', required=True, type=int, help='Task ID')
@click.option('--api-url', default='http://localhost:8000', help='API base URL')
def get_task(task_id, api_url):
    """Get detailed information about a specific task"""
    
    try:
        response = requests.get(f"{api_url}/tasks/{task_id}")
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("success"):
            task = result["task"]
            click.echo(f"📋 Task {task_id} Details:")
            click.echo("=" * 50)
            click.echo(f"ID: {task['id']}")
            click.echo(f"Status: {task['status']}")
            click.echo(f"Playbook: {task['playbook_path']}")
            click.echo(f"Inventory: {task['inventory']}")
            click.echo(f"Run Time: {task['run_time']}")
            click.echo(f"Generated: {'Yes' if task['is_generated'] else 'No'}")
            click.echo(f"Safety Validated: {'Yes' if task['safety_validated'] else 'No'}")
            
            if task.get('generation_metadata'):
                click.echo(f"LLM Provider: {task['generation_metadata'].get('provider', 'N/A')}")
                click.echo(f"Generated At: {task['generation_metadata'].get('timestamp', 'N/A')}")
            
            if task.get('validation_errors'):
                click.echo(f"Validation Errors: {len(task['validation_errors'])}")
                for error in task['validation_errors']:
                    click.echo(f"  - {error}")
            
            if task.get('playbook_content'):
                click.echo(f"\n📄 Playbook Content:")
                click.echo("=" * 30)
                click.echo(task['playbook_content'])
        else:
            click.echo("❌ Failed to get task details")
    
    except requests.exceptions.RequestException as e:
        click.echo(f"❌ API request failed: {e}")


@cli.command()
@click.option('--api-url', default='http://localhost:8000', help='API base URL')
def status(api_url):
    """Check API status"""
    
    try:
        response = requests.get(f"{api_url}/docs")
        if response.status_code == 200:
            click.echo("✅ API is running")
        else:
            click.echo("⚠️  API responded with unexpected status")
    
    except requests.exceptions.RequestException as e:
        click.echo(f"❌ API is not accessible: {e}")


if __name__ == '__main__':
    cli() 