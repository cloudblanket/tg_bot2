# Киновечер — Telegram Bot

Бот для совместного просмотра видео в Telegram. Создавай комнаты, приглашай друзей, смотрите видео синхронно!

## Возможности

- Создание комнат для совместного просмотра
- Приглашение по коду или ссылке
- Синхронизация Play/Pause/Seek через WebSocket
- Встроенный чат
- Поддержка YouTube (с возможностью замены на прокси/Rutube)

## Структура проекта

```
bot.py                 # Точка входа (бот + WebSocket сервер)
handlers/
    start.py           # Команда /start
    room.py            # Команды /create, /join, /leave, /rooms
    webapp.py          # Обработка данных из Mini App
models/
    user.py            # Модель пользователя
    room.py            # Модели комнаты, участников, видео
services/
    database.py        # SQLite подключение и миграции
    sync.py            # WebSocket сервер для синхронизации
miniapp/
    static/
        index.html     # Mini App страница
        style.css      # Стили
        app.js         # Клиентская логика + YouTube Player
requirements.txt
Dockerfile
```

## Установка

### 1. Клонируй репозиторий

```bash
git clone <url>
cd tg_bot
```

### 2. Установи зависимости

```bash
pip install -r requirements.txt
```

### 3. Настрой переменные окружения

```bash
export BOT_TOKEN="your-telegram-bot-token"
export WEBAPP_URL="https://your-domain.com"
export SYNC_PORT=8765
```

### 4. Запусти

```bash
python bot.py
```

## Деплой на Render/Railway

### Render

1. Создай новый Web Service
2. Подключи репозиторий
3. Настрой:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python bot.py`
4. Добавь переменные окружения:
   - `BOT_TOKEN` — токен бота от @BotFather
   - `WEBAPP_URL` — URL твоего сервиса
   - `SYNC_PORT` — `8765`

### Railway

1. Создай новый проект
2. Deploy from GitHub
3. Добавь переменные окружения в Settings → Variables
4. Railway автоматически определит Dockerfile

**Важно:** На бесплатном тарифе Railway сервис засыпает через 15 минут без активности. Используй cron-ping для поддержания активности.

## Настройка YouTube Proxy (для России)

Если YouTube заблокирован, замени URL в `miniapp/static/app.js`:

```javascript
// Было:
tag.src = 'https://www.youtube.com/iframe_api';

// Стало (через прокси):
tag.src = 'https://your-proxy.com/youtube/iframe_api';
```

Альтернативы:
- **Rutube** — используй `<iframe src="https://rutube.ru/..."/>`
- **VK Video** — используй `<iframe src="https://vk.com/video_ext.php?..."/>`
- **Custom proxy** — настрой прокси-сервер для YouTube IFrame API

## API WebSocket

Сервер синхронизации (`sync.py`) обрабатывает сообщения:

### От клиента:
```json
{"action": "play", "timestamp": 42.5, "sender": "Иван"}
{"action": "pause", "timestamp": 42.5, "sender": "Иван"}
{"action": "seek", "timestamp": 120.0, "sender": "Иван"}
{"action": "set_video", "url": "https://...", "sender": "Иван"}
{"action": "chat", "text": "Привет!", "sender": "Иван", "sender_id": 123}
```

### От сервера:
```json
{"type": "state", "is_playing": true, "timestamp": 42.5, "current_video_url": "..."}
{"type": "command", "action": "play", "timestamp": 42.5, "sender": "Иван"}
{"type": "chat", "text": "Привет!", "sender": "Иван", "sender_id": 123}
```

## Лицензия

MIT
