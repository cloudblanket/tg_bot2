from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(title="абсолют синема", docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

start_time = time.time()

MAX_CONNECTIONS_PER_ROOM = 50

CONTROL_EVERYONE = "everyone"
CONTROL_CREATOR = "creator"
CONTROL_VOTED = "voted"


async def cleanup_inactive_rooms():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        inactive = [
            code for code, state in room_states.items()
            if not state.connections and (now - state.last_activity) > ROOM_INACTIVITY_TIMEOUT
        ]
        for code in inactive:
            del room_states[code]
            logger.info("Cleaned up inactive room: %s", code)
            try:
                from models.room import Room
                room = Room.get_by_code(code)
                if room:
                    room.deactivate()
            except Exception:
                pass


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_inactive_rooms())


@app.get("/health")
async def health():
    total = sum(len(r.connections) for r in room_states.values())
    rooms = len(room_states)
    return {"status": "ok", "uptime": int(time.time() - start_time), "rooms": rooms, "connections": total}


@dataclass
class Vote:
    vote_type: str  # skip, next, control, kick
    initiator_id: int
    initiator_name: str
    target_user_id: int = 0
    target_user_name: str = ""
    votes: set = field(default_factory=set)
    created_at: float = 0.0

    def to_dict(self, required: int = 0) -> dict:
        return {
            "type": self.vote_type,
            "initiator_id": self.initiator_id,
            "initiator_name": self.initiator_name,
            "target_user_id": self.target_user_id,
            "target_user_name": self.target_user_name,
            "voters": list(self.votes),
            "votes_count": len(self.votes),
            "required": required,
        }


@dataclass
class RoomState:
    current_video_url: str = ""
    is_playing: bool = False
    timestamp: float = 0.0
    last_activity: float = 0.0
    connections: list = field(default_factory=list)
    creator_id: int = 0
    creator_name: str = ""
    control_mode: str = CONTROL_EVERYONE
    user_ids: dict = field(default_factory=dict)  # ws -> user_id
    user_names: dict = field(default_factory=dict)  # user_id -> name
    active_vote: Optional[Vote] = None
    voters_with_control: set = field(default_factory=set)

    def connected_user_count(self) -> int:
        return len(set(self.user_ids.values()))

    def required_votes(self) -> int:
        count = self.connected_user_count()
        return max(1, count // 2 + 1) if count >= 2 else 1

    def user_has_control(self, user_id: int) -> bool:
        if self.control_mode == CONTROL_EVERYONE:
            return True
        if user_id == self.creator_id:
            return True
        if self.control_mode == CONTROL_VOTED:
            return user_id in self.voters_with_control
        return False

    def ws_for_user(self, user_id: int) -> Optional[WebSocket]:
        for ws, uid in self.user_ids.items():
            if uid == user_id:
                return ws
        return None


room_states: dict[str, RoomState] = {}

ROOM_INACTIVITY_TIMEOUT = 30 * 60


def _json_dumps(msg: dict[str, Any]) -> str:
    return json.dumps(msg, separators=(",", ":"))


async def broadcast_to_room(room_code: str, message: dict[str, Any], exclude: Optional[WebSocket] = None) -> None:
    room = room_states.get(room_code)
    if not room:
        return

    payload = _json_dumps(message)
    dead: list = []

    for ws in room.connections:
        if ws is exclude:
            continue
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)

    for ws in dead:
        if ws in room.connections:
            room.connections.remove(ws)


