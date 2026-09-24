from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .core.config import settings
from .core.logging import get_logger
from .api.routes import forecasts, blend, reliability, verification

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SYNTHESIS starting", version=settings.VERSION, demo_mode=settings.DEMO_MODE)
    yield
    logger.info("SYNTHESIS shutting down")

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

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": settings.VERSION,
        "demo_mode": settings.DEMO_MODE
    }
