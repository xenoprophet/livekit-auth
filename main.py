import os

import aiohttp
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


class WhipRequest(BaseModel):
    identity: str
    room: str
    track_type: str | None = None


class WhipResponse(BaseModel):
    whip_url: str
    stream_key: str
    token: str
    url: str


def _make_twirp_url(method: str) -> str:
    """Build the Twirp RPC URL from the LiveKit WS URL."""
    base = LK_URL.replace("ws://", "http://").replace("wss://", "https://")
    base = base.rstrip("/")
    return f"{base}/twirp/livekit.Ingress/{method}"


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


@app.post("/whip", response_model=WhipResponse)
async def create_whip_ingress(req: WhipRequest):
    """Create a WHIP ingress so GStreamer can publish GPU-encoded video."""
    if not req.identity or not req.room:
        raise HTTPException(status_code=400, detail="identity and room are required")

    # Create an access token for the Twirp API call
    token = (
        AccessToken(API_KEY, API_SECRET)
        .with_identity(req.identity)
        .with_grants(
            VideoGrants(
                room_join=True,
                room=req.room,
                can_publish=True,
                can_subscribe=True,
                ingress_admin=True,
            )
        )
    )
    auth_jwt = token.to_jwt()

    # Use Twirp API to create a WHIP ingress (input_type 1 = WHIP_INPUT)
    twirp_url = _make_twirp_url("CreateIngress")
    use_ssl = twirp_url.startswith("https://")

    payload = {
        "input_type": 1,
        "name": f"whip-{req.track_type or 'stream'}-{req.identity}-{req.room}",
        "room_name": req.room,
        "participant_identity": f"{req.identity}-stream",
        "participant_name": req.identity,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                twirp_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {auth_jwt}",
                },
                ssl=use_ssl if use_ssl else False,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to create ingress: {body}",
                    )
                data = await resp.json()
    except aiohttp.ClientError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create ingress: {exc}",
        )

    stream_key = data.get("streamKey", "")

    # Build the WHIP URL from the ingress service
    base = LK_URL.replace("ws://", "http://").replace("wss://", "https://").rstrip("/")
    whip_url = f"{base}/whip/{stream_key}" if stream_key else ""

    return WhipResponse(
        whip_url=whip_url,
        stream_key=stream_key,
        token=auth_jwt,
        url=LK_URL,
    )
