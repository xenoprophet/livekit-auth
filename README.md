# LiveKit Auth Service

Small FastAPI service that signs LiveKit room tokens for Cozmeeq.

The Electron client now publishes camera and screenshare directly with the
LiveKit browser SDK. This service only mints room tokens.

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

`LK_URL` should point at the LiveKit server you manage separately.

## Running

```bash
docker compose up -d
```

This compose file starts only the auth service. It does not provision LiveKit
or any media pipeline.

## Notes

- CORS is open by default for local/private setups. Tighten it before exposing
  this service publicly.
- This repo assumes direct LiveKit WebRTC publishing from the Electron client.
