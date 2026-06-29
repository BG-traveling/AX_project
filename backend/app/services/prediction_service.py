"""
태풍 경로 물리 모델 예측 서비스

실제 NWP(수치예보)와는 다르지만, 교육용으로 핵심 기상 원리를 반영한 간소화 모델:
  - 베타 드리프트: 지구 자전 효과로 북서 방향 이동
  - 무역풍 조향: 저위도에서 서쪽으로 밀림
  - 전향(Recurvature): 25~30°N 부근에서 북동으로 방향 전환
  - 기압 → 강도 → 이동 속도 영향
  - SST → 열에너지 공급 → 강도 유지/발달 영향
"""

import math
from app.models.schemas import PredictedPoint


def _pressure_to_wind(pressure: float) -> float:
    """중심기압 → 최대풍속(m/s) 변환 (Atkinson-Holliday 근사)"""
    if pressure >= 1010:
        return 0.0
    return min(85.0, (1010 - pressure) ** 0.644 * 3.92)


def _classify_intensity(wind_ms: float) -> str:
    if wind_ms < 17:
        return "TD"
    elif wind_ms < 25:
        return "TS"
    elif wind_ms < 33:
        return "TY"
    return "STY"


def _steering_vector(lat: float, lng: float, pressure: float, sst: float, step: int) -> tuple[float, float]:
    """
    6시간 이동 벡터(dlat, dlng) 계산

    위도 구간별 태풍 행동:
      < 15°N  : 서북서 이동 (무역풍 강, 베타 약)
      15~22°N : 북서 이동 (전형적인 태풍 경로)
      22~28°N : 전향 시작 — 북북동으로 점차 회전
      > 28°N  : 북동~동북동 (편서풍에 편입, 가속)
    """
    intensity = max(0.0, (1010 - pressure) / 160.0)   # 0~1 강도 지수
    sst_boost = max(0.0, (sst - 26) / 9.0)            # SST 26°C 이상에서 부스트

    if lat < 15:
        dlat = 0.5 + intensity * 0.3 + sst_boost * 0.2
        dlng = -1.8 - intensity * 0.3
    elif lat < 22:
        dlat = 0.9 + intensity * 0.4 + sst_boost * 0.2
        dlng = -1.4 - intensity * 0.2
    elif lat < 28:
        t = (lat - 22) / 6.0          # 0→1 전향 진행도
        dlat = 1.3 + t * 1.2 + intensity * 0.3
        dlng = -1.2 + t * 3.0         # 서→동 점진적 전환
    else:
        dlat = 2.0 + intensity * 0.5
        dlng = 1.5 + (lat - 28) * 0.25

    # 기압이 낮을수록 이동 속도 소폭 증가
    speed_mul = 0.85 + intensity * 0.30
    return dlat * speed_mul, dlng * speed_mul


def _decay_pressure(pressure: float, lat: float, sst: float, step: int) -> float:
    """
    단계별 기압 변화:
      - SST ≥ 28°C, 저위도: 발달(기압 하강)
      - SST < 26°C 또는 고위도: 약화(기압 상승)
      - 육지 진입 근사: 경도 100~130°E 내륙 구간에서 급격 약화 (간소화)
    """
    if sst >= 28 and lat < 25:
        delta = -(sst - 26) * 0.8          # 발달
    elif sst < 26 or lat > 35:
        delta = (26 - sst) * 1.2 + max(0, lat - 30) * 0.5  # 약화
    else:
        delta = 0.5                         # 유지

    return min(1010.0, pressure + delta)


def predict_track(
    start_lat: float,
    start_lng: float,
    pressure: float,
    sst: float,
    steps: int = 20,         # 기본 20스텝 = 5일(6h 간격)
) -> list[PredictedPoint]:
    """
    물리 모델 기반 태풍 경로 예측.
    Returns: PredictedPoint 리스트 (6시간 간격)
    """
    track: list[PredictedPoint] = []
    lat, lng, pres = start_lat, start_lng, pressure

    for step in range(steps + 1):
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

        # 태풍이 거의 소멸하거나 지도 밖으로 나가면 종료
        if pres >= 1005 or lat > 55 or lat < 0 or lng > 180 or lng < 80:
            break

        dlat, dlng = _steering_vector(lat, lng, pres, sst, step)
        pres = _decay_pressure(pres, lat, sst, step)
        lat += dlat
        lng += dlng

    return track
