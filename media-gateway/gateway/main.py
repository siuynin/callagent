"""Voice spike server. Binds to 127.0.0.1 by default: the API key never leaves this process.

Browser protocol on /ws/spike:
  client -> server: binary = PCM16 16 kHz mono; text {"type": "hangup"}
  server -> client: binary = PCM16 at the rate announced in {"type": "audio_format"}; text = JSON events
"""

import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gateway.config import ROOT, get_settings
from gateway.providers import make_provider
from gateway.session import CallSession

log = logging.getLogger("gateway")
app = FastAPI(title="VoiceOS media gateway (spike)")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class WebSocketTransport:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self._lock = asyncio.Lock()
        self._announced_rate: int | None = None
        self.closed = False

    async def recv_audio(self) -> bytes | None:
        while True:
            try:
                msg = await self.ws.receive()
            except (WebSocketDisconnect, RuntimeError):
                self.closed = True
                return None
            if msg["type"] == "websocket.disconnect":
                self.closed = True
                return None
            if msg.get("bytes"):
                return msg["bytes"]
            if msg.get("text"):
                data = json.loads(msg["text"])
                if data.get("type") == "hangup":
                    return None

    async def _send(self, *, text: str | None = None, data: bytes | None = None) -> None:
        if self.closed:
            return
        async with self._lock:
            try:
                if data is not None:
                    await self.ws.send_bytes(data)
                else:
                    await self.ws.send_text(text)
            except (WebSocketDisconnect, RuntimeError):
                self.closed = True

    async def play(self, pcm: bytes, rate: int) -> None:
        if self._announced_rate != rate:
            self._announced_rate = rate
            await self.notify({"type": "audio_format", "rate": rate})
        await self._send(data=pcm)

    async def clear_playback(self) -> None:
        await self.notify({"type": "clear"})

    async def notify(self, message: dict) -> None:
        await self._send(text=json.dumps(message, ensure_ascii=False))


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "spike.html")


@app.get("/api/info")
def info():
    s = get_settings()
    available = s.available_providers()
    default = s.ai_provider if s.ai_provider in available else "mock"
    return {
        "default_provider": default,
        # only providers with a key on this machine; the key itself never leaves the gateway
        "providers": [{"name": p, "model": s.model_for(p)} for p in available],
        "business_name": s.business_name,
        "persist": bool(s.gateway_service_token and s.gateway_tenant_id),
    }


@app.websocket("/ws/spike")
async def spike(ws: WebSocket, phone_sim: str | None = None, provider: str | None = None):
    await ws.accept()
    settings = get_settings()
    transport = WebSocketTransport(ws)
    codec = phone_sim if phone_sim in ("alaw", "ulaw") else None
    try:
        live_provider = make_provider(settings, provider)
        session = CallSession(
            live_provider,
            transport,
            settings,
            mode="browser_phone_sim" if codec else "browser",
            phone_sim=codec,
            persist=True,  # spike calls appear in the web app when ADR 0006 config is set
        )
        summary = await session.run()
        log.info("call %s done: %s", summary["call_id"], summary)
    except Exception as exc:  # noqa: BLE001 - report to the page instead of a silent close
        log.exception("spike session failed")
        await transport.notify({"type": "error", "message": str(exc)})
    finally:
        if not transport.closed:
            await ws.close()


def run() -> None:
    import uvicorn

    s = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run("gateway.main:app", host=s.gateway_host, port=s.gateway_port)


if __name__ == "__main__":
    run()
