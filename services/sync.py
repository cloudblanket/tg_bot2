from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(title="Cinema Night", docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

start_time = time.time()

MAX_CONNECTIONS_PER_ROOM = 50


@app.get("/health")
async def health():
    total = sum(len(r.connections) for r in room_states.values())
    rooms = len(room_states)
    return {"status": "ok", "uptime": int(time.time() - start_time), "rooms": rooms, "connections": total}


@dataclass
class RoomState:
    current_video_url: str = ""
    is_playing: bool = False
    timestamp: float = 0.0
    last_updated: float = 0.0
    connections: list[WebSocket] = field(default_factory=list)
    _json_cache: dict[str, str] = field(default_factory=dict, repr=False)


room_states: dict[str, RoomState] = {}


def _json_dumps(msg: dict[str, Any]) -> str:
    return json.dumps(msg, separators=(",", ":"))


async def broadcast_to_room(room_code: str, message: dict[str, Any], exclude: Optional[WebSocket] = None) -> None:
    room = room_states.get(room_code)
    if not room:
        return

    payload = _json_dumps(message)
    dead: list[int] = []

    for i, ws in enumerate(room.connections):
        if ws is exclude:
            continue
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(i)

    for i in reversed(dead):
        room.connections.pop(i, None)


@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str) -> None:
    room = room_states.get(room_code)
    if room and len(room.connections) >= MAX_CONNECTIONS_PER_ROOM:
        await websocket.close(code=1013, reason="Room full")
        return

    await websocket.accept()

    if room_code not in room_states:
        room_states[room_code] = RoomState()

    room = room_states[room_code]
    room.connections.append(websocket)

    logger.info("WS connect room=%s total=%d", room_code, len(room.connections))

    await websocket.send_text(_json_dumps({
        "type": "state",
        "is_playing": room.is_playing,
        "timestamp": room.timestamp,
        "current_video_url": room.current_video_url,
    }))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            action = data.get("action")
            ts = data.get("timestamp", room.timestamp)
            sender = data.get("sender", "")

            if action == "play":
                room.is_playing = True
                room.timestamp = ts
            elif action == "pause":
                room.is_playing = False
                room.timestamp = ts
            elif action == "seek":
                room.timestamp = ts
            elif action == "set_video":
                room.current_video_url = data.get("url", "")
                room.timestamp = 0
                room.is_playing = False
                ts = 0
            elif action == "chat":
                pass
            else:
                continue

            if action == "chat":
                msg = {"type": "chat", "text": data.get("text", ""), "sender": sender, "sender_id": data.get("sender_id", 0)}
            else:
                msg = {"type": "command", "action": action, "timestamp": ts, "sender": sender}
                if action == "set_video":
                    msg["url"] = room.current_video_url

            await broadcast_to_room(room_code, msg, exclude=websocket)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WS error room=%s: %s", room_code, e)
    finally:
        if websocket in room.connections:
            room.connections.remove(websocket)
        logger.info("WS disconnect room=%s total=%d", room_code, len(room.connections))


# Статические файлы
import os
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "miniapp" / "static"
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR), cache_max_age=3600), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(STATIC_DIR / "index.html"), headers={"Cache-Control": "no-cache"})


@app.get("/view/{filename}")
async def view_video(filename: str):
    import re
    if not re.match(r'^[a-f0-9\-]+\.mp4$', filename):
        return {"error": "Invalid filename"}

    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        return {"error": "Video not found or already viewed"}

    from fastapi.responses import FileResponse
    resp = FileResponse(str(file_path), media_type="video/mp4")

    import asyncio
    async def delete_after_view():
        await asyncio.sleep(1)
        try:
            file_path.unlink()
            logger.info("Deleted viewed video: %s", filename)
        except Exception:
            pass

    asyncio.create_task(delete_after_view())
    return resp


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("SYNC_PORT", "8765"))
    uvicorn.run(app, host="0.0.0.0", port=port)
