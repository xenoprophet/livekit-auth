"""
Connects to Murmur via ZeroC Ice, registers a ServerCallback, and stores
every userTextMessage event in SQLite.

Murmur config required (murmur.ini):
    ice=tcp -h 127.0.0.1 -p 6502
    icesecretwrite=<secret>   # only if MURMUR_ICE_SECRET is set
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

MURMUR_HOST = os.environ.get("MURMUR_ICE_HOST", "127.0.0.1")
MURMUR_PORT = int(os.environ.get("MURMUR_ICE_PORT", 6502))
ICE_SECRET = os.environ.get("MURMUR_ICE_SECRET", "")
SERVER_ID = int(os.environ.get("MURMUR_SERVER_ID", 1))
CALLBACK_HOST = os.environ.get("CALLBACK_HOST", "127.0.0.1")

# Reconnect backoff in seconds: 3, 6, 12, 24, 60
_BACKOFF = [3, 6, 12, 24, 60]

_stopped = threading.Event()
_thread: threading.Thread | None = None


def _ctx() -> dict:
    return {"secret": ICE_SECRET} if ICE_SECRET else {}


def _load_murmur():
    try:
        from .generated import Murmur_ice  # noqa: PLC0415
        return Murmur_ice
    except Exception as exc:
        raise RuntimeError(
            "Generated Murmur bindings not found. "
            "Ensure slice2py ran during the Docker build."
        ) from exc


def _run() -> None:
    try:
        import Ice  # noqa: PLC0415
    except ImportError:
        logger.error("[ice] zeroc-ice is not installed — history listener disabled")
        return

    try:
        Murmur = _load_murmur()
    except RuntimeError as exc:
        logger.error("[ice] %s", exc)
        return

    from .db import save_message  # noqa: PLC0415

    attempt = 0
    while not _stopped.is_set():
        props = Ice.createProperties()
        props.setProperty("Ice.Default.EncodingVersion", "1.0")
        props.setProperty("Ice.Default.Timeout", "5000")
        props.setProperty("Ice.RetryIntervals", "-1")
        init_data = Ice.InitializationData()
        init_data.properties = props
        ic = Ice.initialize(init_data)

        try:
            base = ic.stringToProxy(f"Meta:tcp -h {MURMUR_HOST} -p {MURMUR_PORT}")
            meta = Murmur.MetaPrx.checkedCast(base)
            if not meta:
                raise RuntimeError("Meta proxy cast failed — is Murmur running with ICE?")

            server = meta.getServer(SERVER_ID, _ctx())
            if not server:
                raise RuntimeError(f"Virtual server {SERVER_ID} not found")

            logger.info(
                "[ice] Connected to Murmur at %s:%d (server %d)",
                MURMUR_HOST, MURMUR_PORT, SERVER_ID,
            )
            attempt = 0

            adapter = ic.createObjectAdapterWithEndpoints(
                "CallbackAdapter", f"tcp -h {CALLBACK_HOST}"
            )
            adapter.activate()

            class ServerCallbackI(Murmur.ServerCallback):
                def userTextMessage(self, user, message, current=None):
                    try:
                        actor_name = user.name or "unknown"
                        actor_user_id = (
                            user.userid
                            if (user.userid is not None and user.userid >= 0)
                            else None
                        )
                        text = message.text or ""
                        if not text:
                            return

                        has_channels = bool(message.channels)
                        has_trees = bool(message.trees)
                        has_users = bool(message.sessions)

                        if has_channels or has_trees:
                            channel_id = (message.channels or message.trees)[0]
                            save_message(
                                server_id=SERVER_ID,
                                actor_name=actor_name,
                                actor_user_id=actor_user_id,
                                msg_type="channel",
                                channel_id=channel_id,
                                recipients=None,
                                text=text,
                            )
                        elif has_users:
                            save_message(
                                server_id=SERVER_ID,
                                actor_name=actor_name,
                                actor_user_id=actor_user_id,
                                msg_type="dm",
                                channel_id=None,
                                recipients=list(message.sessions),
                                text=text,
                            )
                        else:
                            save_message(
                                server_id=SERVER_ID,
                                actor_name=actor_name,
                                actor_user_id=actor_user_id,
                                msg_type="broadcast",
                                channel_id=None,
                                recipients=None,
                                text=text,
                            )
                    except Exception as exc:  # noqa: BLE001
                        logger.error("[ice] Error saving message: %s", exc)

                def userConnected(self, state, current=None): pass
                def userDisconnected(self, state, current=None): pass
                def userStateChanged(self, state, current=None): pass
                def channelCreated(self, state, current=None): pass
                def channelRemoved(self, state, current=None): pass
                def channelStateChanged(self, state, current=None): pass

            servant = ServerCallbackI()
            proxy = adapter.addWithUUID(servant)
            cb_prx = Murmur.ServerCallbackPrx.uncheckedCast(proxy)
            server.addCallback(cb_prx, _ctx())
            logger.info("[ice] ServerCallback registered — listening for messages.")

            ic.waitForShutdown()
            if not _stopped.is_set():
                logger.warning("[ice] Communicator shut down — will reconnect.")

        except Exception as exc:  # noqa: BLE001
            logger.error("[ice] Connection error: %s", exc)
        finally:
            try:
                ic.destroy()
            except Exception:  # noqa: BLE001
                pass

        if _stopped.is_set():
            break

        delay = _BACKOFF[min(attempt, len(_BACKOFF) - 1)]
        attempt += 1
        logger.info("[ice] Reconnecting in %ds (attempt %d)…", delay, attempt)
        _stopped.wait(delay)


def start() -> None:
    global _thread
    _stopped.clear()
    _thread = threading.Thread(target=_run, name="ice-listener", daemon=True)
    _thread.start()


def stop() -> None:
    _stopped.set()
