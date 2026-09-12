# Ansible-контроллер с LLM

Платформа автоматизации Ansible, которая использует большие языковые модели (LLM) для
генерации плейбуков из описаний на естественном языке. Проект соединяет ИИ с классической
автоматизацией инфраструктуры.

*English version: [README.md](README.md)*

> **Статус проекта — прочитайте это первым.** Описанный ниже прототип уже удалён из
> кода: слои LLM-генерации, Celery и PostgreSQL убраны, ядро переписывается.
> **Команды из этого файла сейчас не работают.** README будет переписан по завершении
> перестройки. Проект
> переделывается в минималистичный Ansible-контроллер, рассчитанный на агентов: MCP как
> основной интерфейс, SQLite и asyncio вместо PostgreSQL/Redis/Celery и без генерации
> плейбуков через LLM (это работа вызывающего агента). Целевая концепция — проблема,
> потребители, схема работы, преимущества и компромиссы — в
> **[docs/ru/concept.md](docs/ru/concept.md)**.

## Возможности

- 🤖 **Генерация плейбуков ИИ**: плейбуки Ansible из описаний на естественном языке
- 🛡️ **Проверка безопасности**: встроенные проверки против опасных операций
- 📋 **Система шаблонов**: переиспользуемые шаблоны Jinja2 для типовых сценариев
- 🔄 **Планирование задач**: запуск плейбуков по расписанию через Celery
- 📊 **Управление задачами**: просмотр и управление запланированными задачами
- 🌐 **REST API**: полноценный REST API для интеграции с другими инструментами
- 💻 **CLI**: интерфейс командной строки
- 🐳 **Docker**: развёртывание в контейнерах через Docker Compose

## Поддерживаемые LLM-провайдеры

- OpenAI GPT-4
- Anthropic Claude
- Расширяется под другие провайдеры

## Быстрый старт

### Требования

- Docker и Docker Compose
- Ключ API OpenAI или Anthropic

### Установка

1. **Сгенерируйте локальные SSH-ключи:**
   ```bash
   make keygen
   ```
   Ключи никогда не коммитятся в репозиторий. Цель `make build` зависит от `keygen`,
   поэтому при первой сборке создаётся свежая пара ed25519: приватный ключ попадает в
   образ контроллера, публичный — в тестовый хост.

2. **Клонируйте и соберите проект:**
   ```bash
   make clean
   make build
   ```

3. **Настройте переменные окружения:**
   ```bash
   cp src/env.example src/.env
   # Отредактируйте src/.env, добавив ключи API
   ```

4. **Запустите приложение:**
   ```bash
   make run
   ```

5. **Откройте API:**
   - Документация API: http://localhost:8000/docs
   - Проверка состояния: http://localhost:8000/status

## Примеры использования

### Генерация плейбука через API

```bash
curl -X POST http://localhost:8000/generate-playbook/ \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Install and configure nginx web server with SSL",
    "hosts": "web_servers",
    "inventory": "/app/ansible_playbooks/inventory",
    "run_time": "2024-11-01T12:00:00",
    "safety_level": "medium"
  }'
```

### Работа через CLI

```bash
# Сгенерировать плейбук
python src/cli.py generate \
  --description "Install Docker and configure firewall" \
  --hosts "docker_hosts" \
  --inventory "/app/ansible_playbooks/inventory" \
  --safety-level high

# Показать доступные шаблоны
python src/cli.py list-templates

# Отрендерить шаблон
python src/cli.py render-template \
  --template-id 1 \
  --variables '{"hosts": "web_servers", "web_server": "nginx"}'
```

### Команды Make

```bash
# Сгенерировать плейбук для веб-сервера
make generate-playbook

# Показать шаблоны
make list-templates

# Отрендерить шаблон
make render-template
```

## Механизмы безопасности

В системе несколько уровней защиты:

- **Обнаружение опасных конструкций**: блокирует операции вроде `rm -rf`, `dd`, `mkfs`
- **Уровни безопасности**: строгость проверок настраивается (low/medium/high)
- **Валидация YAML**: проверяет, что сгенерированный плейбук корректен
- **Проверка прав**: контролирует использование `become` и shell-команд

## Архитектура проекта

- **FastAPI**: фреймворк REST API
- **Celery**: очередь задач и планирование
- **PostgreSQL**: база данных задач и шаблонов
- **Redis**: брокер сообщений для Celery
- **Ansible Runner**: движок выполнения плейбуков
- **Интеграция с LLM**: API OpenAI/Anthropic
- **Jinja2**: рендеринг шаблонов

## Эндпоинты API

- `POST /generate-playbook/` — сгенерировать плейбук через LLM
- `POST /add-task/` — добавить обычную задачу с плейбуком
- `DELETE /remove-task/{task_id}` — удалить запланированную задачу
- `GET /templates/` — список доступных шаблонов
- `POST /templates/` — создать шаблон
- `GET /templates/{id}` — получить шаблон
- `POST /templates/{id}/render` — отрендерить шаблон с переменными
- `DELETE /templates/{id}` — удалить шаблон

## Разработка

```bash
# Запустить тесты
make test

# Проверить линтером
make lint

# Отформатировать код
make format

# Проверить всё сразу
make check
```

## Переменные окружения

- `LLM_PROVIDER`: провайдер LLM (openai/anthropic)
- `OPENAI_API_KEY`: ключ API OpenAI
- `ANTHROPIC_API_KEY`: ключ API Anthropic
- `DATABASE_URL`: строка подключения к PostgreSQL
- `REDIS_URL`: строка подключения к Redis
