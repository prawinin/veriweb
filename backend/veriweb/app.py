import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from threading import RLock
from typing import cast

import anyio
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from numpy.typing import NDArray

from veriweb.config import Settings
from veriweb.model import ModelClient
from veriweb.pipeline import Researcher
from veriweb.retrieval import Encoder
from veriweb.schemas import ResearchRequest, RunEvent

logger = logging.getLogger("veriweb")


def load_encoder(settings: Settings) -> Encoder | None:
    if not settings.embeddings_model:
        return None
    from tqdm import tqdm

    # Encoding is threaded in one process; avoid a process-shared progress-bar semaphore.
    tqdm.set_lock(RLock())
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        settings.embeddings_model, device=settings.embeddings_device, local_files_only=True
    )

    def encode(texts: list[str]) -> NDArray[np.float32]:
        return cast(
            NDArray[np.float32],
            model.encode(texts, batch_size=16, show_progress_bar=False, normalize_embeddings=True),
        )

    return encode


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        os.environ.setdefault("OMP_NUM_THREADS", "6")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        encoder: Encoder | None = None
        if settings.embeddings_model:
            try:
                encoder = await asyncio.to_thread(load_encoder, settings)
            except (ImportError, OSError, ValueError):
                logger.warning("Embedding model unavailable; retrieval uses BM25")
        app.state.encoder = encoder
        try:
            yield
        finally:
            app.state.encoder = None
            if settings.embeddings_device == "cuda":
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

    app = FastAPI(title="Veriweb", lifespan=lifespan, docs_url="/api/docs")
    app.state.busy = False
    app.state.encoder = None
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    async def stream_factory(question: str, mode: str) -> AsyncIterator[str]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.fetch_timeout),
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_connections=6),
        ) as client:
            researcher = Researcher(settings, client, app.state.encoder)
            researcher.model_available = (
                await researcher.model.available() if mode == "research" else False
            )
            async for event in researcher.run(question, mode):
                yield event.model_dump_json() + "\n"

    app.state.stream_factory = stream_factory

    @app.get("/api/status")
    async def status() -> dict[str, object]:
        async with httpx.AsyncClient(trust_env=False) as client:
            available = await ModelClient(settings, client).available()
        return {
            "available": available,
            "model": settings.model_name if settings.model_url else None,
            "backend": settings.model_backend,
            "backend_verified": False,
            "embeddings": bool(app.state.encoder),
            "busy": app.state.busy,
            "message": "Model connected"
            if available
            else "Connect a model for synthesis. Live evidence retrieval is available.",
        }

    @app.post("/api/research")
    async def research(payload: ResearchRequest, request: Request) -> StreamingResponse:
        if app.state.busy:
            raise HTTPException(
                status_code=409, detail="A research run is already active. Wait or cancel it first."
            )
        app.state.busy = True

        async def generate() -> AsyncIterator[str]:
            started = time.monotonic()
            iterator = app.state.stream_factory(payload.question, payload.mode).__aiter__()
            pending: asyncio.Task[str] | None = None
            try:
                while True:
                    if time.monotonic() - started > settings.run_timeout:
                        yield (
                            RunEvent(
                                type="error",
                                stage="timeout",
                                message="Research exceeded its time budget. Try a narrower question.",
                                level="error",
                            ).model_dump_json()
                            + "\n"
                        )
                        break
                    if await request.is_disconnected():
                        break
                    if pending is None:
                        pending = asyncio.create_task(anext(iterator))
                    done, _ = await asyncio.wait({pending}, timeout=2)
                    if not done:
                        yield (
                            RunEvent(
                                type="heartbeat",
                                stage="working",
                                message="Research is active.",
                                elapsed=round(time.monotonic() - started, 2),
                            ).model_dump_json()
                            + "\n"
                        )
                        continue
                    try:
                        chunk = pending.result()
                    except StopAsyncIteration:
                        break
                    pending = None
                    yield chunk
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Research failed: %s", type(exc).__name__)
                yield (
                    RunEvent(
                        type="error",
                        stage="error",
                        message="Research stopped unexpectedly. Check service configuration and retry.",
                        level="error",
                    ).model_dump_json()
                    + "\n"
                )
            finally:
                try:
                    with anyio.CancelScope(shield=True):
                        if pending is not None:
                            pending.cancel()
                            await asyncio.gather(pending, return_exceptions=True)
                        await iterator.aclose()
                finally:
                    app.state.busy = False

        return StreamingResponse(
            generate(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return app


app = create_app()
