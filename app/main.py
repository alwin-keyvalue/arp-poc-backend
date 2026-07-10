import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.controllers.subscription_controller import router as subscription_router
from app.controllers.task_controller import router as task_router
from app.controllers.webhook_controller import router as webhook_router
from app.dependencies import close_http_client

# Dev only — delete app/dev/ folder and remove these lines before production
from app.dev import router as dev_router, register_dev_hooks

register_dev_hooks()

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
app.include_router(subscription_router)
app.include_router(webhook_router)
app.include_router(dev_router)  # dev only — remove before production


@app.get("/health")
def health_check():
    return {"status": "ok"}
