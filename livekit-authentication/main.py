import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit.api import AccessToken, VideoGrants
from pydantic import BaseModel

# message_history/ is a sibling of main.py in /app — add that dir to sys.path.
_app_dir = os.path.dirname(os.path.abspath(__file__))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

try:
    from message_history import api as history_api
    from message_history import ice_listener
    _HISTORY_ENABLED = True
except Exception as _err:  # noqa: BLE001
    print(f"[warn] Message history unavailable: {_err}", flush=True)
    _HISTORY_ENABLED = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _HISTORY_ENABLED:
        ice_listener.start()
    yield
    if _HISTORY_ENABLED:
        ice_listener.stop()


app = FastAPI(title="Cozmeeq Services", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

if _HISTORY_ENABLED:
    app.include_router(history_api.router)

# ── Config ────────────────────────────────────────────────────────────────────

API_KEY = os.environ.get("LK_API_KEY")
API_SECRET = os.environ.get("LK_API_SECRET")
LK_URL = os.environ.get("LK_URL")

if not API_KEY or not API_SECRET:
    raise RuntimeError("LK_API_KEY and LK_API_SECRET environment variables must be set")
if not LK_URL:
    raise RuntimeError("LK_URL environment variable must be set")


# ── Models ────────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    identity: str
    room: str


class TokenResponse(BaseModel):
    token: str
    url: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/token", response_model=TokenResponse)
def get_token(req: TokenRequest):
    if not req.identity or not req.room:
        raise HTTPException(status_code=400, detail="identity and room are required")

    token = (
        AccessToken(API_KEY, API_SECRET)
        .with_identity(req.identity)
        .with_grants(
            VideoGrants(
                room_join=True,
                room=req.room,
                can_publish=True,
                can_subscribe=True,
            )
        )
    )

    return TokenResponse(token=token.to_jwt(), url=LK_URL)
