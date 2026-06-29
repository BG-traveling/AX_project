from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    ANTHROPIC_API_KEY: str = ""
    REDIS_URL: str = "redis://localhost:6379"
    DATA_PATH: Path = Path(__file__).parent.parent.parent / "data" / "typhoons.json"
    CACHE_TTL: int = 3600  # 1시간

    class Config:
        env_file = ".env"

settings = Settings()
