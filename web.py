"""Только веб-сервер для Render (Mini App + WebSocket)."""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
load_dotenv()

from services.sync import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8765"))
    logging.info("Web server starting on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
