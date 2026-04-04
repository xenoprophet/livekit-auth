import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from livekit.api import AccessToken, VideoGrants
from livekit.protocol import ingress as proto_ingress
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


class PublishTargetRequest(BaseModel):
    identity: str
    room: str
    trackType: str = "screen"
    protocol: str = "rtmp"


class PublishTargetResponse(BaseModel):
    protocol: str
    ingressId: str
    url: str
    streamKey: str
    participantIdentity: str
    participantName: str


def _detect_publish_protocol(url: str) -> str:
    raw = str(url or "").strip()
    if "://" in raw:
        return raw.split("://", 1)[0].lower()
    return "rtmp"


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


def _build_participant_identity(identity: str, track_type: str) -> str:
    base_identity = str(identity or "").strip()
    normalized_track_type = str(track_type or "screen").strip().lower()
    suffix = "screen" if normalized_track_type == "screen" else normalized_track_type
    return f"{base_identity}-{suffix}"


def _build_participant_name(identity: str, track_type: str) -> str:
    base_identity = str(identity or "").strip()
    normalized_track_type = str(track_type or "screen").strip().lower()
    label = "Screen" if normalized_track_type == "screen" else normalized_track_type.title()
    return f"{base_identity} ({label})"


@app.post("/publish-target", response_model=PublishTargetResponse)
async def create_publish_target(req: PublishTargetRequest):
    if not req.identity or not req.room:
        raise HTTPException(status_code=400, detail="identity and room are required")
    requested_protocol = str(req.protocol or "").strip().lower()
    if requested_protocol not in {"rtmp", "rtmps"}:
        raise HTTPException(status_code=400, detail="Only RTMP/RTMPS publish targets are currently supported")

    participant_identity = _build_participant_identity(req.identity, req.trackType)
    participant_name = _build_participant_name(req.identity, req.trackType)
    ingress_request = proto_ingress.CreateIngressRequest(
        input_type=proto_ingress.RTMP_INPUT,
        name=f"{participant_identity}-{req.room}",
        room_name=req.room,
        participant_identity=participant_identity,
        participant_name=participant_name,
        enable_transcoding=True,
    )

    try:
        async with api.LiveKitAPI(url=LK_URL, api_key=API_KEY, api_secret=API_SECRET) as lkapi:
            ingress_info = await lkapi.ingress.create_ingress(ingress_request)
    except Exception as exc:  # pragma: no cover - network/runtime failure path
        raise HTTPException(status_code=502, detail=f"Failed to create ingress: {exc}") from exc

    ingress_url = str(getattr(ingress_info, "url", "") or "")

    return PublishTargetResponse(
        protocol=_detect_publish_protocol(ingress_url),
        ingressId=str(getattr(ingress_info, "ingress_id", "") or ""),
        url=ingress_url,
        streamKey=str(getattr(ingress_info, "stream_key", "") or ""),
        participantIdentity=participant_identity,
        participantName=participant_name,
    )


@app.delete("/publish-target/{ingress_id}")
async def delete_publish_target(ingress_id: str):
    normalized_ingress_id = str(ingress_id or "").strip()
    if not normalized_ingress_id:
        raise HTTPException(status_code=400, detail="ingress_id is required")

    delete_request = proto_ingress.DeleteIngressRequest(ingress_id=normalized_ingress_id)
    try:
        async with api.LiveKitAPI(url=LK_URL, api_key=API_KEY, api_secret=API_SECRET) as lkapi:
            await lkapi.ingress.delete_ingress(delete_request)
    except Exception as exc:  # pragma: no cover - network/runtime failure path
        raise HTTPException(status_code=502, detail=f"Failed to delete ingress: {exc}") from exc

    return {"ok": True}
