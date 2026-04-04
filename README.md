# LiveKit Auth / Ingress Stack

This folder now contains the small FastAPI auth service Cozmeeq uses, plus a
Docker Compose stack for:

- LiveKit server
- LiveKit Ingress
- Redis
- Auth middleware

The current Cozmeeq screenshare path is:

- bundled FFmpeg on the client
- GPU H.264 encode when available
- publish to LiveKit Ingress
- reflected into the LiveKit room

The current ingress target for screenshare is WHIP.

## Endpoints

### `GET /health`

Simple health check.

### `POST /token`

Request body:

```json
{
  "identity": "username",
  "room": "123"
}
```

Response:

```json
{
  "token": "eyJhbGciOiJIUzI1NiJ9...",
  "url": "ws://192.168.1.13:7880"
}
```

### `POST /publish-target`

Creates a reusable LiveKit ingress publish target for Cozmeeq's FFmpeg
screenshare publisher. The app now requests a `whip` target by default.

## Configuration

The stack now uses mounted config/data files that fit an Unraid-style setup
better than embedded environment blobs.

Mounted paths used by the compose file:

- `/mnt/user/appdata/livekit-auth/config/livekit.yaml`
- `/mnt/user/appdata/livekit-auth/config/ingress.yaml`
- `/mnt/user/appdata/livekit-auth/data/redis`

The current hardcoded LAN addresses are:

- auth: `192.168.1.12`
- livekit: `192.168.1.13`
- ingress: `192.168.1.14`
- redis: `192.168.1.15`

The current publish target is:

- `ingress.whip_base_url = http://192.168.1.14:8080/whip`

## HTTPS Note

The stack is currently set to plain `http://` WHIP on the LAN so it works
directly on `br0` without guessing a TLS endpoint.

If you later want secure external ingest, change `ingress.whip_base_url` in
`livekit.yaml` to your real HTTPS front-end URL, for example
`https://stream.example.com/whip`, and terminate TLS in front of Ingress.

## Running

```bash
docker compose up -d
```

## Notes

- LiveKit and Ingress must share the same Redis instance.
- The compose file is set up for Unraid `br0` style static container IPs.
- This compose file already targets `/mnt/user/appdata/livekit-auth/...` host
  paths for Unraid-style bind mounts.
- CORS is open by default for local/private setups. Tighten it before exposing
  the auth service publicly.
