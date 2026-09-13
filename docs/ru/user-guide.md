# Руководство пользователя

Установка контроллера, подключение клиента и всё, что он умеет, — в том порядке,
в котором это понадобится.

*English version: [docs/user-guide.md](../user-guide.md)*

Все ответы ниже сняты с работающего сервера, а не написаны от руки. Метки времени
и идентификаторы будут другими, форма — той же.

## Что вы устанавливаете

Сервис, который по запросу выполняет плейбуки Ansible и хранит историю, логи и
артефакты каждого прогона. Основной интерфейс — MCP, то есть им напрямую
управляет ИИ-агент; когда сервис отдаёт HTTP, те же операции доступны и на
`/api/v1` — для человека с curl.

Это **тупой исполнитель**: он не пишет плейбуки, не выбирает хосты и не судит,
разумно ли запускать то, что ему дали. Решаете вы (или ваш агент), он выполняет и
записывает. Если вы ждали платформу, которая проверит вашу автоматизацию, — это
не она, и [концепция](concept.md) объясняет почему.

## 1. Установка

Три способа для трёх ситуаций.

### Из исходников, чтобы запускал клиент

Самый короткий путь и единственный без сетевой поверхности: процесс запускает сам
клиент и общается с ним через stdin/stdout.

```bash
git clone https://github.com/ppavlovrus/simple_ansible_controller
cd simple_ansible_controller
poetry install
poetry run ansible-mcp        # говорит на MCP через stdio, ctrl-c для остановки
```

Нужны Python 3.11 или новее и Poetry.

### Контейнером, чтобы отдавать по HTTP

Для агента на другой машине или нескольких клиентов на один контроллер.

```bash
docker build -f Containerfile -t ansible-mcp .
mkdir -p data && sudo chown 1000:1000 data     # образ работает под uid 1000

docker run -d --name ansible-mcp -p 8080:8080 \
  -v ./data:/data \
  -e ANSIBLE_MCP_API_KEY="$(openssl rand -hex 32)" \
  ansible-mcp
```

Ключ не опционален. Контейнер слушает не на loopback, а сервер скорее завершится,
чем поднимет эндпоинт, исполняющий плейбуки для любого, кто дотянулся до порта.

Проверьте, что поднялся, — этому эндпоинту токен не нужен:

```console
$ curl -s http://127.0.0.1:8080/healthz
{"status":"ok","version":"0.1.0","tasks":{"pending":0,"running":0,"success":0,"failed":0,"cancelled":0},"failed_calls":0}
```

`Containerfile.alpine` собирает тот же сервис в заметно меньший образ ценой musl;
размеры и то, когда обмен оправдан, — в [упаковке](../../packaging/README.md).

### deb-пакетом, чтобы работал как сервис

Для хоста, на котором контроллер должен жить между перезагрузками. Это же
единственная установка, где сможет работать изоляция прогонов в образе (ADR-0008).

```bash
packaging/build-deb.sh amd64                      # или arm64
sudo dpkg -i dist/ansible-mcp_0.1.0_amd64.deb
sudo editor /etc/ansible-mcp/ansible-mcp.env      # задайте ANSIBLE_MCP_API_KEY
sudo systemctl enable --now ansible-mcp
```

Настройки лежат в этом env-файле, а не в юните. Что именно ставится и что
выживает при удалении — в [упаковке](../../packaging/README.md).

## 2. Подключение клиента

Для stdio укажите клиенту команду:

```json
{
  "mcpServers": {
    "ansible-mcp": {
      "command": "poetry",
      "args": ["run", "ansible-mcp"],
      "env": { "ANSIBLE_MCP_DATA_DIR": "/home/you/.local/share/ansible-mcp" }
    }
  }
}
```

Для HTTP — URL и токен:

```json
{
  "mcpServers": {
    "ansible-mcp": {
      "type": "http",
      "url": "http://your-host:8080/mcp",
      "headers": { "Authorization": "Bearer ${ANSIBLE_MCP_API_KEY}" }
    }
  }
}
```

Другие варианты и готовый скилл, объясняющий агенту порядок работы, — в
[интеграции](../../integration/README.md).

## 3. Доступ к вашим хостам

Контроллер добирается до хостов так же, как Ansible: ключ или пароль плюс
решение про host keys. Спотыкаются все об одно: *где именно* должен лежать
доступ — домашний каталог сервисного пользователя не ваш.

[Доступ к хостам](connecting-hosts.md) разбирает это по способам установки, с
точными путями, правами и владельцами. Прочитайте до первого прогона на реальном
хосте.

