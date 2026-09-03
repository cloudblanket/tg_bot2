from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

start_time = time.time()
MAX_CONNECTIONS_PER_ROOM = 50
ROOM_INACTIVITY_TIMEOUT = 30 * 60
SYNC_INTERVAL = 5.0
CONTROL_EVERYONE = "everyone"
CONTROL_CREATOR = "creator"
CONTROL_VOTED = "voted"

_jcache: dict[str, str] = {}
_JCACHE_MAX = 500


def _jd(msg: dict[str, Any]) -> str:
    key = json.dumps(msg, separators=(",", ":"), sort_keys=True)
    if key not in _jcache:
        if len(_jcache) >= _JCACHE_MAX:
            _jcache.clear()
        _jcache[key] = json.dumps(msg, separators=(",", ":"))
    return _jcache[key]


async def _startup():
    asyncio.create_task(periodic_sync())
    asyncio.create_task(cleanup_inactive_rooms())
    asyncio.create_task(cleanup_old_uploads())
    asyncio.create_task(keep_alive())


async def _shutdown():
    for code, room in list(room_states.items()):
        for ws in list(room.connections):
            try:
                await ws.close()
            except Exception:
                pass
        room.connections.clear()
    room_states.clear()


@asynccontextmanager
async def lifespan(application):
    await _startup()
    yield
    await _shutdown()


