import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit.api import AccessToken, VideoGrants
from pydantic import BaseModel


app = FastAPI(title="LiveKit Auth Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this in production.
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

API_KEY = os.environ.get("LK_API_KEY")
API_SECRET = os.environ.get("LK_API_SECRET")
LK_URL = os.environ.get("LK_URL")

if not API_KEY or not API_SECRET:
    raise RuntimeError("LK_API_KEY and LK_API_SECRET environment variables must be set")
if not LK_URL:
    raise RuntimeError("LK_URL environment variable must be set")


class TokenRequest(BaseModel):
    identity: str
    room: str


class TokenResponse(BaseModel):
    token: str
    url: str


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