## 4. Первый прогон, от начала до конца

Это и есть весь рабочий цикл. Вызывайте как инструменты из вашего клиента;
ответы — те, что сервер действительно вернул.

**Проверьте, что плейбук разбирается.** Ни к чему не подключается, ничего не
записывает:

```console
syntax_check_playbook(playbook: "---\n- name: Make sure nginx is installed\n  hosts: all\n  ...")

{"ok": true, "playbook_name": null, "truncated": false, "output": "playbook: playbook.yml"}
```

**Сохраните под именем**, чтобы следующие прогоны не тащили текст:

```console
save_playbook(name: "install-nginx", content: "...", description: "Installs nginx", tags: ["web"])

{"name": "install-nginx", "updated_at": "2026-09-12T18:38:15+00:00", "lines": 8}
```

**Настройте, откуда берутся хосты:**

```console
add_provider(name: "lab", plugin_type: "static", config: {"inventory": "[web]\nweb1.example.com\n"})

{"name": "lab", "plugin_type": "static", "usable": true}
```

**Спросите, во что это раскрывается**, пока ничего не запущено:

```console
get_inventory(provider: "lab")

{"provider": "lab", "total_lines": 2, "truncated": false, "inventory": "[web]\nweb1.example.com\n"}
```

**Сначала сухой прогон.** Он опрашивает хосты и ничего не меняет:

```console
run_playbook(playbook_name: "install-nginx", provider: "lab", check: true, diff: true)

{"task_id": "321e2d74...", "status": "pending", "check_mode": true,
 "hint": "poll get_task_status; read output with get_task_logs"}
```

**Опрашивайте до завершения.** Обратите внимание на `check_mode` в ответе:
успешный сухой прогон ничего не применил, и именно так вы отличаете одно от
другого:

```console
get_task_status(task_id: "321e2d74...")

{"task_id": "321e2d74...", "status": "success", "playbook_name": "install-nginx",
 "provider_name": "lab", "started_at": "...", "finished_at": "...", "exit_code": 0,
 "error_message": null, "check_mode": true, "diff_mode": true}
```

**Теперь запустите по-настоящему** — тот же вызов без `check` — и прочитайте
вывод:

```console
get_task_logs(task_id: "b4890876...", tail: 6)

{"task_id": "b4890876...", "returned_lines": 6, "next_line": 10,
 "may_have_more": false, "output": "ok: [web1] => {\n    \"msg\": \"...\"\n}\n\nPLAY RECAP ..."}
```

Вот и весь цикл: проверить, прогнать насухо, запустить, опросить, прочитать.

## Что он умеет

### Запустить плейбук

`run_playbook` принимает что запускать и где — ровно по одному из каждой пары:

| Что запускать | Где |
|---|---|
| `playbook` — сам YAML | `inventory` — текст инвентаря |
| `playbook_name` — что-то сохранённое здесь | `provider` — настроенный источник |

Передать оба из пары — отказ, а не выбор одного: прогон, который тихо ушёл не на
тот источник, хуже ошибки. Плейбук можно передавать как YAML-текст или как уже
разобранный список плеев.

Дополнительно: `variables` (это `--extra-vars`), `tags`, `check` (сухой прогон),
`diff`.

### Следить за прогоном

`get_task_status` отдаёт статус — `pending`, `running`, `success`, `failed`,
`cancelled` — с метками времени, кодом выхода и признаком сухого прогона.

`get_task_logs` отдаёт вывод, по умолчанию последние строки. Когда следите за
идущим прогоном, передавайте предыдущий `next_line` обратно как `after_line` —
получите только новое, а не тот же хвост снова.

`list_tasks` перечисляет недавние прогоны, новые первыми, с фильтром по статусу —
удобно для «идёт ли что-нибудь сейчас» и чтобы найти потерянный идентификатор.

### Остановить прогон

`cancel_task` требует `confirm=true`:

```console
cancel_task(task_id: "b4890876...")

{"error": "cancelling task b4890876... is destructive and was not confirmed.
           Re-issue the call with confirm=true if this is intended."}
```

Отмена на середине оставляет хосты в том состоянии, до которого дошёл плейбук:
уже применённые задачи не откатываются. Перезапуска нет — чтобы выполнить то же
снова, вызовите `run_playbook` ещё раз: получится новый прогон, а старый
останется в истории.

### Хранить плейбуки

`save_playbook`, `list_playbooks`, `get_playbook`, `delete_playbook`.

