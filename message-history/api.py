import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from .db import get_channel_history, get_dm_history, get_stats

API_SECRET = os.environ.get("API_SECRET", "")
SERVER_ID = int(os.environ.get("MURMUR_SERVER_ID", 1))
DEFAULT_LIMIT = int(os.environ.get("DEFAULT_PAGE_SIZE", 100))

router = APIRouter(prefix="/api")


def _require_auth(request: Request) -> None:
    if not API_SECRET:
        return
    auth = request.headers.get("Authorization", "")
    token = auth[len("Bearer "):] if auth.startswith("Bearer ") else ""
    if token != API_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/history/channel/{channel_id}")
def channel_history(
    channel_id: int,
    limit: int = DEFAULT_LIMIT,
    before: Optional[int] = None,
    _: None = Depends(_require_auth),
):
    rows = get_channel_history(
        server_id=SERVER_ID, channel_id=channel_id, before=before, limit=limit
    )
    return {"ok": True, "channelId": channel_id, "messages": [_fmt(r) for r in rows]}


@router.get("/history/dm")
def dm_history(
    userA: str,
    userB: str,
    limit: int = DEFAULT_LIMIT,
    before: Optional[int] = None,
    _: None = Depends(_require_auth),
):
    rows = get_dm_history(
        server_id=SERVER_ID, user_a=userA, user_b=userB, before=before, limit=limit
    )
    return {"ok": True, "userA": userA, "userB": userB, "messages": [_fmt(r) for r in rows]}


def _fmt(row: dict) -> dict:
    return {
        "id": row["id"],
        "ts": row["ts"],
        "actorName": row["actor_name"],
        "actorUserId": row["actor_user_id"],
        "type": row["msg_type"],
        "channelId": row["channel_id"],
        "recipients": json.loads(row["recipients"]) if row.get("recipients") else None,
        "text": row["text"],
    }
