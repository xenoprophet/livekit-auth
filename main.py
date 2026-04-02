from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from livekit.api import AccessToken, VideoGrants
import os
import aiohttp
import time

app = FastAPI(title="LiveKit Auth Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this in production
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

API_KEY = os.environ.get("LK_API_KEY")
API_SECRET = os.environ.get("LK_API_SECRET")
LK_URL = os.environ.get("LK_URL")
# HTTP URL for the LiveKit API (ingress management etc.)
LK_HTTP_URL = os.environ.get("LK_HTTP_URL") or LK_URL.replace("ws://", "http://").replace("wss://", "https://")

if not API_KEY or not API_SECRET:
    raise RuntimeError("LK_API_KEY and LK_API_SECRET environment variables must be set")
if not LK_URL:
    raise RuntimeError("LK_URL environment variable must be set")

def _make_twirp_token(grants: dict) -> str:
    """Create a signed JWT for LiveKit Twirp API calls."""
    import jwt
    now = int(time.time())
    payload = {
        "iss": API_KEY,
        "sub": API_KEY,
        "iat": now,
        "exp": now + 600,
        "video": grants,
    }
    return jwt.encode(payload, API_SECRET, algorithm="HS256")


async def _twirp_request(method: str, body: dict) -> dict:
    """Make a Twirp RPC call to the LiveKit server."""
    url = f"{LK_HTTP_URL}/twirp/livekit.Ingress/{method}"
    token = _make_twirp_token({"ingressAdmin": True})
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    ssl_ctx = False if LK_HTTP_URL.startswith("http://") else None
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers, ssl=ssl_ctx) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise Exception(data.get("msg", f"Twirp error {resp.status}"))
            return data


class TokenRequest(BaseModel):
    identity: str  # Mumble username
    room: str      # Mumble channel ID


class TokenResponse(BaseModel):
    token: str
    url: str


class WhipRequest(BaseModel):
    identity: str       # Mumble username
    room: str           # Mumble channel ID
    track_type: str     # "screen" or "camera"


class WhipResponse(BaseModel):
    token: str
    url: str
    whip_url: str


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
async def get_whip_endpoint(req: WhipRequest):
    if not req.identity or not req.room:
        raise HTTPException(status_code=400, detail="identity and room are required")

    if req.track_type not in ("screen", "camera"):
        raise HTTPException(status_code=400, detail="track_type must be 'screen' or 'camera'")

    participant_identity = f"{req.identity}-{req.track_type}"
    ingress_name = f"{req.room}-{participant_identity}"

    # Clean up any existing ingress with the same name
    try:
        existing = await _twirp_request("ListIngress", {})
        for ing in existing.get("items", []):
            if ing.get("name") == ingress_name:
                await _twirp_request("DeleteIngress", {"ingress_id": ing["ingress_id"]})
    except Exception:
        pass  # If listing fails, proceed to create

    # Create a new WHIP ingress (input_type 1 = WHIP_INPUT)
    try:
        ingress = await _twirp_request("CreateIngress", {
            "input_type": 1,
            "name": ingress_name,
            "room_name": req.room,
            "participant_identity": participant_identity,
            "participant_name": f"{req.identity} ({req.track_type})",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create ingress: {str(e)}")

    import logging
    logging.info(f"Ingress response: {ingress}")

    # Also generate a viewer token for the client to subscribe to tracks
    viewer_token = (
        AccessToken(API_KEY, API_SECRET)
        .with_identity(req.identity)
        .with_grants(
            VideoGrants(
                room_join=True,
                room=req.room,
                can_publish=False,
                can_subscribe=True,
            )
        )
    )

    # The ingress response has 'url' (the full WHIP endpoint with stream key)
    # and 'stream_key' as separate fields
    whip_url = ingress.get("url", "")
    stream_key = ingress.get("stream_key", "")

    # If url is just the base, append the stream key
    if stream_key and whip_url and not whip_url.endswith(stream_key):
        whip_url = f"{whip_url}/{stream_key}"

    return WhipResponse(
        token=viewer_token.to_jwt(),
        url=LK_URL,
        whip_url=whip_url,
    )
