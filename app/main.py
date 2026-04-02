import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="HF Daily Papers", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory="static"), name="static")

    from app.routers.pages import router as pages_router
    from app.routers.api import router as api_router
    app.include_router(api_router)
    app.include_router(pages_router)

    return app
