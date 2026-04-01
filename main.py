from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from livekit.api import LiveKitAPI, AccessToken, VideoGrants
from livekit.protocol.ingress import CreateIngressRequest, IngressInput
import os
import ssl
import aiohttp

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

def _make_lk_api():
    """Create LiveKitAPI with SSL disabled for plain HTTP URLs."""
    if LK_HTTP_URL.startswith("http://"):
        connector = aiohttp.TCPConnector(ssl=False)
        session = aiohttp.ClientSession(connector=connector)
        return LiveKitAPI(url=LK_HTTP_URL, api_key=API_KEY, api_secret=API_SECRET, session=session)
    return LiveKitAPI(url=LK_HTTP_URL, api_key=API_KEY, api_secret=API_SECRET)


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

    api = _make_lk_api()
    try:
        # Clean up any existing ingress with the same name
        try:
            existing = await api.ingress.list_ingress()
            for ing in existing:
                if ing.name == ingress_name:
                    await api.ingress.delete_ingress(ing.ingress_id)
        except Exception:
            pass  # If listing fails, proceed to create

        # Create a new WHIP ingress
        try:
            ingress = await api.ingress.create_ingress(
                CreateIngressRequest(
                    input_type=IngressInput.WHIP_INPUT,
                    name=ingress_name,
                    room_name=req.room,
                    participant_identity=participant_identity,
                    participant_name=f"{req.identity} ({req.track_type})",
                )
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create ingress: {str(e)}")
    finally:
        await api.aclose()

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

    return WhipResponse(
        token=viewer_token.to_jwt(),
        url=LK_URL,
        whip_url=ingress.url,
    )
