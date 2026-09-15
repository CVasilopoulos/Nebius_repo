import asyncio
import json
import time
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .client import TokenFactoryClient, UsageLedger
from .config import Settings, load_settings
from .pipeline import Pipeline
from .samples import list_samples, recording_path


class Source(BaseModel):
    name: str = Field(default="log", max_length=120)
    text: str = Field(max_length=300_000)


class AnalyzeRequest(BaseModel):
    sources: list[Source] = Field(min_length=1, max_length=8)


def create_app(settings: Settings | None = None, client_factory=None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Postmortem Pilot")
    runs: dict[str, list[float]] = defaultdict(list)
    gate = asyncio.Semaphore(3)

    def make_client() -> TokenFactoryClient:
        if client_factory:
            return client_factory()
        return TokenFactoryClient(settings.api_key, settings.base_url, UsageLedger(settings.usage_log))

    def allow(ip: str) -> bool:
        now = time.time()
        runs[ip] = [t for t in runs[ip] if now - t < 86_400]
        if len(runs[ip]) >= settings.runs_per_ip_per_day:
            return False
        runs[ip].append(now)
        return True

    @app.get("/api/health")
    async def health():
        return {"ok": True, "live": settings.live or client_factory is not None, "models": {"extract": settings.extract_model, "reason": settings.reason_model, "verify": settings.verify_model}, "max_lines": settings.max_lines}

    @app.get("/api/samples")
    async def samples():
        return list_samples(settings.samples_dir)

    @app.post("/api/analyze")
    async def analyze(body: AnalyzeRequest, request: Request):
        if not (settings.live or client_factory):
            raise HTTPException(503, "Live analysis is disabled: NEBIUS_API_KEY is not configured. Use a recorded replay.")
        ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
        if not allow(ip):
            raise HTTPException(429, "Daily live-run limit reached for this address. Recorded replays are still available.")
        sources = [s.model_dump() for s in body.sources]

        async def stream():
            started = time.perf_counter()
            async with gate:
                client = make_client()
                try:
                    async for event in Pipeline(settings, client).run(sources):
                        event["t"] = round(time.perf_counter() - started, 3)
                        yield json.dumps(event) + "\n"
                except Exception as exc:
                    yield json.dumps({"type": "error", "message": f"{type(exc).__name__}: {str(exc)[:300]}"}) + "\n"
                finally:
                    await client.aclose()

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.get("/api/replay/{sample_id}")
    async def replay(sample_id: str, speed: float = 1.0):
        path = recording_path(settings.samples_dir, sample_id)
        if not path:
            raise HTTPException(404, "No recording for this sample")
        speed = min(max(speed, 0.25), 20.0)

        async def stream():
            previous = 0.0
            for raw in path.read_text().splitlines():
                if not raw.strip():
                    continue
                event = json.loads(raw)
                delay = max(0.0, float(event.get("t", previous)) - previous) / speed
                previous = float(event.get("t", previous))
                if delay:
                    await asyncio.sleep(min(delay, 8.0))
                event["replay"] = True
                yield json.dumps(event) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.get("/")
    async def index():
        return FileResponse(settings.static_dir / "index.html")

    app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
    return app


app = create_app()
