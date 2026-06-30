"""
Analog Blending 예측 서비스

IBTrACS 유사 태풍의 실제 이동 벡터를 가중 평균해 경로를 생성합니다.
기압/강도 모델은 실제 태풍 생애주기(강화→절정→약화→소멸)를 반영합니다.
"""

import math
from app.models.schemas import PredictedPoint, AnalogTyphoon, UserTrackPoint
from app.services.typhoon_service import _load_data


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _month_diff(m1: int, m2: int) -> int:
    d = abs(m1 - m2)
    return min(d, 12 - d)


def _pressure_to_wind(pres: float) -> float:
    delta = max(0.0, 1010 - pres)
    return min(85.0, delta ** 0.644 * 3.92)


def _classify(wind: float) -> str:
    if wind < 17: return "TD"
    if wind < 25: return "TS"
    if wind < 33: return "TY"
    return "STY"


# ── 현실적인 태풍 기압 변화 모델 ─────────────────────────
def _lifecycle_dpres(step: int, pres: float, lat: float, sst: float,
                     start_pres: float) -> float:
    """
    태풍 생애주기에 따른 6시간 기압 변화(hPa).
    양수 = 약화(기압 상승), 음수 = 강화(기압 하강).

    단계:
      0~ 4 스텝 (0~24h):  초기. 조건에 따라 소폭 강화 또는 유지
      4~12 스텝 (24~72h): 성숙기. 유지 또는 완만한 약화
     12~   스텝 (72h~):   약화기. 위도·SST·강도에 따라 가속
    """
    # 기본 약화율 (약한 양수)
    base = 0.8

    # ① 초기 강화 단계 (0~24h)
    if step < 4:
        if sst >= 29 and lat < 22 and pres > 940:
            return -1.0   # 강한 강화 조건: 소폭 강화 허용
        return 0.3        # 그 외: 유지에 가깝게

    # ② 성숙기 (24~72h)
    if step < 12:
        if lat > 28:
            base = 1.5    # 중위도 진입 시 약화 시작
        elif sst >= 28:
            base = 0.5    # 고온 해역: 유지
        else:
            base = 1.2    # 저온 해역: 약화

    # ③ 약화기 (72h~)
    else:
        # 위도별 약화 가속
        if lat > 40:
            base = 4.0
        elif lat > 35:
            base = 2.5
        elif lat > 28:
            base = 1.8
        else:
            base = 1.0

        # SST에 따른 약화 조정
        if sst < 25:
            base *= 1.5
        elif sst >= 28 and lat < 25:
            base *= 0.5   # 고온 저위도: 약화 둔화

    # 이미 약한 태풍은 빠르게 소멸
    if pres > 990:
        base *= 1.5

    return round(base, 2)


def find_analogs_extended(
    start_lat: float,
    start_lng: float,
    pressure: float,
    month: int,
    top_n: int = 10,
    display_n: int = 3,
) -> tuple[list[AnalogTyphoon], list[AnalogTyphoon]]:
    data = _load_data()
    scored: list[tuple[float, dict]] = []

    for typhoon in data["typhoons"]:
        track = typhoon.get("track", [])
        if len(track) < 8:
            continue

        first = track[0]
        t_lat, t_lng = first["lat"], first["lng"]
        t_pres = first.get("pressure") or 985

        try:
            t_month = int(first["dt"][5:7])
        except Exception:
            continue
        if _month_diff(month, t_month) > 3:
            continue

        dist_km = _haversine(start_lat, start_lng, t_lat, t_lng)
        if dist_km > 1500:
            continue

        pres_diff = abs(pressure - t_pres)
        if pres_diff > 80:
            continue

        pos_score    = max(0.0, 1.0 - dist_km / 1500)
        pres_score   = max(0.0, 1.0 - pres_diff / 80)
        season_score = max(0.0, 1.0 - _month_diff(month, t_month) / 3)
        len_bonus    = min(0.1, len(track) / 400)

        score = pos_score * 0.45 + pres_score * 0.3 + season_score * 0.2 + len_bonus
        scored.append((score, typhoon))

    scored.sort(key=lambda x: x[0], reverse=True)

    def to_analog(score: float, t: dict) -> AnalogTyphoon:
        return AnalogTyphoon(
            id=t["id"], name_en=t["name_en"], year=t["year"],
            similarity=round(score, 3),
            track=[UserTrackPoint(lat=p["lat"], lng=p["lng"]) for p in t["track"]],
        )

    return (
        [to_analog(s, t) for s, t in scored[:top_n]],
        [to_analog(s, t) for s, t in scored[:display_n]],
    )


def blend_predict(
    start_lat: float,
    start_lng: float,
    pressure: float,
    sst: float,
    analogs: list[AnalogTyphoon],
    max_steps: int = 80,   # 소멸 조건(pres≥1008) 도달까지 최대 480h
) -> list[PredictedPoint]:
    """유사 태풍 상대 이동 벡터 가중 평균 + 현실적 생애주기 기압 모델."""
    if not analogs:
        from app.services.prediction_service import predict_track
        return predict_track(start_lat, start_lng, pressure, sst, max_steps)

    weights = [a.similarity for a in analogs]
    total_w = sum(weights) or 1.0
    norm_w  = [w / total_w for w in weights]

    track: list[PredictedPoint] = []
    pres = pressure

    for step in range(max_steps + 1):
        # ── 위치: 유사 태풍 가중 평균 블렌딩 ──
        b_lat = b_lng = used_w = 0.0

        for analog, w in zip(analogs, norm_w):
            atr = analog.track
            n   = len(atr)
            if step < n:
                b_lat += (atr[step].lat - atr[0].lat) * w
                b_lng += (atr[step].lng - atr[0].lng) * w
                used_w += w
            elif step < n + 12:          # 최대 12스텝(72h) 외삽
                extra = step - n + 1
                decay = 0.8 ** extra     # 완만한 감쇠
                if n >= 2:
                    dl = atr[-1].lat - atr[-2].lat
                    dn = atr[-1].lng - atr[-2].lng
                    cumul_lat = (atr[-1].lat - atr[0].lat) + dl * extra
                    cumul_lng = (atr[-1].lng - atr[0].lng) + dn * extra
                    b_lat += cumul_lat * w * decay
                    b_lng += cumul_lng * w * decay
                    used_w += w * decay

        if used_w < 0.02:
            break

        pred_lat = start_lat + b_lat / used_w
        pred_lng = start_lng + b_lng / used_w

        if pred_lat > 65 or pred_lat < -5 or pred_lng > 215 or pred_lng < 55:
            break

        # ── 기압: 현실적 생애주기 모델 ──
        dpres = _lifecycle_dpres(step, pres, pred_lat, sst, pressure)
        pres  = round(min(1010, pres + dpres), 1)
        wind  = _pressure_to_wind(pres)

        track.append(PredictedPoint(
            lat=round(pred_lat, 3),
            lng=round(pred_lng, 3),
            pressure=pres,
            wind_ms=round(wind, 1),
            intensity=_classify(wind),
            hour=step * 6,
        ))

        if pres >= 1008:
            break

    if len(track) < 5:
        from app.services.prediction_service import predict_track
        return predict_track(start_lat, start_lng, pressure, sst, max_steps)

    return track
