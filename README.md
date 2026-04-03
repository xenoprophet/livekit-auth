# LiveKit Auth Service

Small FastAPI service that signs LiveKit room tokens for Cozmeeq.

The Electron client now publishes camera and screenshare directly with the
standard LiveKit WebRTC SDK. This service only needs to mint room tokens.

## What It Does

- accepts a Cozmeeq identity and room id
- returns a signed LiveKit JWT
- returns the LiveKit WebSocket URL the client should connect to

It does **not** manage media publishing, Redis, or any external video pipeline.

## Files

```text
livekit-auth/
|-- main.py
|-- requirements.txt
|-- Dockerfile
|-- docker-compose.yml
|-- livekit-config.yaml
`-- README.md
```

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
  "url": "ws://192.168.1.12:7880"
}
```

## Environment Variables

- `LK_API_KEY`
- `LK_API_SECRET`
- `LK_URL`

`LK_URL` should be your LiveKit WebSocket URL, for example:

```text
ws://192.168.1.12:7880
```

## Running

```bash
docker compose up -d
```

## Unraid Paths

This compose file is set up to use bind-mounted directories under:

```text
/mnt/user/appdata/livekit-auth/
```

Host directory layout:

```text
/mnt/user/appdata/livekit-auth/
|-- livekit/
|   `-- livekit-config.yaml
`-- redis/
```

The LiveKit service reads its config from:

```text
/etc/livekit/livekit-config.yaml
```

## Notes

- CORS is open by default for local/private setups. Tighten it before exposing
  this service publicly.
- This repo now assumes direct LiveKit WebRTC publishing from the Electron
  client.
- If your deployed LiveKit server config outside this repo still references
  older distributed media services, update that config too before restarting
  the stack.
