# Развертывание на домашнем сервере

Исходники лежат в `/opt/food-tracker`, данные — в `/srv/food-tracker`. Сервисы:
`backend`, `frontend`, `bot`, `minio` и при необходимости `tg-proxy`.

## 1. Код и папки

```sh
sudo mkdir -p /opt/food-tracker /srv/food-tracker && sudo chown "$USER" /opt/food-tracker /srv/food-tracker
git clone git@github.com:quneo/food_tracker.git /opt/food-tracker
mkdir -p /srv/food-tracker/data /srv/food-tracker/minio /srv/food-tracker/codex-ssh \
         /srv/food-tracker/tg-proxy /srv/food-tracker/backups
# backend работает в контейнере под uid 10001
docker run --rm -v /srv/food-tracker:/s alpine chown -R 10001:10001 /s/data /s/codex-ssh /s/tg-proxy
```

## 2. Бот в Telegram

1. В @BotFather: `/newbot` → токен. В `/setdomain` укажите домен сайта: без этого не
   заработает Telegram Login Widget. Вход через бота и Mini App работают и без него.
2. Свой Telegram id можно узнать у @userinfobot. Он нужен для `ADMIN_TELEGRAM_IDS`.

## 3. `.env`

```sh
cd /opt/food-tracker && cp .env.example .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # для BOT_API_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # для S3_SECRET_KEY
```

Обязательные переменные: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `BOT_API_SECRET`,
`S3_SECRET_KEY`, `ADMIN_TELEGRAM_IDS`, `PUBLIC_URL`, `COOKIE_SECURE=true` (при https).
Пути к данным:

```
DATA_DIR=/srv/food-tracker/data
MINIO_DIR=/srv/food-tracker/minio
CODEX_SSH_DIR=/srv/food-tracker/codex-ssh
TG_PROXY_SSH_DIR=/srv/food-tracker/tg-proxy
FRONTEND_BIND=<LAN IP сервера>
FRONTEND_PORT=8090
```

## 4. Telegram через VPS

Если сервер не достает до `api.telegram.org`, бот ходит туда через SSH SOCKS-туннель на
VPS. Пользователь VPS (например `tgproxy` с `nologin`) пускает этот ключ только к Telegram:

```sh
ssh-keygen -t ed25519 -N "" -C food-tracker-tg-proxy -f /srv/food-tracker/tg-proxy/id_ed25519
ssh-keyscan -t ed25519 VPS_HOST > /srv/food-tracker/tg-proxy/known_hosts
docker run --rm -v /srv/food-tracker:/s alpine chown -R 10001:10001 /s/tg-proxy
# На VPS, в ~tgproxy/.ssh/authorized_keys одной строкой:
# restrict,port-forwarding,permitopen="api.telegram.org:443" ssh-ed25519 AAAA... food-tracker-tg-proxy
```

В `.env`: `TELEGRAM_PROXY=socks5://tg-proxy:1080` и `TG_PROXY_SSH_TARGET=tgproxy@VPS_HOST`.
Затем сервисы запускаются с `--profile tg-proxy`.

## 5. Ключ для Codex

```sh
ssh-keygen -t ed25519 -N "" -C food-tracker-codex -f /srv/food-tracker/codex-ssh/id_ed25519
ssh-keyscan -t ed25519 VPS_HOST > /srv/food-tracker/codex-ssh/known_hosts
docker run --rm -v /srv/food-tracker:/s alpine sh -c 'chown -R 10001:10001 /s/codex-ssh && chmod 600 /s/codex-ssh/*'
cat /srv/food-tracker/codex-ssh/id_ed25519.pub   # -> runner/install.sh на VPS
```

Дальше VPS настраивается по [vps-codex.md](vps-codex.md). Пока Codex не готов, оставьте
`AI_RUNNER=off`. Сайт будет работать, а бот будет записывать вес, фото прогресса и
показывать итоги дня.

## 6. Запуск

```sh
cd /opt/food-tracker
docker compose --profile tg-proxy up -d --build
docker compose ps
docker compose logs -f bot
```

Миграции базы применяются при старте backend'а. Бакет MinIO создается при первой загрузке
фото и остается приватным: фото отдает только backend и только владельцу.

## 7. Домен и https

Mini App и Login Widget требуют https. Добавьте DNS-запись поддомена на внешний IP и блок
в Caddyfile:

```
food.example.com {
    reverse_proxy <LAN IP сервера>:8090
}
```

После этого `PUBLIC_URL=https://food.example.com`, `COOKIE_SECURE=true` и
`docker compose up -d`. Бот сам поставит кнопку меню «Дневник», которая открывает сайт
внутри Telegram и сразу выполняет вход.

## 8. Вход через Bastion (если есть)

1. В Bastion: «Проекты» → новый проект «Дневник питания», способ входа — своя форма
   проекта; выдайте ему группы (например, `family`). Секрет показывается один раз.
2. В `.env`:

   ```
   REGISTRATION=bastion
   BASTION_URL=http://<LAN IP>:8800
   BASTION_CLIENT_ID=...
   BASTION_CLIENT_SECRET=...
   ADMIN_USERNAMES=<ваш логин в Bastion>
   ```

3. Люди входят на сайте логином, паролем и кодом из приложения. Telegram привязывают в
   «Профиль → Аккаунт → Привязать Telegram», подтвердив в чате с ботом. Бот обслуживает
   только привязанные аккаунты. Если убрать человека из групп проекта, его вход и бот
   закроются при ежечасной сверке.

## 9. Первый вход и приглашения (REGISTRATION=invite)

1. Администратор (id из `ADMIN_TELEGRAM_IDS`) пишет боту `/start`, после этого его аккаунт
   создан.
2. На сайте он нажимает «Войти через Telegram» и подтверждает вход в чате.
3. В «Профиль → Администрирование» он создает приглашение и отправляет ссылку
   `https://t.me/<бот>?start=inv_...`.

С `REGISTRATION=invite` (по умолчанию) без приглашения войти нельзя.

## 10. Резервные копии

`deploy/backup.sh` делает две вещи:
- онлайн-копию SQLite в `/srv/food-tracker/data/backups`, хранятся последние 14;
- зеркало фото из MinIO в `/srv/food-tracker/backups/media`.

```sh
chmod +x /opt/food-tracker/deploy/backup.sh
crontab -e
# 15 4 * * * /opt/food-tracker/deploy/backup.sh >> /srv/food-tracker/backups/backup.log 2>&1
```

Обе папки стоит регулярно копировать за пределы сервера, например `restic` или `rsync`
на VPS.

Восстановление:
1. Остановите backend.
2. Положите копию базы как `/srv/food-tracker/data/food.db` и удалите рядом `food.db-wal`
   и `food.db-shm`.
3. Загрузите фото обратно: `mc mirror /backup food/food-tracker`, тем же образом `pgsty/mc`,
   что в `backup.sh`.

## Обновление

```sh
cd /opt/food-tracker && git pull && docker compose --profile tg-proxy up -d --build
```
