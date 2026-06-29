import anthropic
from app.core.config import settings
from app.models.schemas import (
    FeedbackRequest, FeedbackResponse, ErrorSummary, UserTrackPoint,
    PredictRequest, PredictedPoint, AnalogTyphoon,
)
import math


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _calc_error(user_track: list, actual_track: list) -> tuple[float, str]:
    n = min(len(user_track), len(actual_track))
    if n == 0:
        return 0.0, "알 수 없음"
    user_sample = [user_track[int(i * len(user_track) / n)] for i in range(n)]
    actual_sample = [actual_track[int(i * len(actual_track) / n)] for i in range(n)]
    dists = [_haversine_km(u.lat, u.lng, a["lat"], a["lng"])
             for u, a in zip(user_sample, actual_sample)]
    avg_dist = sum(dists) / len(dists)
    u_last, a_last = user_sample[-1], actual_sample[-1]
    dlat = u_last.lat - a_last["lat"]
    dlon = u_last.lng - a_last["lng"]
    bias = ("북쪽" if dlat > 1 else "남쪽" if dlat < -1 else "") + \
           ("동쪽" if dlon > 1 else "서쪽" if dlon < -1 else "")
    return round(avg_dist, 1), bias or "거의 정확"


async def generate_feedback(req: FeedbackRequest, actual_track_points: list) -> FeedbackResponse:
    avg_dist, direction_bias = _calc_error(req.user_track, actual_track_points)

    prompt = (
        "당신은 기상 교육 전문가입니다. 사용자가 태풍 경로를 예측했으며, 실제 경로와 비교 분석이 필요합니다.\n\n"
        f"[태풍 정보]\n- 태풍 ID: {req.typhoon_id}\n\n"
        f"[사용자 조작 변수]\n- 기압: {req.user_variables.pressure} hPa\n- 온도: {req.user_variables.temperature} C\n\n"
        f"[오차 분석]\n- 평균 거리 오차: {avg_dist} km\n- 경로 편향: {direction_bias}\n\n"
        "다음을 포함하여 한국어로 교육적 피드백을 작성해주세요:\n"
        "1. 예측의 주요 차이점\n"
        "2. 오차가 발생한 기상학적 원인\n"
        "3. 핵심 학습 포인트 1~2가지\n\n"
        "피드백은 200자 이내로 친절하고 쉽게 작성해주세요."
    )

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    feedback_text = message.content[0].text
    actual_simplified = [UserTrackPoint(lat=p["lat"], lng=p["lng"]) for p in actual_track_points]

    return FeedbackResponse(
        actual_track=actual_simplified,
        feedback=feedback_text,
        error_summary=ErrorSummary(
            avg_distance_km=avg_dist,
            direction_bias=direction_bias,
        ),
    )


async def generate_prediction_explanation(
    req: PredictRequest,
    predicted: list[PredictedPoint],
    analogs: list[AnalogTyphoon],
) -> str:
    end = predicted[-1] if predicted else None
    analog_names = ", ".join(f"{a.name_en}({a.year})" for a in analogs) if analogs else "없음"

    prompt = (
        "당신은 기상 교육 전문가입니다. 아래 조건으로 예측된 태풍 경로를 쉽고 교육적으로 설명해주세요.\n\n"
        f"[초기 조건]\n"
        f"- 시작 위치: 위도 {req.start_lat:.1f}N, 경도 {req.start_lng:.1f}E\n"
        f"- 중심기압: {req.pressure} hPa\n"
        f"- 해수면 온도(SST): {req.sst}C\n"
        f"- 예측 월: {req.month}월\n\n"
        f"[예측 결과]\n"
        f"- 예측 경로: {len(predicted)}개 관측점 ({len(predicted) * 6}시간)\n"
    )
    if end:
        prompt += (
            f"- 최종 위치: 위도 {end.lat:.1f}N, 경도 {end.lng:.1f}E\n"
            f"- 최종 강도: {end.intensity} (기압 {end.pressure:.0f} hPa, 풍속 {end.wind_ms:.1f} m/s)\n\n"
        )
    prompt += (
        f"[유사 과거 태풍]\n{analog_names}\n\n"
        "다음 내용을 포함해 한국어 200자 이내로 설명해주세요:\n"
        "1. 이 경로가 예측된 주요 기상 원인 (기압, SST, 위도 조향력)\n"
        "2. 유사 과거 태풍과의 공통점 한 가지\n"
        "3. 변수를 바꾸면 경로가 어떻게 달라질지 힌트 한 가지"
    )

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
