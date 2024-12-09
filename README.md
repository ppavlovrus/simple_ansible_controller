# Simple Ansible Console pet project
This is my simple ansible console pet project, 
i want to create som thing for managing ansible playbooks
like very-very simple AWX with control via REST API and from CLI in future

## Building project
To build project following commands:

make clean

make build

make run

## Stop running project
To stop running project can be used following command:

make down

## Check project
Command make check may be used to start linter

## Project architecture

Currently project contains data model for Ansible task, queue, powered by Celery module,
very simple ansible scripts starter and basic FastAPI configuration for adding-removing tasks.
Also present basic tests, example how to add task via REST API and docker compose configuration for 
@testing infrastructure"


