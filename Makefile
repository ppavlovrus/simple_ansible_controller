.PHONY: all keygen build run down test lint format clean check help

DOCKER_COMPOSE = docker-compose
DC_FILE = -f docker-compose.yml

# SSH keys are never committed: generate them locally before building.
# The public key goes into the test hosts; the private one stays here for tests
# and local runs to reach them.
keygen:
	@test -f tests/fixtures/keys/id_rsa || ssh-keygen -t ed25519 -N '' -C ansible-controller -f tests/fixtures/keys/id_rsa
	@cp tests/fixtures/keys/id_rsa.pub ansible_test_host/keys/id_rsa.pub

build: keygen
	$(DOCKER_COMPOSE) $(DC_FILE) build

run:
	$(DOCKER_COMPOSE) $(DC_FILE) up

down:
	$(DOCKER_COMPOSE) $(DC_FILE) down

test:
	poetry run task tests

lint:
	poetry run task lint

format:
	poetry run task fmt

clean:
	$(DOCKER_COMPOSE) $(DC_FILE) down --volumes --remove-orphans
	docker system prune -f

check: lint test

help:
	@echo "Usage:"
	@echo "  make keygen      - Генерация SSH-ключей для контейнеров (локально, не в git)"
	@echo "  make build       - Сборка тестовых хостов"
	@echo "  make run         - Запуск тестовых хостов"
	@echo "  make down        - Остановка и удаление контейнеров"
	@echo "  make test        - Запуск тестов"
	@echo "  make lint        - Линтер ruff + mypy"
	@echo "  make format      - Форматирование кода ruff"
	@echo "  make clean       - Очистка системы от контейнеров и образов"
	@echo "  make check       - Запуск линтинга и тестов"