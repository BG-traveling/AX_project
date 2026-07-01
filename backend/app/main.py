import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import typhoons, feedback, predict
from app.core.redis import close_redis

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
    """앱 시작 시 typhoons.json + LSTM 모델을 미리 메모리에 로드 (첫 요청 타임아웃 방지)"""
    # 1. typhoons.json 사전 로드
    try:
        from app.services.typhoon_service import _load_data
        data = _load_data()
        count = len(data.get("typhoons", []))
        print(f"[startup] ✅ typhoons.json 로드 완료 — 태풍 {count}개", flush=True)
    except Exception as e:
        print(f"[startup] ⚠️ typhoons.json 로드 실패: {e}", flush=True)

    # 2. LSTM 모델 사전 로드 (첫 예측 요청에서 지연 방지)
    try:
        from app.services.lstm_prediction_service import lstm_available
        if lstm_available():
            print("[startup] ✅ LSTM 모델 로드 완료", flush=True)
        else:
            print("[startup] ℹ️  LSTM 모델 없음 — Analog Blending 사용", flush=True)
    except Exception as e:
        print(f"[startup] ⚠️ LSTM 로드 실패: {e}", flush=True)

@app.on_event("shutdown")
async def shutdown():
    await close_redis()

@app.get("/health")
def health():
    return {"status": "ok", "service": "TyphoonPath API"}
