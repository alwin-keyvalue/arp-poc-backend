import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.controllers.conversation_controller import router as conversation_router
from app.controllers.subscription_controller import router as subscription_router
from app.controllers.bot_controller import router as bot_router
from app.controllers.internal_controller import router as internal_router
from app.controllers.report_controller import router as report_router
from app.controllers.label_controller import router as label_router
from app.controllers.task_controller import router as task_router
from app.controllers.user_controller import router as user_router
from app.controllers.webhook_controller import router as webhook_router
from app.dependencies import close_http_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_http_client()

logging.basicConfig(level=logging.INFO)

app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(task_router)
app.include_router(label_router)
app.include_router(user_router)
app.include_router(report_router)
app.include_router(subscription_router)
app.include_router(conversation_router)
app.include_router(webhook_router)
app.include_router(bot_router)
app.include_router(internal_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
