# Codex на VPS

Домашний сервер не ходит в OpenAI сам. Backend подключается по SSH к VPS, где установлен
и авторизован Codex CLI, и передает запрос **ограниченному runner'у**
(`runner/food_codex_runner.py`).

```
backend (дом) ──ssh, ключ с forced command──▶ food-ai@VPS: food-codex-runner
                                               └─ codex exec (read-only, без инструментов)
```

- SSH-ключ backend'а в `authorized_keys` привязан к runner'у (`restrict,command=...`). Этот ключ
  не может открыть shell, пробросить порты или запустить что-то другое.
- Запрос (промт, JSON Schema и фото в base64) приходит одним JSON на stdin. Командная строка
  `codex` собирается из фиксированных частей, текст пользователя туда не попадает.
- Фото пишутся во временную папку `~/work/req-*` с правами `0700` и удаляются сразу после
  ответа, в том числе при ошибке и тайм-ауте. На VPS уходит уменьшенная копия без EXIF
  и геометки.
- Codex запускается со своим `CODEX_HOME`. Там конфиг без shell, web search, MCP и памяти,
  а также `--sandbox read-only`, `--ephemeral` (без файлов сессий) и пустая рабочая папка.
- Если Codex все-таки вызвал инструмент (`command_execution`, `web_search` и т. п.), runner
  считает ответ ошибкой (`tool_use`): так заметна неверная настройка.
- Параллельно идут не больше `FOOD_RUNNER_SLOTS` (по умолчанию 2) вызовов, они
  разделяются `flock`.

## 1. Codex CLI

На VPS нужен Node.js 22+ (или готовый бинарник из релизов `openai/codex` на GitHub):

```sh
sudo npm install -g @openai/codex
codex --version
```

## 2. Пользователь и runner

Ключ для backend'а создается на домашнем сервере (шаг 5 в [deploy.md](deploy.md)). Его
публичная часть передается установщику:

```sh
git clone https://github.com/quneo/food_tracker.git && cd food_tracker/runner
sudo sh install.sh "ssh-ed25519 AAAA... food-tracker@home-server"
```

Установщик создает системного пользователя `food-ai` с домашней папкой `/var/lib/food-ai`,
кладет `/usr/local/bin/food-codex-runner`, конфиг `/var/lib/food-ai/codex-home/config.toml`
(из `runner/codex-config.toml`) и строку в `authorized_keys`.

## 3. Вход в ChatGPT

```sh
sudo -iu food-ai env CODEX_HOME=/var/lib/food-ai/codex-home codex login --device-auth
sudo -iu food-ai env CODEX_HOME=/var/lib/food-ai/codex-home codex login status
```

Для `--device-auth` в настройках безопасности ChatGPT должен быть включен вход по коду
устройства. Без этого можно пробросить порт и войти обычным способом:
`ssh -L 1455:localhost:1455 vps`, затем `codex login` под `food-ai`.

`auth.json` — это пароль от аккаунта, права у него должны быть `0600`. Для runner'а лучше
войти отдельно, а не копировать файл с другой машины: один `auth.json` нельзя использовать
одновременно в нескольких местах.

## 4. Модель и проверка конфига

В `codex-home/config.toml` укажите модель, доступную на вашем тарифе и умеющую
работать с картинками. Список моделей показывает команда `/model` в интерактивном `codex`.
По умолчанию стоит `gpt-6-luna`: быстрая и с большими лимитами. Backend может
переопределить модель через `AI_MODEL`.

Проверьте, что вход и конфиг работают и Codex не пытается вызывать инструменты:

```sh
sudo -iu food-ai food-codex-runner --selftest
# OK in 4210 ms, model gpt-6-luna: {'reply': 'ok'}
```

`--selftest` работает только локально: через SSH forced command аргументы не передаются.
Если Codex ругается на
неизвестный ключ конфига (у разных версий набор `[features]` отличается), уберите эту
строку из `config.toml`. Разовая проверка с `--strict-config` показывает все такие ключи.

## 5. Проверка с домашнего сервера

```sh
cd /opt/food-tracker
docker compose exec backend sh -c 'echo "{}" | ssh -T -i /run/codex-ssh/id_ed25519 \
  -o UserKnownHostsFile=/run/codex-ssh/known_hosts food-ai@VPS_HOST run'
# -> {"ok": false, "error": "bad_request", ...}: доступ есть, runner отвечает
```

После этого в `.env`: `AI_RUNNER=ssh`, `AI_SSH_TARGET=food-ai@VPS_HOST`, и
`docker compose up -d backend`.

## Лимиты

У входа через ChatGPT есть лимиты сообщений за 5 часов и за неделю. Они зависят от тарифа
и модели, текущий расход виден в chatgpt.com/codex/settings/usage. Один ответ бота — это
один вызов `codex exec`. При ошибке сети или тайм-ауте backend повторяет вызов один раз.
