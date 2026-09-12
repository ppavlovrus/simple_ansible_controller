# Руководство по конфигурации

*English version: [docs/configuration.md](../configuration.md)*

## Обзор

Ansible-контроллер с LLM использует централизованную систему конфигурации: переменные
окружения, файл конфигурации и валидацию при запуске. Здесь описаны все параметры и
рекомендации по их использованию.

## Источники конфигурации

Настройки читаются из следующих источников (в порядке убывания приоритета):

1. **Переменные окружения** (высший приоритет)
2. **Файл конфигурации** (`src/.env`)
3. **Значения по умолчанию** (низший приоритет)

## Переменные окружения

### Настройки LLM

| Переменная | По умолчанию | Описание | Обязательна |
|----------|---------|-------------|----------|
| `LLM_PROVIDER` | `openai` | Провайдер LLM: `openai` или `anthropic` | Нет |
| `OPENAI_API_KEY` | нет | Ключ API OpenAI | Да (при использовании OpenAI) |
| `ANTHROPIC_API_KEY` | нет | Ключ API Anthropic | Да (при использовании Anthropic) |
| `OPENAI_MODEL` | `gpt-4` | Название модели OpenAI | Нет |
| `ANTHROPIC_MODEL` | `claude-3-sonnet-20240229` | Название модели Anthropic | Нет |
| `MAX_TOKENS` | `2000` | Максимум токенов в ответе модели | Нет |
| `TEMPERATURE` | `0.3` | Уровень «креативности» модели (0.0–1.0) | Нет |

### Настройки базы данных

| Переменная | По умолчанию | Описание | Обязательна |
|----------|---------|-------------|----------|
| `DATABASE_URL` | `postgresql://user123:password@db:5432/tasksdb` | Строка подключения к PostgreSQL | Нет |
| `POSTGRES_USER` | `user123` | Пользователь PostgreSQL | Нет |
| `POSTGRES_PASSWORD` | `password` | Пароль PostgreSQL | Нет |
| `POSTGRES_DB` | `tasksdb` | Имя базы данных | Нет |
| `POSTGRES_HOST` | `db` | Хост PostgreSQL | Нет |
| `POSTGRES_PORT` | `5432` | Порт PostgreSQL | Нет |

### Настройки Redis

| Переменная | По умолчанию | Описание | Обязательна |
|----------|---------|-------------|----------|
| `REDIS_URL` | `redis://redis:6379/0` | Строка подключения к Redis | Нет |
| `REDIS_HOST` | `redis` | Хост Redis | Нет |
| `REDIS_PORT` | `6379` | Порт Redis | Нет |
| `REDIS_DB` | `0` | Номер базы Redis | Нет |

### Настройки приложения

| Переменная | По умолчанию | Описание | Обязательна |
|----------|---------|-------------|----------|
| `DEBUG` | `True` | Режим отладки | Нет |
| `LOG_LEVEL` | `INFO` | Уровень логирования | Нет |
| `DEFAULT_SAFETY_LEVEL` | `medium` | Уровень безопасности по умолчанию | Нет |
| `API_HOST` | `0.0.0.0` | Хост сервера API | Нет |
| `API_PORT` | `80` | Порт сервера API | Нет |

## Файл конфигурации

Создайте файл `.env` в каталоге `src/`:

```bash
# Скопировать пример конфигурации
cp src/env.example src/.env

# Отредактировать
nano src/.env
```

### Пример файла конфигурации

```bash
# Настройки LLM
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-api-key-here
ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key-here
OPENAI_MODEL=gpt-4
ANTHROPIC_MODEL=claude-3-sonnet-20240229
MAX_TOKENS=2000
TEMPERATURE=0.3

# Настройки базы данных
DATABASE_URL=postgresql://user123:password@db:5432/tasksdb
POSTGRES_USER=user123
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=tasksdb
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Настройки Redis
REDIS_URL=redis://redis:6379/0
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Настройки приложения
DEBUG=True
LOG_LEVEL=INFO
DEFAULT_SAFETY_LEVEL=medium
API_HOST=0.0.0.0
API_PORT=80
```

