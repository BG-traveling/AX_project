from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import typhoons, feedback, predict
from app.core.redis import close_redis

app = FastAPI(title="TyphoonPath API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(typhoons.router)
app.include_router(feedback.router)
app.include_router(predict.router)

@app.on_event("shutdown")
async def shutdown():
    await close_redis()

@app.get("/health")
def health():
    return {"status": "ok", "service": "TyphoonPath API"}