async def send_room_state(room_code: str) -> None:
    room = room_states.get(room_code)
    if not room:
        return
    await broadcast_to_room(room_code, {
        "type": "room_state",
        "control_mode": room.control_mode,
        "creator_id": room.creator_id,
        "connected_users": room.connected_user_count(),
        "voters_with_control": list(room.voters_with_control),
    })


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
    room.last_activity = time.time()

    logger.info("WS connect room=%s total=%d", room_code, len(room.connections))

    await websocket.send_text(_json_dumps({
        "type": "state",
        "is_playing": room.is_playing,
        "timestamp": room.timestamp,
        "current_video_url": room.current_video_url,
        "control_mode": room.control_mode,
        "creator_id": room.creator_id,
        "connected_users": room.connected_user_count(),
        "voters_with_control": list(room.voters_with_control),
        "active_vote": room.active_vote.to_dict(room.required_votes()) if room.active_vote else None,
    }))

    try:
        while True:
            raw = await websocket.receive_text()
            room.last_activity = time.time()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            action = data.get("action")
            sender = data.get("sender", "")
            user_id = data.get("user_id", 0)
            ts = data.get("timestamp", room.timestamp)

            room.user_ids[websocket] = user_id
            if user_id:
                room.user_names[user_id] = sender

            if action == "identify":
                await send_room_state(room_code)
                continue

            if action == "set_control_mode":
                if user_id == room.creator_id:
                    room.control_mode = data.get("mode", CONTROL_EVERYONE)
                    room.voters_with_control.clear()
                    if room.active_vote:
                        room.active_vote = None
                    await broadcast_to_room(room_code, {
                        "type": "control_mode",
                        "mode": room.control_mode,
                    })
                continue

            if action == "vote":
                await handle_vote(room_code, room, websocket, user_id, sender, data)
                continue

            if action == "chat":
                await broadcast_to_room(room_code, {
                    "type": "chat",
                    "text": data.get("text", ""),
                    "sender": sender,
                    "sender_id": user_id,
                }, exclude=None)
                continue

            if action in ("play", "pause", "seek", "set_video"):
                if not room.user_has_control(user_id):
                    await websocket.send_text(_json_dumps({
                        "type": "denied",
                        "message": "Нет прав на управление видео",
                    }))
                    continue

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
        uid = room.user_ids.pop(websocket, 0)
        if uid and uid in room.user_names:
            del room.user_names[uid]
        if uid in room.voters_with_control:
            room.voters_with_control.discard(uid)
        logger.info("WS disconnect room=%s total=%d", room_code, len(room.connections))
        if not room.connections and room.active_vote:
            room.active_vote = None


async def handle_vote(room_code: str, room: RoomState, ws: WebSocket, user_id: int, sender: str, data: dict):
    vote_action = data.get("vote_action")

    if vote_action == "start":
        vote_type = data.get("vote_type", "skip")
        target_id = data.get("target_user_id", 0)
        target_name = data.get("target_user_name", "")

        if room.active_vote:
            await ws.send_text(_json_dumps({
                "type": "vote_error",
                "message": "Уже идёт голосование",
            }))
            return

        room.active_vote = Vote(
            vote_type=vote_type,
            initiator_id=user_id,
            initiator_name=sender,
            target_user_id=target_id,
            target_user_name=target_name,
            votes={user_id},
            created_at=time.time(),
        )

        required = room.required_votes()
        await broadcast_to_room(room_code, {
            "type": "vote_started",
            "vote": room.active_vote.to_dict(required),
        })

        if len(room.active_vote.votes) >= required:
            await execute_vote(room_code, room)

    elif vote_action == "yes":
        if not room.active_vote:
            return
        room.active_vote.votes.add(user_id)
        required = room.required_votes()
        await broadcast_to_room(room_code, {
            "type": "vote_update",
            "vote": room.active_vote.to_dict(required),
        })
        if len(room.active_vote.votes) >= required:
            await execute_vote(room_code, room)

    elif vote_action == "no":
        if not room.active_vote:
            return
        room.active_vote = None
        await broadcast_to_room(room_code, {
            "type": "vote_cancelled",
            "message": f"{sender} отменил голосование",
        })

    elif vote_action == "grant_control":
        if user_id != room.creator_id:
            return
        grant_id = data.get("target_user_id", 0)
        if grant_id:
            room.voters_with_control.add(grant_id)
            grant_ws = room.ws_for_user(grant_id)
            if grant_ws:
                await grant_ws.send_text(_json_dumps({
                    "type": "control_granted",
                    "message": "Теперь ты можешь управлять видео",
                }))
            await send_room_state(room_code)


