"""
유사 태풍 탐색 서비스 (Analog Method)

사용자가 설정한 시작 위치·기압·월과 유사한 과거 태풍을 검색한다.
유사도 점수는 위치 거리, 기압 차이, 계절 유사도 세 가지로 구성.
"""

import math
from app.models.schemas import AnalogTyphoon, UserTrackPoint
from app.services.typhoon_service import _load_data


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 \
        + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _month_diff(m1: int, m2: int) -> int:
    """두 월 간 최소 거리 (원형 거리, 최대 6)"""
    diff = abs(m1 - m2)
    return min(diff, 12 - diff)


def find_analogs(
    start_lat: float,
    start_lng: float,
    pressure: float,
    month: int,
    top_n: int = 3,
) -> list[AnalogTyphoon]:
    """
    유사 태풍 top_n개 반환.
    유사도 기준:
      - 시작 위치 거리 (km): 가까울수록 높음, 500km 이내 최고점
      - 기압 차이 (hPa): 작을수록 높음, 30hPa 이내 최고점
      - 계절 유사도: 같은 달 최고, 3달 이상 차이 시 제외
    """
    data = _load_data()
    scored: list[tuple[float, dict]] = []

    for typhoon in data["typhoons"]:
        if not typhoon["track"]:
            continue

        first = typhoon["track"][0]
        t_lat = first["lat"]
        t_lng = first["lng"]
        t_pres = first.get("pressure") or 985

        # 계절 필터: 3달 이상 차이 제외
        try:
            t_month = int(first["dt"][5:7])
        except Exception:
            continue
        if _month_diff(month, t_month) > 3:
            continue

        # 위치 거리 점수 (0~1)
        dist_km = _haversine(start_lat, start_lng, t_lat, t_lng)
        if dist_km > 1500:
            continue
        pos_score = max(0.0, 1.0 - dist_km / 1500)

        # 기압 차이 점수 (0~1)
        pres_diff = abs(pressure - t_pres)
        if pres_diff > 80:
            continue
        pres_score = max(0.0, 1.0 - pres_diff / 80)

        # 계절 유사도 점수 (0~1)
        season_score = max(0.0, 1.0 - _month_diff(month, t_month) / 3)

        # 종합 점수 (위치 50%, 기압 30%, 계절 20%)
        score = pos_score * 0.5 + pres_score * 0.3 + season_score * 0.2
        scored.append((score, typhoon))

    # 점수 내림차순 정렬, top_n 추출
    scored.sort(key=lambda x: x[0], reverse=True)
    results: list[AnalogTyphoon] = []

    for score, t in scored[:top_n]:
        track_points = [
            UserTrackPoint(lat=p["lat"], lng=p["lng"])
            for p in t["track"]
        ]
        results.append(AnalogTyphoon(
            id=t["id"],
            name_en=t["name_en"],
            year=t["year"],
            similarity=round(score, 3),
            track=track_points,
        ))

    return results