Сохранение новой версии под тем же именем не меняет уже сделанные прогоны: каждый
хранит свою копию именно того, что выполнял. Именно это позволяет сравнить два
прогона «одного и того же» плейбука спустя месяцы.

`get_playbook` возвращает первые 40 строк, если не передать `full=true`: длинный
плейбук в контексте агента редко бывает тем, что было нужно.

### Настроить источники хостов

`add_provider`, `list_providers`, `get_inventory`, `delete_provider`.

`static` — встроенный плагин: инвентарь, записанный в конфигурацию, или читаемый
из файла в момент прогона. Другие плагины регистрируются через группу entry
points `ansible_mcp.providers`; облачные — в планах, но не сделаны.

`list_providers` сообщает, работоспособен ли каждый, — провайдер, у которого
переехал файл, виден с описанием проблемы, а не падает посреди прогона.

**Credentials в конфигурацию провайдера не кладутся.** Называйте переменную
окружения — `{"token_env": "YC_TOKEN"}`, — а значение, похожее на секрет,
отвергается сразу.

### Проверить, не запуская

`syntax_check_playbook` разбирает плейбук — текст или сохранённый — и говорит,
валиден ли он: ни к чему не подключается и задачу не создаёт. Внутри — родной
`--syntax-check` Ansible, поэтому он ловит больше, чем проверка формы в
`save_playbook`.

Вопрос «а что он *сделает*» — это `run_playbook` с `check=true`: сухой прогон
подключается к хостам и сообщает, что изменилось бы.

## REST-поверхность, для людей и скриптов

Всё, что выше, идёт через агента. Когда контроллером нужно управлять самому, те
же операции доступны на `/api/v1` — на том же порту, что и `/mcp`, и за тем же
токеном. Основным интерфейсом остаётся MCP (ADR-0002); это дверь для curl, cron
и того, чем вы уже скриптуете.

Отдаётся только HTTP-транспортом. При работе через stdio порта нет, значит нет и
REST.

| Инструмент | Маршрут |
|---|---|
| `run_playbook` | `POST /api/v1/runs` |
| `get_task_status` | `GET /api/v1/runs/{id}` |
| `get_task_logs` | `GET /api/v1/runs/{id}/logs?tail=&after_line=` |
| `cancel_task` | `POST /api/v1/runs/{id}/cancel` |
| `list_tasks` | `GET /api/v1/runs?status=&limit=` |
| `save_playbook` | `PUT /api/v1/playbooks/{name}` |
| `list_playbooks` / `get_playbook` | `GET /api/v1/playbooks` / `GET /api/v1/playbooks/{name}?full=` |
| `delete_playbook` | `DELETE /api/v1/playbooks/{name}` |
| `syntax_check_playbook` | `POST /api/v1/syntax-checks` |
| `add_provider` / `list_providers` | `PUT /api/v1/providers/{name}` / `GET /api/v1/providers` |
| `get_inventory` | `GET /api/v1/providers/{name}/inventory?full=` |
| `delete_provider` | `DELETE /api/v1/providers/{name}` |

Полный цикл против сервера, запущенного с `ANSIBLE_MCP_API_KEY=s3cret`:

```console
$ export AUTH="Authorization: Bearer s3cret"
$ export API=http://127.0.0.1:8080/api/v1

$ curl -s -X PUT $API/playbooks/site -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"content\": $(jq -Rs . < site.yml), \"description\": \"say hello\"}"
{"name":"site","updated_at":"2026-09-13T09:05:56.480931+00:00","lines":8}

$ curl -s -X PUT $API/providers/lab -H "$AUTH" -H 'Content-Type: application/json' \
    -d '{"plugin_type":"static","config":{"inventory":"[all]\nlocalhost ansible_connection=local\n"}}'
{"name":"lab","plugin_type":"static","usable":true}

$ curl -si -X POST $API/runs -H "$AUTH" -H 'Content-Type: application/json' \
    -d '{"playbook_name":"site","provider":"lab"}'
HTTP/1.1 202 Accepted
location: /api/v1/runs/8aeac1aeb682464c81b55b0a338e45ec

{"task_id":"8aeac1aeb682464c81b55b0a338e45ec","status":"pending","check_mode":false}

$ curl -s $API/runs/8aeac1aeb682464c81b55b0a338e45ec -H "$AUTH" | jq -c '{status, exit_code, check_mode}'
{"status":"success","exit_code":0,"check_mode":false}

$ curl -s "$API/runs/8aeac1aeb682464c81b55b0a338e45ec/logs?tail=3" -H "$AUTH" | jq -r .output
PLAY RECAP *********************************************************************
localhost                  : ok=1    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

(Цветовые коды Ansible там же: терминал их отрисует, агент проигнорирует.)

Сухой прогон — тот же вызов с `"check": true`, и ответ об этом говорит, как
потом говорит и сам прогон: иначе «успешно» читается как «применено».

```console
$ curl -s -X POST $API/runs -H "$AUTH" -H 'Content-Type: application/json' \
    -d '{"playbook_name":"site","provider":"lab","check":true}'
{"task_id":"359ae9d780144e42bb38023161d78c8a","status":"pending","check_mode":true}
```

Проверка плейбука разбирает его и ничего не запускает, поэтому в списке прогонов
ничего не появляется:

```console
$ curl -s -X POST $API/syntax-checks -H "$AUTH" -H 'Content-Type: application/json' \
    -d '{"playbook_name":"site"}'
{"ok":true,"playbook_name":"site","truncated":false,"output":"playbook: playbook.yml"}
```

Отказы приходят одной фразой с кодом ответа, а не трейсбеком:

```console
$ curl -s $API/runs/no-such-run -H "$AUTH"
{"error":"no task with id 'no-such-run'"}

