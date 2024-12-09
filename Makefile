.PHONY: all build run test lint format clean add-task

DOCKER_COMPOSE = docker-compose
DC_FILE = -f docker-compose.yml

build:
	$(DOCKER_COMPOSE) $(DC_FILE) build

run:
	$(DOCKER_COMPOSE) $(DC_FILE) up

down:
	$(DOCKER_COMPOSE) $(DC_FILE) down

test:
	PYTHONPATH=./app pytest

lint:
	flake8 app/. tests/.

format:
	black app/. tests/.

clean:
	$(DOCKER_COMPOSE) $(DC_FILE) down --volumes --remove-orphans
	docker system prune -f

check: lint test

add-task:
	curl -X POST http://localhost:8000/add-task/ \
	-H "Content-Type: application/json" \
	-d '{"playbook_path": "/app/ansible_playbooks/example_playbook.yml", "inventory": "/app/ansible_playbooks/inventory", "run_time": "2024-11-01T12:00:00"}'

help:
	@echo "Usage:"
	@echo "  make build       - Сборка Docker контейнеров"
	@echo "  make run         - Запуск приложения"
	@echo "  make down        - Остановка и удаление контейнеров"
	@echo "  make test        - Запуск тестов"
	@echo "  make lint        - Запуск линтера flake8"
	@echo "  make format      - Форматирование кода black"
	@echo "  make clean       - Очистка системы от контейнеров и образов"
	@echo "  make check       - Запуск линтинга и тестов"
	@echo "  make add-task    - Добавляет задачу для выполнения плейбука в тестовых контейнерах"