app = FastAPI(title="абсолют синема", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/webhook")
async def webhook(update: dict) -> dict:
    from aiogram.types import Update as AiogramUpdate
    from services.bot_instance import get_bot, get_dp
    bot = get_bot()
    dp = get_dp()
    if not bot or not dp:
        return {"error": "bot not ready"}
    if bot.session.is_closed:
        logger.warning("Bot session closed, recreating...")
        from aiogram import Bot as FreshBot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        import os
        fresh = FreshBot(
            token=os.getenv("BOT_TOKEN", ""),
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        from services.bot_instance import set_bot
        set_bot(fresh)
        bot = fresh
    telegram_update = AiogramUpdate.model_validate(update, context={"bot": bot})
    asyncio.create_task(dp.feed_update(bot, telegram_update))
    return {"status": "ok"}


@dataclass
class Vote:
    vote_type: str
    initiator_id: int
    initiator_name: str
    target_user_id: int = 0
    target_user_name: str = ""
    votes: set = field(default_factory=set)
    created_at: float = 0.0

    def to_dict(self, required: int = 0) -> dict:
        return {
            "type": self.vote_type,
            "iid": self.initiator_id,
            "in": self.initiator_name,
            "tid": self.target_user_id,
            "tn": self.target_user_name,
            "v": list(self.votes),
            "vc": len(self.votes),
            "r": required,
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
    user_ids: dict = field(default_factory=dict)
    user_names: dict = field(default_factory=dict)
    active_vote: Optional[Vote] = None
    voters_with_control: set = field(default_factory=set)
    _dirty: bool = False

    def connected_user_count(self) -> int:
        return len(set(self.user_ids.values()))

    def required_votes(self) -> int:
        c = self.connected_user_count()
        return max(1, c // 2 + 1) if c >= 2 else 1

    def user_has_control(self, uid: int) -> bool:
        if self.control_mode == CONTROL_EVERYONE:
            return True
        if uid == self.creator_id:
            return True
        if self.control_mode == CONTROL_VOTED:
            return uid in self.voters_with_control
        return False

    def ws_for_user(self, uid: int) -> Optional[WebSocket]:
        for ws, u in self.user_ids.items():
            if u == uid:
                return ws
        return None


room_states: dict[str, RoomState] = {}


async def broadcast_to_room(room_code: str, payload: str, exclude: Optional[WebSocket] = None) -> None:
    room = room_states.get(room_code)
    if not room:
        return
    if not room.connections:
        return

    if exclude is None:
        targets = list(room.connections)
    else:
        targets = [ws for ws in room.connections if ws is not exclude]

    if not targets:
        return

    dead = []
    sends = []
    for ws in targets:
        sends.append(_send_safe(ws, payload, dead))

    await asyncio.gather(*sends)

    for ws in dead:
        try:
            room.connections.remove(ws)
        except ValueError:
            pass


async def _send_safe(ws: WebSocket, payload: str, dead: list):
    try:
        await ws.send_text(payload, timeout=3)
    except Exception:
        dead.append(ws)


async def periodic_sync():
    while True:
        await asyncio.sleep(SYNC_INTERVAL)
        now = time.time()
        for code, room in list(room_states.items()):
            if not room.connections:
                continue
            if room.is_playing:
                room.timestamp += SYNC_INTERVAL
            payload = _jd({
                "t": "sync",
                "ts": round(room.timestamp, 2),
                "p": room.is_playing,
            })
            dead = []
            sends = []
            for ws in room.connections:
                sends.append(_send_safe(ws, payload, dead))
            await asyncio.gather(*sends)
            for ws in dead:
                try:
                    room.connections.remove(ws)
                except ValueError:
                    pass


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
            try:
                from models.room import Room
                room = Room.get_by_code(code)
                if room:
                    room.deactivate()
            except Exception:
                pass


UPLOAD_MAX_AGE = 12 * 3600


async def cleanup_old_uploads():
    while True:
        await asyncio.sleep(300)
        now = time.time()
        try:
            for f in UPLOAD_DIR.iterdir():
                if f.is_file():
                    age = now - f.stat().st_mtime
                    if age > UPLOAD_MAX_AGE:
                        f.unlink()
                        logger.info("Deleted old upload: %s (age %.0fs)", f.name, age)
        except Exception as e:
            logger.warning("Upload cleanup error: %s", e)


async def keep_alive():
    import aiohttp
    while True:
        await asyncio.sleep(600)
        try:
            port = int(os.getenv("PORT", os.getenv("SYNC_PORT", "8765")))
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{port}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    logger.debug("Keep-alive ping: %s", resp.status)
        except Exception as e:
            logger.debug("Keep-alive error: %s", e)


@app.get("/health")
async def health():
    total = sum(len(r.connections) for r in room_states.values())
    return {"status": "ok", "uptime": int(time.time() - start_time), "rooms": len(room_states), "connections": total}


@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str) -> None:
    room = room_states.get(room_code)
    if room and len(room.connections) >= MAX_CONNECTIONS_PER_ROOM:
        await websocket.close(code=1013)
        return

    await websocket.accept()

    if room_code not in room_states:
        room_states[room_code] = RoomState()

    room = room_states[room_code]
    room.connections.append(websocket)
    room.last_activity = time.time()

    state_payload = _jd({
        "t": "state",
        "v": room.current_video_url,
        "p": room.is_playing,
        "ts": round(room.timestamp, 2),
        "cm": room.control_mode,
        "cr": room.creator_id,
        "cu": room.connected_user_count(),
        "vc": list(room.voters_with_control),
        "av": room.active_vote.to_dict(room.required_votes()) if room.active_vote else None,
    })
    await websocket.send_text(state_payload)

    try:
        while True:
            raw = await websocket.receive_text()
            room.last_activity = time.time()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            action = data.get("a")
            uid = data.get("u", 0)
            sender = data.get("s", "")

            if action == "i":
                room.user_ids[websocket] = uid
                if uid:
                    room.user_names[uid] = sender
                continue

            if action == "cm":
                if uid == room.creator_id:
                    room.control_mode = data.get("m", CONTROL_EVERYONE)
                    room.voters_with_control.clear()
                    if room.active_vote:
                        room.active_vote = None
                    await broadcast_to_room(room_code, _jd({"t": "cm", "m": room.control_mode}))
                continue

            if action == "v":
                await handle_vote(room_code, room, websocket, uid, sender, data)
                continue

            if action == "c":
                msg = _jd({"t": "c", "tx": data.get("tx", ""), "s": sender, "u": uid})
                await broadcast_to_room(room_code, msg)
                continue

            if action in ("p", "a", "k", "sv"):
                if not room.user_has_control(uid):
                    await websocket.send_text(_jd({"t": "d", "m": "Нет прав"}))
                    continue

                ts = data.get("ts", room.timestamp)

                if action == "p":
                    room.is_playing = True
                    room.timestamp = ts
                elif action == "a":
                    room.is_playing = False
                    room.timestamp = ts
                elif action == "k":
                    room.timestamp = ts
                elif action == "sv":
                    room.current_video_url = data.get("v", "")
                    room.timestamp = 0
                    room.is_playing = False
                    ts = 0

                msg = {"t": "cmd", "a": action, "ts": round(ts, 2), "s": sender}
                if action == "sv":
                    msg["v"] = room.current_video_url
                await broadcast_to_room(room_code, _jd(msg), exclude=websocket)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WS error %s: %s", room_code, e)
    finally:
        if websocket in room.connections:
            room.connections.remove(websocket)
        uid = room.user_ids.pop(websocket, 0)
        if uid and uid in room.user_names:
            del room.user_names[uid]
        room.voters_with_control.discard(uid)
        if not room.connections and room.active_vote:
            room.active_vote = None


async def handle_vote(room_code: str, room: RoomState, ws: WebSocket, uid: int, sender: str, data: dict):
    va = data.get("va")

    if va == "s":
        vt = data.get("vt", "skip")
        tid = data.get("tid", 0)
        tname = data.get("tn", "")

        if room.active_vote:
            await ws.send_text(_jd({"t": "ve", "m": "Уже идёт"}))
            return

        room.active_vote = Vote(
            vote_type=vt, initiator_id=uid, initiator_name=sender,
            target_user_id=tid, target_user_name=tname,
            votes={uid}, created_at=time.time(),
        )
        req = room.required_votes()
        await broadcast_to_room(room_code, _jd({"t": "vs", "v": room.active_vote.to_dict(req)}))

        if len(room.active_vote.votes) >= req:
            await execute_vote(room_code, room)

    elif va == "y":
        if not room.active_vote:
            return
        room.active_vote.votes.add(uid)
        req = room.required_votes()
        await broadcast_to_room(room_code, _jd({"t": "vu", "v": room.active_vote.to_dict(req)}))
        if len(room.active_vote.votes) >= req:
            await execute_vote(room_code, room)

    elif va == "n":
        if not room.active_vote:
            return
        room.active_vote = None
        await broadcast_to_room(room_code, _jd({"t": "vc", "m": f"{sender} отменил"}))

    elif va == "g":
        if uid != room.creator_id:
            return
        gid = data.get("tid", 0)
        if gid:
            room.voters_with_control.add(gid)
            gws = room.ws_for_user(gid)
            if gws:
                await gws.send_text(_jd({"t": "cg", "m": "Право управления"}))
            await broadcast_to_room(room_code, _jd({
                "t": "rs", "cm": room.control_mode, "cr": room.creator_id,
                "cu": room.connected_user_count(), "vc": list(room.voters_with_control),
            }))


async def execute_vote(room_code: str, room: RoomState):
    vote = room.active_vote
    if not vote:
        return

    if vote.vote_type == "skip":
        room.is_playing = False
        room.timestamp = 0
        await broadcast_to_room(room_code, _jd({"t": "cmd", "a": "a", "ts": 0, "s": "Голосование"}))

    elif vote.vote_type == "next":
        room.current_video_url = ""
        room.timestamp = 0
        room.is_playing = False
        await broadcast_to_room(room_code, _jd({"t": "vr", "a": "clr", "m": "Видео снято"}))

    elif vote.vote_type == "control":
        room.control_mode = CONTROL_VOTED
        room.voters_with_control.add(vote.initiator_id)
        await broadcast_to_room(room_code, _jd({
            "t": "vr", "a": "gc", "m": f"{vote.initiator_name} управляет",
            "vc": list(room.voters_with_control),
        }))

    elif vote.vote_type == "kick":
        tws = room.ws_for_user(vote.target_user_id)
        if tws:
            try:
                await tws.send_text(_jd({"t": "kicked", "m": "Исключён"}))
                await tws.close()
            except Exception:
                pass
            if tws in room.connections:
                room.connections.remove(tws)

    room.active_vote = None
    await broadcast_to_room(room_code, _jd({"t": "vcl"}))


# ==========================================
# REST API
# ==========================================

@app.get("/api/rooms")
async def api_list_rooms():
    from models.room import Room
    rooms = Room.get_public_rooms()
    return {"rooms": [{
        "code": r.code, "title": r.title,
        "members": len(r.get_members()),
        "has_password": bool(r.password),
        "creator_id": r.creator_id,
    } for r in rooms]}


@app.get("/api/rooms/my/{user_id}")
async def api_my_rooms(user_id: int):
    from models.room import Room
    rooms = Room.get_user_rooms(user_id)
    return [{"code": r.code, "title": r.title, "members": r.member_count(),
             "is_public": r.is_public, "is_active": r.is_active} for r in rooms]


@app.post("/api/rooms/create")
async def api_create_room(data: dict):
    from models.room import Room
    from models.user import User
    from models.subscription import Subscription

    uid = data.get("user_id")
    title = data.get("title", "абсолют синема")[:50]
    pw = data.get("password", "")
    is_pub = data.get("is_public", True)

    if not uid:
        return JSONResponse({"error": "user_id required"}, status_code=400)
    user = User.get_by_telegram_id(uid)
    if not user:
        return JSONResponse({"error": "User not found"}, status_code=404)

    sub = Subscription.get_by_telegram_id(uid)
    room = Room.create(creator_id=uid, title=title, password=pw if pw else None, is_public=is_pub)
    room.add_member(uid)

    ws_room = room_states.get(room.code)
    if ws_room:
        ws_room.creator_id = uid
        ws_room.creator_name = user.first_name or ""

    return {"code": room.code, "title": room.title, "has_password": bool(room.password),
            "is_public": room.is_public, "max_members": sub.max_members}


@app.post("/api/rooms/join")
async def api_join_room(data: dict):
    from models.room import Room
    from models.user import User
    from models.subscription import Subscription

    uid = data.get("user_id")
    code = data.get("code", "")
    pw = data.get("password", "")

    if not uid:
        return JSONResponse({"error": "user_id required"}, status_code=400)

    room = Room.get_by_code(code)
    if not room or not room.is_active:
        return JSONResponse({"error": "Room not found"}, status_code=404)
    if room.password and room.password != pw:
        return JSONResponse({"error": "Wrong password"}, status_code=403)
    if not room.add_member(uid):
        return JSONResponse({"error": "Room full"}, status_code=400)

    sub = Subscription.get_by_telegram_id(uid)

    ws_room = room_states.get(code)
    if ws_room and not ws_room.creator_id:
        ws_room.creator_id = uid
        u = User.get_by_telegram_id(uid)
        ws_room.creator_name = u.first_name if u else ""

    return {"code": room.code, "title": room.title, "tier": sub.tier, "max_members": sub.max_members}


@app.post("/api/rooms/close")
async def api_close_room(data: dict):
    from models.room import Room

    uid = data.get("user_id")
    code = data.get("code", "")

    if not uid:
        return JSONResponse({"error": "user_id required"}, status_code=400)

    room = Room.get_by_code(code)
    if not room:
        return JSONResponse({"error": "Room not found"}, status_code=404)
    if room.creator_id != uid:
        return JSONResponse({"error": "Only creator can close"}, status_code=403)

    ws_room = room_states.get(code)
    if ws_room:
        close_msg = _jd({"t": "rc"})
        for ws in list(ws_room.connections):
            try:
                await ws.send_text(close_msg)
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
    return {"bg_url": row[0] or "", "bg_color": row[1] or "", "font_name": row[2] or "",
            "accent_color": row[3] or "", "border_radius": row[4] or ""}


@app.post("/api/personalize/{user_id}")
async def api_save_personalization(user_id: int, data: dict):
    from services.database import get_db, placeholder
    db = get_db()
    p = placeholder()
    db.execute(
        f"""INSERT INTO personalization (telegram_id, bg_url, bg_color, font_name, accent_color, border_radius)
        VALUES ({p}, {p}, {p}, {p}, {p}, {p})
        ON CONFLICT(telegram_id) DO UPDATE SET
            bg_url=excluded.bg_url, bg_color=excluded.bg_color, font_name=excluded.font_name,
            accent_color=excluded.accent_color, border_radius=excluded.border_radius""",
        (user_id, data.get("bg_url", ""), data.get("bg_color", ""), data.get("font_name", ""),
         data.get("accent_color", ""), data.get("border_radius", "")),
    )
    db.commit()
    return {"status": "ok"}


@app.get("/api/referral/{user_id}")
async def api_get_referral(user_id: int):
    from services.database import get_db, placeholder
    from models.user import User
    user = User.get_by_telegram_id(user_id)
    if not user:
        return {"error": "user not found"}
    from services.bot_instance import get_bot_username
    username = get_bot_username() or "absolut_bot"
    ref_link = f"https://t.me/{username}?start=ref_{user.referral_code}"
    return {
        "referral_code": user.referral_code,
        "referral_link": ref_link,
        "referrals_count": user.referrals_count,
    }


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
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(str(file_path), media_type="video/mp4")


@app.post("/api/upload")
async def api_upload_video():
    return JSONResponse({"error": "Upload temporarily unavailable"}, status_code=503)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("SYNC_PORT", "8765"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
