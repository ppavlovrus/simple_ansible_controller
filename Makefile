.PHONY: all build run test lint format clean add-task generate-playbook list-templates render-template list-tasks get-task

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
	flake8 src/. tests/.

format:
	black src/. tests/.

clean:
	$(DOCKER_COMPOSE) $(DC_FILE) down --volumes --remove-orphans
	docker system prune -f

check: lint test

add-task:
	curl -X POST http://localhost:8000/add-task/ \
	-H "Content-Type: application/json" \
	-d '{"playbook_path": "/app/ansible_playbooks/example_playbook.yml", "inventory": "/app/ansible_playbooks/inventory", "run_time": "2024-11-01T12:00:00"}'

generate-playbook:
	@echo "Example: Generate a web server setup playbook"
	curl -X POST http://localhost:8000/generate-playbook/ \
	-H "Content-Type: application/json" \
	-d '{"description": "Install and configure nginx web server", "hosts": "web_servers", "inventory": "/app/ansible_playbooks/inventory", "run_time": "2024-11-01T12:00:00", "safety_level": "medium"}'

list-templates:
	curl -X GET http://localhost:8000/templates/

render-template:
	@echo "Example: Render template with variables"
	curl -X POST http://localhost:8000/templates/1/render \
	-H "Content-Type: application/json" \
	-d '{"hosts": "web_servers", "web_server": "nginx", "port": 80}'

list-tasks:
	curl -X GET http://localhost:8000/tasks/

get-task:
	@echo "Example: Get details of task ID 1"
	curl -X GET http://localhost:8000/tasks/1

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
	@echo "  make generate-playbook - Генерирует плейбук с помощью LLM"
	@echo "  make list-templates - Показывает доступные шаблоны"
	@echo "  make render-template - Рендерит шаблон с переменными"
	@echo "  make list-tasks   - Показывает все запланированные задачи"
	@echo "  make get-task     - Получает детали конкретной задачи"