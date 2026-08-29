from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="Cinema Night Sync Server")


@dataclass
class RoomState:
    """Состояние комнаты для синхронизации видео."""
    current_video_url: str = ""
    is_playing: bool = False
    timestamp: float = 0.0
    last_updated: float = 0.0
    connections: list[WebSocket] = field(default_factory=list)


# Хранилище состояний комнат
room_states: dict[str, RoomState] = {}


async def broadcast_to_room(room_code: str, message: dict[str, Any], exclude: Optional[WebSocket] = None) -> None:
    """Отправить сообщение всем подключённым клиентам в комнате."""
    if room_code not in room_states:
        return

    room = room_states[room_code]
    dead: list[WebSocket] = []

    for ws in room.connections:
        if ws is exclude:
            continue
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)

    for ws in dead:
        room.connections.remove(ws)


@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str) -> None:
    await websocket.accept()

    if room_code not in room_states:
        room_states[room_code] = RoomState()

    room = room_states[room_code]
    room.connections.append(websocket)

    logger.info("Client connected to room %s (total: %d)", room_code, len(room.connections))

    # Отправляем текущее состояние при подключении
    await websocket.send_json({
        "type": "state",
        "is_playing": room.is_playing,
        "timestamp": room.timestamp,
        "current_video_url": room.current_video_url,
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            action = data.get("action")
            logger.info("Room %s: action=%s", room_code, action)

            if action == "play":
                room.is_playing = True
                room.timestamp = data.get("timestamp", room.timestamp)
                await broadcast_to_room(room_code, {
                    "type": "command",
                    "action": "play",
                    "timestamp": room.timestamp,
                    "sender": data.get("sender", ""),
                }, exclude=websocket)

            elif action == "pause":
                room.is_playing = False
                room.timestamp = data.get("timestamp", room.timestamp)
                await broadcast_to_room(room_code, {
                    "type": "command",
                    "action": "pause",
                    "timestamp": room.timestamp,
                    "sender": data.get("sender", ""),
                }, exclude=websocket)

            elif action == "seek":
                room.timestamp = data.get("timestamp", room.timestamp)
                await broadcast_to_room(room_code, {
                    "type": "command",
                    "action": "seek",
                    "timestamp": room.timestamp,
                    "sender": data.get("sender", ""),
                }, exclude=websocket)

            elif action == "set_video":
                room.current_video_url = data.get("url", "")
                room.timestamp = 0
                room.is_playing = False
                await broadcast_to_room(room_code, {
                    "type": "command",
                    "action": "set_video",
                    "url": room.current_video_url,
                    "sender": data.get("sender", ""),
                }, exclude=websocket)

            elif action == "chat":
                await broadcast_to_room(room_code, {
                    "type": "chat",
                    "text": data.get("text", ""),
                    "sender": data.get("sender", ""),
                    "sender_id": data.get("sender_id", 0),
                }, exclude=websocket)

    except WebSocketDisconnect:
        room.connections.remove(websocket)
        logger.info("Client disconnected from room %s (total: %d)", room_code, len(room.connections))

        if not room.connections:
            # Не удаляем состояние сразу, чтобы переподключение было возможным
            logger.info("Room %s is now empty", room_code)


# Статические файлы Mini App
import os
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "miniapp" / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(STATIC_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("SYNC_PORT", "8765"))
    uvicorn.run(app, host="0.0.0.0", port=port)