## Валидация конфигурации

Система проверяет конфигурацию при запуске:

```python
from src.config import Config

# Проверить конфигурацию
errors = Config.validate()
if errors:
    print("Configuration errors:")
    for error in errors:
        print(f"  - {error}")
```

### Правила валидации

1. **Провайдер LLM**: должен быть `openai` или `anthropic`
2. **Ключи API**: обязательны для выбранного провайдера
3. **DATABASE_URL**: должна быть корректной строкой подключения к PostgreSQL
4. **REDIS_URL**: должна быть корректной строкой подключения к Redis

## Классы конфигурации

### Класс Config

Основной класс конфигурации даёт централизованный доступ ко всем настройкам:

```python
from src.config import Config

# Доступ к значениям конфигурации
llm_provider = Config.LLM_PROVIDER
api_key = Config.OPENAI_API_KEY
database_url = Config.DATABASE_URL

# Получить настройки, относящиеся к LLM
llm_config = Config.get_llm_config()
# Возвращает: {
#     "provider": "openai",
#     "model": "gpt-4",
#     "max_tokens": 2000,
#     "temperature": 0.3,
#     "api_key": "sk-..."
# }
```

## Конфигурации под разные окружения

### Разработка

```bash
# .env.development
DEBUG=True
LOG_LEVEL=DEBUG
DEFAULT_SAFETY_LEVEL=low
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-test-key
```

### Промышленная эксплуатация

```bash
# .env.production
DEBUG=False
LOG_LEVEL=WARNING
DEFAULT_SAFETY_LEVEL=high
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-production-key
```

### Тестирование

```bash
# .env.testing
DEBUG=True
LOG_LEVEL=DEBUG
DEFAULT_SAFETY_LEVEL=low
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-test-key
DATABASE_URL=postgresql://test:test@localhost:5433/testdb
```

## Конфигурация Docker

### Окружение в Docker Compose

```yaml
# docker-compose.yml
version: '3.8'
services:
  web:
    build: ./src
    environment:
      - LLM_PROVIDER=${LLM_PROVIDER:-openai}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - DATABASE_URL=postgresql://user123:password@db:5432/tasksdb
      - REDIS_URL=redis://redis:6379/0
      - DEBUG=${DEBUG:-False}
    depends_on:
      - db
      - redis
```

### Файл окружения для Docker

```bash
# .env.docker
LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
DEBUG=False
LOG_LEVEL=INFO
```

## Настройки безопасности

### Управление ключами API

**Никогда не коммитьте ключи API в систему контроля версий:**

```bash
# .gitignore
.env
.env.local
.env.production
*.key
```

**Используйте средства управления секретами:**

```bash
# Секреты Docker
echo "your-api-key" | docker secret create openai_api_key -

# Секреты Kubernetes
kubectl create secret generic llm-keys \
  --from-literal=openai-api-key=your-key \
  --from-literal=anthropic-api-key=your-key
```

### Безопасность базы данных

```bash
# Используйте стойкие пароли
POSTGRES_PASSWORD=your-very-secure-password-here

# Включите SSL
DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require

# Используйте пул соединений
DATABASE_URL=postgresql://user:pass@host:5432/db?pool_size=20&max_overflow=30
```

### Безопасность Redis

```bash
# Включите аутентификацию
REDIS_URL=redis://:password@redis:6379/0

# Используйте SSL
REDIS_URL=rediss://:password@redis:6379/0

# Используйте пул соединений
REDIS_URL=redis://redis:6379/0?max_connections=20
```

## Рекомендации

### 1. Разделение окружений

- Держите отдельные файлы конфигурации для разных окружений
- Никогда не используйте боевые учётные данные в разработке
- Передавайте чувствительные данные через переменные окружения

