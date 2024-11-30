# Simple Ansible Manager (SAM) Project Requirements

## Purpose of project

I want to improve my python developer skill and, maybe at some point, creaate project, which will be useful for other peoples in real tasks

## Functional requirements

- Run ansible playbooks
  - Install Ansible if needed
  - Run playbooks in pre-created Docker container, which will be created from Docker image
  - Run many playbooks simultaneously 
- Create workflow for playbooks
- Create schedules for playbooks 
- Control application via REST API
- Application should have command line interface for starting
- Application should have CI/CD pipeline on GitHub
- Application should have Docker compose configuration for starting and working
- Application should have tests 

## Non-functional requirements
- Application should be able to run 100 playbooks at same time

## Notes about running Ansible playbooks
Like other modern DevOps systems this one should use Docker contaainers 
