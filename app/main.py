import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.controllers.task_controller import router as task_router
from app.dependencies import close_http_client
from app.integrations.microsoft_graph.router import router as microsoft_graph_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_http_client()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(task_router)
app.include_router(microsoft_graph_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