$ curl -s -X POST $API/runs -H "$AUTH" -H 'Content-Type: application/json' -d '{"playbook_name":"site"}'
{"error":"neither inventory nor provider was given; pass exactly one. Use inventory with the INI or YAML text, or provider with the name of a configured source."}

$ curl -s $API/runs -H 'Authorization: Bearer wrong'
{"error": "a bearer token is required"}
```

| Код | Что значит |
|---|---|
| 202 | Прогон принят, но ещё не закончен |
| 400 | Запрос неверен — в том числе опечатка в имени поля: её отвергают, а не игнорируют |
| 401 | Токена нет или он не тот |
| 404 | Того, что вы назвали, здесь нет |
| 500 | Дефект в самом сервисе; трейсбек — в его журнале, а не в ответе |

Два отличия от инструментов сделаны намеренно (ADR-0015). Здесь нет
`confirm=true`: `DELETE` и `POST .../cancel` уже говорят, что вы имели в виду.
И `DELETE` отвечает 404, когда удалять было нечего, — там, где инструмент
отвечает `deleted: false`.

Схема лежит на `/api/v1/openapi.json`, за токеном, как и всё остальное.
Интерактивные страницы выключены сознательно: они грузят свой JavaScript с CDN,
а сервис рассчитан работать там, где до CDN может не быть маршрута.

## Прогоны в контейнере

По умолчанию плейбук выполняется на самом контроллере — потому API-ключ и
равен доступу к шеллу на этой машине. Изоляция переносит выполнение в контейнер,
и `hosts: localhost` начинает означать контейнер, а не ваш хост:

```bash
ANSIBLE_MCP_ISOLATION=true
ANSIBLE_MCP_CONTAINER_RUNTIME=podman
ANSIBLE_MCP_EXECUTION_IMAGE=quay.io/ansible/awx-ee:latest
```

По умолчанию выключено, потому что нужен контейнерный рантайм, а сервис обещает
не требовать ничего. Полная настройка для deb-пакета — в
[заметках по упаковке](../../packaging/README.md#two-shapes-of-the-installation):
rootless podman, образ в хранилище самого сервисного пользователя, systemd
drop-in. Контейнерный вариант этот режим не предлагает: он и так изолирован от
своего хоста, а дотянуться до рантайма изнутри контейнера — значит отдать его
сокет.

Включаете вы, для установки; прогон выключить не может. Назвать другой образ —
может, и то, в чём он в итоге выполнялся, приходит вместе со статусом:

```console
$ curl -s $API/runs/8aeac1ae... -H "$AUTH" | jq -c '{status, execution_environment}'
{"status":"success","execution_environment":"quay.io/ansible/awx-ee:latest"}
```

Образ годится, если в нём есть три вещи. `ansible-playbook` в PATH; отсутствие
собственного `ENTRYPOINT` — команда дописывается после имени образа, и
entrypoint её проглотит; и ssh-клиент, без которого прогон не дотянется никуда,
кроме localhost. У любого execution environment, собранного для AWX, всё это
есть; `tests/fixtures/ee/Containerfile` в этом репозитории — самое маленькое, что
подходит.

Два следствия, о которых стоит знать заранее. Ansible и коллекции теперь
приезжают из образа, а не с хоста, — это и есть выигрыш в воспроизводимости и
одновременно новый способ упасть: нужной коллекции в образе может не быть. И
плейбук, который законно писал что-то на контроллере, теперь пишет внутрь
контейнера, где это исчезает вместе с прогоном.

Чего изоляция не делает — не защищает управляемые хосты. У кого API-ключ, тот
по-прежнему запускает любой плейбук против всего, до чего дотягиваются ваши
креды. Она ограничивает ущерб на контроллере, а не в парке.

## Чего он делать не будет

Это не недоделки, а решения, каждое с обоснованием в
[журнале решений](../adr/INDEX.md):

- **Писать плейбуки и проверять их стиль.** Генерация — работа вызывающего
  агента.
- **Судить, безопасен ли плейбук.** Проверка по шаблонам из прототипа удалена:
  она создавала иллюзию гарантии.
- **Перезапускать, повторять и возобновлять прогоны.**
- **Планировать.** Ни cron, ни отложенных запусков.
- **Отличать вызывающих друг от друга.** Один ключ на экземпляр; журнал аудита
  фиксирует, что сделано, а не кем.
- **Отдавать веб-интерфейс** и масштабироваться дальше одного узла.

Упереться в это — сигнал переходить на полноценную платформу вроде AWX или
Ansible Automation Platform.

## Безопасность, одним абзацем

Кто держит API-ключ, может исполнить произвольный код на хосте контроллера:
плейбук с `hosts: localhost` выполняется *здесь*, а контроллер исполняет всё, что
ему передали. Относитесь к ключу как к SSH-доступу на эту машину. Запускайте
сервис непривилегированно, не выставляйте эндпоинт в сеть без необходимости и
предпочитайте stdio, где процесс запускает клиент и порта нет вообще. Первое
предложение лечится включением изоляции — тогда «здесь» означает контейнер, а не
ваш хост; чего это не лечит, так это парк. Полная версия — в
[README](../../README.ru.md#безопасность-api-ключ-равен-доступу-к-шеллу).

## Когда что-то пошло не так

| Что видите | Что это значит |
|---|---|
| `refusing to listen on 0.0.0.0: ... requires ANSIBLE_MCP_API_KEY` | Отдача не на loopback без токена. Задайте ключ. |
| `401` на `/mcp`, но `/healthz` отвечает | Сервер в порядке; токен неверный или отсутствует. |
| `both playbook and playbook_name were given` | `playbook_name` — ссылка на уже сохранённое, а не имя для передаваемого текста. |
| `the playbook is not valid YAML: ... on line N` | Именно это; строка приведена в сообщении. |
| Задача висит в `pending` | Заняты все слоты. `list_tasks(status: "running")` покажет, кто держит; предел поднимается через `ANSIBLE_MCP_MAX_CONCURRENT_TASKS`. |
| `Permission denied (publickey)` в логах | Дело в доступе, а не в контроллере. Таблица таких симптомов — в [доступе к хостам](connecting-hosts.md). |
| `[redacted]` там, где ждали значение | Так и задумано: значения, похожие на секреты, вырезаются из вывода, сообщений и аудита. |
| Escape-коды в выводе логов | Цветовые коды Ansible, переданные дословно. Агенту не мешают; для человека их стоит вырезать. |
| `Unable to execute ssh command line on a controller: ... No such file or directory: b'ssh'` | Включена изоляция, а в образе нет ssh-клиента. Он обязателен — см. требования к образу выше. |
| Каждый прогон падает с `table tasks has no column named ...` | Каталог данных создан более старой версией, а миграций пока нет: схема создаётся, но не изменяется. Начните с чистого каталога данных или отложите `ansible_mcp.db` в сторону, потеряв историю прогонов. У контейнера `/data` лежит в томе, поэтому это переживает смену образа. |

Журнал аудита в базе отвечает на «что вызывали, чем закончилось и какой прогон из
этого вышел», включая отклонённые вызовы. Инструмента для его чтения нет —
смотрите через sqlite3 в `$ANSIBLE_MCP_DATA_DIR/ansible_mcp.db`.

## Куда дальше

| | |
|---|---|
| [Конфигурация](configuration.md) | Все настройки, включая удержание артефактов и таймауты |
| [Доступ к хостам](connecting-hosts.md) | Ключи, пароли, host keys |
| [Упаковка](../../packaging/README.md) | Подробности про контейнер и пакет *(на английском)* |
| [Интеграция](../../integration/README.md) | Настройка клиента и готовый скилл *(на английском)* |
| [Концепция](concept.md) | Почему он такой |
| [Архитектура](architecture.md) | Как устроен внутри |
| [Журнал решений](../adr/INDEX.md) | Почему границы там, где они есть *(на английском)* |