### 2. Безопасность

- Храните ключи API безопасно (переменные окружения, менеджеры секретов)
- Используйте стойкие пароли для баз данных
- Включайте SSL/TLS для всех соединений
- Настраивайте контроль доступа

### 3. Производительность

- Задавайте адекватные размеры пулов соединений
- Устанавливайте разумные таймауты
- Кешируйте там, где это уместно
- Следите за потреблением ресурсов

### 4. Мониторинг

- Включите структурированное логирование
- Выставьте подходящие уровни логов
- Отслеживайте изменения конфигурации
- Контролируйте использование API и расходы

## Диагностика проблем

### Типичные ошибки конфигурации

1. **Отсутствует ключ API**:
   ```
   Configuration errors:
     - OPENAI_API_KEY is required when LLM_PROVIDER is 'openai'
   ```
   **Решение**: задайте нужную переменную окружения с ключом

2. **Некорректная DATABASE_URL**:
   ```
   Configuration errors:
     - Invalid DATABASE_URL format
   ```
   **Решение**: проверьте формат строки подключения к PostgreSQL

3. **Не удалось подключиться к Redis**:
   ```
   Configuration errors:
     - Cannot connect to Redis
   ```
   **Решение**: убедитесь, что Redis запущен и доступен

### Проверка конфигурации

```python
# Проверка валидации конфигурации
from src.config import Config

def test_config():
    errors = Config.validate()
    if errors:
        print("Configuration errors found:")
        for error in errors:
            print(f"  ❌ {error}")
        return False
    else:
        print("✅ Configuration is valid")
        return True

# Проверка настроек LLM
def test_llm_config():
    config = Config.get_llm_config()
    print(f"LLM Provider: {config['provider']}")
    print(f"Model: {config['model']}")
    print(f"API Key: {'Set' if config['api_key'] else 'Not set'}")
```

### Отладка переменных окружения

```bash
# Посмотреть переменные окружения
env | grep -E "(LLM|OPENAI|ANTHROPIC|DATABASE|REDIS)"

# Проверить загрузку конфигурации
python -c "
from src.config import Config
print(f'LLM Provider: {Config.LLM_PROVIDER}')
print(f'Database URL: {Config.DATABASE_URL}')
print(f'Debug Mode: {Config.DEBUG}')
"
```

## Продвинутая конфигурация

### Собственные провайдеры LLM

Чтобы добавить своего провайдера LLM:

```python
# src/config.py
class Config:
    # Добавить нового провайдера
    CUSTOM_LLM_API_KEY: Optional[str] = os.getenv("CUSTOM_LLM_API_KEY")

    @classmethod
    def validate(cls) -> list:
        errors = []
        # Добавить валидацию для своего провайдера
        if cls.LLM_PROVIDER == "custom" and not cls.CUSTOM_LLM_API_KEY:
            errors.append("CUSTOM_LLM_API_KEY is required for custom provider")
        return errors
```

### Собственные уровни безопасности

```python
# Определение собственных уровней безопасности
SAFETY_LEVELS = {
    "ultra": {
        "max_score": 100,
        "blocked_modules": ["shell", "command", "raw", "script"],
        "require_approval": True
    },
    "high": {
        "max_score": 90,
        "blocked_modules": ["shell", "command"],
        "require_approval": False
    },
    "medium": {
        "max_score": 70,
        "blocked_modules": [],
        "require_approval": False
    },
    "low": {
        "max_score": 50,
        "blocked_modules": [],
        "require_approval": False
    }
}
```

### Перезагрузка конфигурации

```python
# Горячая перезагрузка конфигурации
import os
from src.config import Config

def reload_config():
    """Reload configuration from environment"""
    # Сбросить закешированные значения
    Config._clear_cache()

    # Перепроверить
    errors = Config.validate()
    if errors:
        raise ValueError(f"Configuration errors: {errors}")

    return True
```
