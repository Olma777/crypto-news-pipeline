"""FastAPI app with APScheduler. Entry point for the service."""

import logging

from fastapi import FastAPI

from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Crypto News Pipeline", version="1.0.0")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status():
    return {"status": "ok", "message": "Pipeline not yet initialized"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
