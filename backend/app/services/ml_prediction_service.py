"""
ML 기반 태풍 경로 예측 서비스
훈련된 GradientBoosting 모델을 로드하여 실시간 경로 예측.
"""

import math
import json
import logging
from pathlib import Path
from typing import Optional

from app.models.schemas import PredictedPoint

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"

# ── 모델 캐시 (None은 캐시하지 않아 재시도 가능) ──────────
_model_cache: dict | None = None


def _load_models() -> dict | None:
    """joblib 모델 로드. None은 캐시하지 않아 pkl 생성 후 재시도 가능."""
    global _model_cache
    if _model_cache is not None:
        return _model_cache

    try:
        import joblib
    except ImportError:
        logger.warning("joblib 미설치 — pip install joblib")
        return None

    lat_path  = DATA_DIR / "track_model_lat.pkl"
    lng_path  = DATA_DIR / "track_model_lng.pkl"
    pres_path = DATA_DIR / "pres_model.pkl"
    meta_path = DATA_DIR / "model_meta.json"

    if not all(p.exists() for p in [lat_path, lng_path, pres_path]):
        logger.info("ML 모델 파일 없음 → Analog Blending 폴백")
        return None

    try:
        m = {
            "lat":  joblib.load(lat_path),
            "lng":  joblib.load(lng_path),
            "pres": joblib.load(pres_path),
            "meta": {},
        }
        if meta_path.exists():
            with open(meta_path) as f:
                m["meta"] = json.load(f)
        logger.info(
            "ML 모델 로드 완료 — 위치오차 %.1f km, 스킬 +%.1f%%",
            m["meta"].get("pos_error_mean_km", 0),
            m["meta"].get("skill_score_pct", 0),
        )
        _model_cache = m
        return _model_cache
    except Exception as e:
        logger.error("ML 모델 로드 실패: %s", e)
        return None


def ml_available() -> bool:
    return _load_models() is not None


def get_model_meta() -> dict:
    m = _load_models()
    return m["meta"] if m else {}


# ── 피처 생성 ─────────────────────────────────────────────
def _make_feature(lat, lng, pres, w1, w10, diam, month, prev_dlat, prev_dlng):
    lsm = math.sin(2 * math.pi * month / 12)
    lcm = math.cos(2 * math.pi * month / 12)
    return [lat, lng, pres, w1, w10, diam, month, prev_dlat, prev_dlng,
            lsm * lat, lcm * lat]


def _pressure_to_wind(pressure: float) -> float:
    delta = max(0.0, 1010 - pressure)
    return min(85.0, delta ** 0.644 * 3.92)


def _classify_intensity(wind_ms: float) -> str:
    if wind_ms < 17: return "TD"
    if wind_ms < 25: return "TS"
    if wind_ms < 33: return "TY"
    return "STY"


# ── 메인 예측 함수 ─────────────────────────────────────────
def ml_predict(
    start_lat: float,
    start_lng: float,
    pressure: float,
    sst: float,
    wind_1min_ms: Optional[float],
    wind_10min_ms: Optional[float],
    diameter_km: Optional[float],
    month: int,
    max_steps: int = 80,   # 소멸 조건(pres≥1008) 도달까지 최대 480h
) -> list[PredictedPoint]:
    models = _load_models()
    if models is None:
        return []

    m_lat  = models["lat"]
    m_lng  = models["lng"]
    m_pres = models["pres"]

    if wind_1min_ms is None or wind_1min_ms <= 0:
        wind_1min_ms = _pressure_to_wind(pressure)
    if wind_10min_ms is None or wind_10min_ms <= 0:
        wind_10min_ms = wind_1min_ms * 0.88
    if diameter_km is None or diameter_km <= 0:
        diameter_km = 300.0

    track: list[PredictedPoint] = []
    lat, lng, pres = start_lat, start_lng, pressure
    w1, w10, diam = wind_1min_ms, wind_10min_ms, diameter_km

    # 초기 관성 벡터 (위도별 전형적 이동 방향)
    if lat < 22:
        prev_dlat, prev_dlng = 0.6, -1.0    # 저위도: 북서진
    elif lat < 28:
        prev_dlat, prev_dlng = 0.9, -0.4    # 중위도: 북북서
    else:
        prev_dlat, prev_dlng = 1.3, 0.6     # 고위도: 북동진

    for step in range(max_steps + 1):
        wind = _pressure_to_wind(pres)
        intensity = _classify_intensity(wind)

        track.append(PredictedPoint(
            lat=round(lat, 3),
            lng=round(lng, 3),
            pressure=round(pres, 1),
            wind_ms=round(wind, 1),
            intensity=intensity,
            hour=step * 6,
        ))

        # 소멸 조건
        if pres >= 1008 or lat > 65 or lat < -5 or lng > 210 or lng < 60:
            break

        # ML 이동 예측
        feat = [_make_feature(lat, lng, pres, w1, w10, diam, month, prev_dlat, prev_dlng)]
        try:
            dlat = float(m_lat.predict(feat)[0])
            dlng = float(m_lng.predict(feat)[0])
            dpres = float(m_pres.predict(feat)[0])
        except Exception as e:
            logger.error("ML predict 오류: %s", e)
            break

        # ── 현실적인 기압 변화 제약 ──────────────────────────
        # 1. 초기 24h (4스텝): ML 예측 그대로 사용 (강화 허용)
        # 2. 이후: 위도 기반 약화 강제 적용
        # 3. 고위도(>30N): 더 빠른 약화
        if step < 4:
            # 초기 강화/유지 단계 — ML 결과 신뢰
            dpres_capped = max(-3.0, min(2.0, dpres))
        elif lat > 35:
            # 고위도: 반드시 약화
            lat_decay = (lat - 30) * 0.25
            dpres_capped = max(1.5, dpres, lat_decay)
        elif lat > 25:
            # 중위도: 완만한 약화
            dpres_capped = max(0.5, dpres)
        else:
            # 저위도: SST 기반 보정
            if sst >= 28:
                dpres_capped = min(dpres, 0.5)   # 강화 억제 (ML 예측 유지)
            else:
                dpres_capped = max(0.8, dpres)    # 약화 촉진

        prev_dlat, prev_dlng = dlat, dlng
        lat  = round(lat  + dlat,  3)
        lng  = round(lng  + dlng,  3)
        pres = round(min(1010, pres + dpres_capped), 1)

        w1  = _pressure_to_wind(pres)
        w10 = w1 * 0.88

    return track
