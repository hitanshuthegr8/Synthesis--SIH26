from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .core.config import settings
from .core.logging import get_logger
from .api.routes import (
    autopsy,
    blend,
    computation,
    demo,
    dossier,
    forecast_analysis,
    forecasts,
    grid,
    model_analysis,
    pipeline,
    reliability,
    sources,
    spatial,
    synthesis,
    system,
    verification,
)

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AIRAVAT starting", version=settings.VERSION, demo_mode=settings.DEMO_MODE)
    yield
    logger.info("AIRAVAT shutting down")

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(forecasts.router)
app.include_router(blend.router)
app.include_router(reliability.router)
app.include_router(verification.router)
# Fixed-path live routes first: /api/forecast/{run_id} would otherwise capture /api/forecast/grid.
app.include_router(spatial.router)
app.include_router(synthesis.router)
app.include_router(pipeline.router)
app.include_router(computation.router)
app.include_router(demo.router)
app.include_router(sources.router)
app.include_router(system.router)
app.include_router(autopsy.router)
app.include_router(forecast_analysis.router)
app.include_router(grid.router)
app.include_router(dossier.router)
app.include_router(model_analysis.router)

@app.get("/api/health")
async def health():
    database = "ok"
    try:
        from app.storage.database import SQLiteDatabase
        from app.core.config import settings as cfg

        raw = cfg.DATABASE_URL.removeprefix("sqlite:///")
        db_path = raw if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":") else raw
        with SQLiteDatabase(db_path).connect() as connection:
            connection.execute("SELECT 1")
    except Exception:
        database = "unavailable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "version": settings.VERSION,
        "demo_mode": settings.DEMO_MODE,
        "database": database,
    }
