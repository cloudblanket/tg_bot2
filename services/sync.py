from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
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
        room.connections.pop(i)


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


@app.get("/api/rooms")
async def api_list_rooms():
    from models.room import Room
    rooms = Room.get_public_rooms()
    result = []
    for r in rooms:
        members = r.get_members()
        result.append({
            "code": r.code,
            "title": r.title,
            "members": len(members),
            "has_password": bool(r.password),
            "creator_id": r.creator_id,
        })
    return {"rooms": result}


@app.get("/api/rooms/my/{user_id}")
async def api_my_rooms(user_id: int):
    from models.room import Room
    rooms = Room.get_user_rooms(user_id)
    return [{"code": r.code, "title": r.title, "members": r.member_count, "is_public": r.is_public, "is_active": r.is_active} for r in rooms]


@app.post("/api/rooms/create")
async def api_create_room(data: dict):
    from models.room import Room
    from models.user import User
    from models.subscription import Subscription

    user_id = data.get("user_id")
    title = data.get("title", "Киновечер")[:50]
    password = data.get("password", "")
    is_public = data.get("is_public", True)

    if not user_id:
        return JSONResponse({"error": "user_id required"}, status_code=400)

    user = User.get_by_telegram_id(user_id)
    if not user:
        return JSONResponse({"error": "User not found"}, status_code=404)

    sub = Subscription.get_by_telegram_id(user_id)
    room = Room.create(
        creator_id=user_id,
        title=title,
        password=password if password else None,
        is_public=is_public,
    )
    room.add_member(user_id)

    return {
        "code": room.code,
        "title": room.title,
        "has_password": bool(room.password),
        "is_public": room.is_public,
        "max_members": sub.max_members,
    }


@app.post("/api/rooms/join")
async def api_join_room(data: dict):
    from models.room import Room
    from models.user import User
    from models.subscription import Subscription

    user_id = data.get("user_id")
    code = data.get("code", "")
    password = data.get("password", "")

    if not user_id:
        return JSONResponse({"error": "user_id required"}, status_code=400)

    room = Room.get_by_code(code)
    if not room or not room.is_active:
        return JSONResponse({"error": "Room not found"}, status_code=404)

    if room.password and room.password != password:
        return JSONResponse({"error": "Wrong password"}, status_code=403)

    if not room.add_member(user_id):
        return JSONResponse({"error": "Room full"}, status_code=400)

    sub = Subscription.get_by_telegram_id(user_id)
    return {
        "code": room.code,
        "title": room.title,
        "tier": sub.tier,
        "max_members": sub.max_members,
    }


@app.post("/api/rooms/close")
async def api_close_room(data: dict):
    from models.room import Room

    user_id = data.get("user_id")
    code = data.get("code", "")

    if not user_id:
        return JSONResponse({"error": "user_id required"}, status_code=400)

    room = Room.get_by_code(code)
    if not room:
        return JSONResponse({"error": "Room not found"}, status_code=404)

    if room.creator_id != user_id:
        return JSONResponse({"error": "Only creator can close"}, status_code=403)

    room.deactivate()
    return {"status": "closed"}


@app.get("/api/personalize/{user_id}")
async def api_get_personalization(user_id: int):
    from services.database import get_db
    db = get_db()
    row = db.execute(
        "SELECT bg_url, bg_color, font_name, accent_color, border_radius FROM personalization WHERE telegram_id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return {"bg_url": "", "bg_color": "", "font_name": "", "accent_color": "", "border_radius": ""}
    return {
        "bg_url": row[0] or "",
        "bg_color": row[1] or "",
        "font_name": row[2] or "",
        "accent_color": row[3] or "",
        "border_radius": row[4] or "",
    }


@app.post("/api/personalize/{user_id}")
async def api_save_personalization(user_id: int, data: dict):
    from services.database import get_db
    db = get_db()
    db.execute(
        """
        INSERT INTO personalization (telegram_id, bg_url, bg_color, font_name, accent_color, border_radius)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            bg_url = excluded.bg_url,
            bg_color = excluded.bg_color,
            font_name = excluded.font_name,
            accent_color = excluded.accent_color,
            border_radius = excluded.border_radius
        """,
        (
            user_id,
            data.get("bg_url", ""),
            data.get("bg_color", ""),
            data.get("font_name", ""),
            data.get("accent_color", ""),
            data.get("border_radius", ""),
        ),
    )
    db.commit()
    return {"status": "ok"}


# Статические файлы
import os
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "miniapp" / "static"
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
