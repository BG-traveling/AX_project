import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import typhoons, feedback, predict
from app.core.redis import close_redis

logger = logging.getLogger(__name__)

app = FastAPI(title="TyphoonPath API", version="1.0.0")

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://bg-traveling.github.io",
]
extra = os.getenv("ALLOWED_ORIGINS", "")
if extra:
    ALLOWED_ORIGINS += [o.strip() for o in extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(typhoons.router)
app.include_router(feedback.router)
app.include_router(predict.router)

@app.on_event("startup")
async def startup():
    """앱 시작 시 typhoons.json을 미리 메모리에 로드 (첫 요청 타임아웃 방지)"""
    try:
        from app.services.typhoon_service import _load_data
        data = _load_data()
        count = len(data.get("typhoons", []))
        logger.info("✅ typhoons.json 사전 로드 완료 — 태풍 %d개", count)
    except Exception as e:
        logger.warning("⚠️ typhoons.json 사전 로드 실패: %s", e)

@app.on_event("shutdown")
async def shutdown():
    await close_redis()

@app.get("/health")
def health():
    return {"status": "ok", "service": "TyphoonPath API"}
