"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import orjson
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from .cache import close_redis, init_redis
from .config import settings
from .db import close_pool, init_pool
from .routers.auth_router import router as auth_router
from .routers.datasets import router as datasets_router
from .routers.map_router import router as map_router
from .routers.stats_router import router as stats_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_pool()
    await init_redis()
    yield
    await close_pool()
    await close_redis()


app = FastAPI(
    title="Leipzig Open Data API",
    description="Authenticated API serving cleaned Leipzig open data for the map dashboard.",
    version="1.0.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(datasets_router, prefix="/api")
app.include_router(map_router, prefix="/api")
app.include_router(stats_router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    from .db import _pool
    if _pool is None:
        return ORJSONResponse({"status": "not ready"}, status_code=503)
    return {"status": "ready"}
