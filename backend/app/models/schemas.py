from pydantic import BaseModel, Field
from typing import Optional

# ── 태풍 데이터 스키마 ──────────────────────────
class TrackPoint(BaseModel):
    dt: str
    lat: float
    lng: float
    wind_ms: float
    pressure: Optional[int]
    intensity: str  # TD | TS | TY | STY

class TyphoonSummary(BaseModel):
    id: str
    name_en: str
    year: int
    season_no: int
    track_count: int

class TyphoonDetail(TyphoonSummary):
    track: list[TrackPoint]

# ── 피드백 요청/응답 스키마 ──────────────────────
class UserTrackPoint(BaseModel):
    lat: float
    lng: float

class UserVariables(BaseModel):
    pressure: float
    temperature: float

class FeedbackRequest(BaseModel):
    typhoon_id: str
    user_track: list[UserTrackPoint]
    user_variables: UserVariables

class ErrorSummary(BaseModel):
    avg_distance_km: float
    direction_bias: str

class FeedbackResponse(BaseModel):
    actual_track: list[UserTrackPoint]
    feedback: str
    error_summary: ErrorSummary

# ── 경로 예측 요청/응답 스키마 ───────────────────
class PredictRequest(BaseModel):
    start_lat: float = Field(..., description="시작 위도")
    start_lng: float = Field(..., description="시작 경도")
    pressure: float  = Field(..., description="초기 중심기압 (hPa, 850~1010)")
    sst: float       = Field(..., description="해수면 온도 (C, 20~35)")
    month: int       = Field(..., description="예측 월 (1~12)")

    # 추가 입력 파라미터 (선택 — 없으면 기압에서 자동 추정)
    wind_1min_ms:  Optional[float] = Field(None, description="1분 지속풍속 (m/s, 0~85)")
    wind_10min_ms: Optional[float] = Field(None, description="10분 지속풍속 (m/s, 0~75)")
    diameter_km:   Optional[float] = Field(None, description="태풍 최대직경 (km, 100~2000)")

class PredictedPoint(BaseModel):
    lat: float
    lng: float
    pressure: float
    wind_ms: float
    intensity: str
    hour: int

class AnalogTyphoon(BaseModel):
    id: str
    name_en: str
    year: int
    similarity: float
    track: list[UserTrackPoint]

class PredictResponse(BaseModel):
    predicted_track: list[PredictedPoint]
    analogs: list[AnalogTyphoon]
    ai_explanation: str
    prediction_method: str = "analog_blending"   # "ml" | "analog_blending" | "physics"
