FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG BUILD_TIME=none
COPY . .

RUN mkdir -p /app/data

ENV BOT_TOKEN=""
ENV WEBAPP_URL=""
ENV SYNC_PORT=8765
ENV DATABASE_PATH=/app/data/bot.db
ENV PYTHONUNBUFFERED=1

EXPOSE 8765

CMD ["python", "bot.py"]
