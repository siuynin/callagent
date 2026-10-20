"""Voice spike server. Binds to 127.0.0.1 by default: the API key never leaves this process.

Browser protocol on /ws/spike:
  client -> server: binary = PCM16 16 kHz mono; text {"type": "hangup"}
  server -> client: binary = PCM16 at the rate announced in {"type": "audio_format"}; text = JSON events
"""

import asyncio
import json
import logging

from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from gateway import evals
from gateway.agent import fetch_active_agent, fetch_routing, settings_for
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
        # live calls run the published active agent version (never a draft); bundled prompt if unreachable
        agent = await fetch_active_agent(settings)
        # in/out of hours from the tenant calendar (AC24); unknown -> answer as in hours
        routing = await fetch_routing(settings)
        provider = provider or (agent.config.get("provider") if agent else None)
        live_provider = make_provider(
            settings_for(settings, agent, provider or settings.ai_provider), provider
        )
        session = CallSession(
            live_provider,
            transport,
            settings_for(settings, agent, live_provider.name),
            mode="browser_phone_sim" if codec else "browser",
            phone_sim=codec,
            persist=True,  # spike calls appear in the web app when ADR 0006 config is set
            agent=agent,
            routing=routing,
        )
        summary = await session.run()
        log.info("call %s done: %s", summary["call_id"], summary)
    except Exception as exc:  # noqa: BLE001 - report to the page instead of a silent close
        log.exception("spike session failed")
        await transport.notify({"type": "error", "message": str(exc)})
    finally:
        if not transport.closed:
            await ws.close()


@app.post("/internal/eval", status_code=202)
async def internal_eval(req: evals.EvalRequest, x_service_token: str | None = Header(default=None)):
    """Backend asks for a publish-gating eval of a draft agent version (ADR 0007)."""
    settings = get_settings()
    if not evals.authorized(settings, x_service_token, req.tenant_id):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    if evals.busy():
        return JSONResponse(status_code=409, content={"error": "eval_running"})
    asyncio.create_task(evals.run_suite(settings, req))
    return {"accepted": True, "scenarios": len(evals.scenario_paths(settings))}


def run() -> None:
    import uvicorn

    s = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run("gateway.main:app", host=s.gateway_host, port=s.gateway_port)


if __name__ == "__main__":
    run()
