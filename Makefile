.PHONY: all build run test lint format clean

DOCKER_COMPOSE = docker-compose
DC_FILE = -f docker-compose.yml

build:
	$(DOCKER_COMPOSE) $(DC_FILE) build

run:
	$(DOCKER_COMPOSE) $(DC_FILE) up

# Остановка и удаление контейнеров
down:
	$(DOCKER_COMPOSE) $(DC_FILE) down

# Запуск тестов
test:
	pytest

# Линтинг с помощью flake8
lint:
	flake8 .

# Форматирование кода с помощью black
format:
	black .

# Очистка Docker контейнеров и образов
clean:
	$(DOCKER_COMPOSE) $(DC_FILE) down --volumes --remove-orphans
	docker system prune -f

# Запуск всех проверок и тестов
check: lint test

# Помощь
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