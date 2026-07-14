import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.controllers.conversation_controller import router as conversation_router
from app.controllers.subscription_controller import router as subscription_router
from app.controllers.task_controller import router as task_router
from app.controllers.user_controller import router as user_router
from app.controllers.webhook_controller import router as webhook_router
from app.dependencies import close_http_client

# Dev only 
# TODO: delete app/dev/ folder and remove these lines before production
from app.dev import router as dev_router, register_dev_hooks

register_dev_hooks()

# ------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_http_client()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(task_router)
app.include_router(user_router)
app.include_router(subscription_router)
app.include_router(conversation_router)
app.include_router(webhook_router)
app.include_router(dev_router)  # dev only — remove before production


@app.get("/health")
def health_check():
    return {"status": "ok"}
