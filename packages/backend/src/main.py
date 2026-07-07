# src/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from structlog import get_logger

from src.config import settings

logger = get_logger()

app = FastAPI(
    title="AI Town Backend",
    description="World Engine + LangGraph",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    logger.info("ai_town_backend_started", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}