async def execute_vote(room_code: str, room: RoomState):
    vote = room.active_vote
    if not vote:
        return

    if vote.vote_type == "skip":
        if room.is_playing:
            room.is_playing = False
            room.timestamp = 0
        await broadcast_to_room(room_code, {
            "type": "command",
            "action": "pause",
            "timestamp": 0,
            "sender": "Голосование",
        })

    elif vote.vote_type == "next":
        room.current_video_url = ""
        room.timestamp = 0
        room.is_playing = False
        await broadcast_to_room(room_code, {
            "type": "vote_result",
            "action": "clear_video",
            "message": "Видео снято по голосованию",
        })

    elif vote.vote_type == "control":
        room.control_mode = CONTROL_VOTED
        room.voters_with_control.add(vote.initiator_id)
        await broadcast_to_room(room_code, {
            "type": "vote_result",
            "action": "grant_control",
            "message": f"{vote.initiator_name} получил право управления",
            "voters_with_control": list(room.voters_with_control),
        })

    elif vote.vote_type == "kick":
        target_ws = room.ws_for_user(vote.target_user_id)
        if target_ws:
            try:
                await target_ws.send_text(_json_dumps({
                    "type": "kicked",
                    "message": "Тебя исключили из комнаты",
                }))
                await target_ws.close()
            except Exception:
                pass
            if target_ws in room.connections:
                room.connections.remove(target_ws)

    room.active_vote = None
    await broadcast_to_room(room_code, {
        "type": "vote_completed",
        "vote_type": vote.vote_type,
    })


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
    return [{"code": r.code, "title": r.title, "members": r.member_count(), "is_public": r.is_public, "is_active": r.is_active} for r in rooms]


@app.post("/api/rooms/create")
async def api_create_room(data: dict):
    from models.room import Room
    from models.user import User
    from models.subscription import Subscription

    user_id = data.get("user_id")
    title = data.get("title", "абсолют синема")[:50]
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

    ws_room = room_states.get(code)
    if ws_room and not ws_room.creator_id:
        ws_room.creator_id = user_id
        ws_room.creator_name = User.get_by_telegram_id(user_id).first_name if User.get_by_telegram_id(user_id) else ""

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

    ws_room = room_states.get(code)
    if ws_room:
        for ws in list(ws_room.connections):
            try:
                await ws.send_text(_json_dumps({"type": "room_closed"}))
                await ws.close()
            except Exception:
                pass
        ws_room.connections.clear()
        del room_states[code]

    room.deactivate()
    return {"status": "closed"}


@app.get("/api/personalize/{user_id}")
async def api_get_personalization(user_id: int):
    from services.database import get_db, placeholder
    db = get_db()
    p = placeholder()
    row = db.execute(
        f"SELECT bg_url, bg_color, font_name, accent_color, border_radius FROM personalization WHERE telegram_id = {p}",
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
    from services.database import get_db, placeholder
    db = get_db()
    p = placeholder()
    db.execute(
        f"""
        INSERT INTO personalization (telegram_id, bg_url, bg_color, font_name, accent_color, border_radius)
        VALUES ({p}, {p}, {p}, {p}, {p}, {p})
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
    if not re.match(r'^[a-f0-9\-]+\.\w+$', filename):
        return JSONResponse({"error": "Invalid filename"}, status_code=400)

    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        return JSONResponse({"error": "Video not found or already viewed"}, status_code=404)

    resp = FileResponse(str(file_path), media_type="video/mp4")

    async def delete_after_view():
        await asyncio.sleep(1)
        try:
            file_path.unlink()
            logger.info("Deleted viewed video: %s", filename)
        except Exception:
            pass

    asyncio.create_task(delete_after_view())
    return resp


@app.post("/api/upload")
async def api_upload_video():
    return JSONResponse({"error": "Upload temporarily unavailable"}, status_code=503)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("SYNC_PORT", "8765"))
    uvicorn.run(app, host="0.0.0.0", port=port)
