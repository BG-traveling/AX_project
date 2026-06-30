import logging
from fastapi import APIRouter
from app.models.schemas import PredictRequest, PredictResponse
from app.services.blend_service import find_analogs_extended, blend_predict
from app.services.ml_prediction_service import ml_predict, ml_available, get_model_meta
from app.services.lstm_prediction_service import lstm_predict, lstm_available, get_lstm_meta
from app.services import claude_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/predict", tags=["predict"])


def _is_plausible(predicted: list, start_lat: float, start_lng: float) -> bool:
    """
    물리적 타당성 검사.
    서태평양 저위도 태풍(lat<25, lng>125)이 48h 내에 동쪽으로
    크게 이동하거나 남쪽으로 내려가면 비정상으로 판단.
    """
    if len(predicted) < 8:
        return True   # 포인트 부족 시 기각 없이 통과
    if start_lat >= 25 or start_lng <= 125:
        return True   # 고위도 또는 서쪽 시작은 다양한 방향 허용

    p0 = predicted[0]
    p8 = predicted[min(8, len(predicted) - 1)]
    net_dlng = p8.lng - p0.lng   # 48h 경도 변화 (양수=동진)
    net_dlat = p8.lat - p0.lat   # 48h 위도 변화 (음수=남진)

    if net_dlng > 3.0:   # 48h 내 3도 이상 동진 → 비정상
        logger.warning("타당성 검사 실패: 저위도 태풍이 동쪽으로 이동 (Δlng=%.1f) → 폴백", net_dlng)
        return False
    if net_dlat < -2.5:  # 48h 내 2.5도 이상 남진 → 비정상
        logger.warning("타당성 검사 실패: 저위도 태풍이 남쪽으로 이동 (Δlat=%.1f) → 폴백", net_dlat)
        return False

    return True


@router.post("", response_model=PredictResponse)
async def predict_typhoon(req: PredictRequest):
    """
    태풍 경로 예측 — 4단계 폴백 체인

    0순위: LSTM Seq2Seq + Attention (딥러닝, 앙상블 3개 완성 시)
    1순위: Analog Blending (유사 태풍 실데이터 가중평균) ← 검증 결과 가장 정확
    2순위: GBM ML 모델 (타당성 검사 통과 시)
    3순위: 물리 모델 (최후 폴백)
    """
    method = "analog_blending"

    # 유사 태풍 탐색 (항상 실행 — 표시용 + Blending)
    blend_analogs, display_analogs = find_analogs_extended(
        start_lat=req.start_lat,
        start_lng=req.start_lng,
        pressure=req.pressure,
        month=req.month,
        top_n=10,
        display_n=3,
    )

    predicted = []

    # ── 0순위: LSTM (앙상블 3개 모두 로드된 경우만) ─────────
    if lstm_available():
        try:
            predicted = lstm_predict(
                start_lat=req.start_lat,
                start_lng=req.start_lng,
                pressure=req.pressure,
                sst=req.sst,
                month=req.month,
                max_steps=80,
            )
            if len(predicted) >= 5 and _is_plausible(predicted, req.start_lat, req.start_lng):
                method = "lstm"
                meta = get_lstm_meta()
                logger.info("LSTM 예측 채택 (6h오차 %.1f km)", meta.get("km_error_6h", 0))
            else:
                logger.warning("LSTM 예측 기각 → Analog Blending")
                predicted = []
        except Exception as e:
            logger.warning("LSTM 예측 실패 → Analog Blending: %s", e)
            predicted = []

    # ── 1순위: Analog Blending (검증 결과 가장 신뢰도 높음) ──
    if not predicted:
        predicted = blend_predict(
            start_lat=req.start_lat,
            start_lng=req.start_lng,
            pressure=req.pressure,
            sst=req.sst,
            analogs=blend_analogs,
            max_steps=80,
        )
        if len(predicted) >= 5 and _is_plausible(predicted, req.start_lat, req.start_lng):
            method = "analog_blending"
            logger.info("Analog Blending 채택 (%d개 유사 태풍)", len(blend_analogs))
        else:
            logger.warning("Analog Blending 기각 → GBM")
            predicted = []

    # ── 2순위: GBM ML (타당성 검사 통과 시) ─────────────────
    if not predicted and ml_available():
        try:
            predicted = ml_predict(
                start_lat=req.start_lat,
                start_lng=req.start_lng,
                pressure=req.pressure,
                sst=req.sst,
                wind_1min_ms=req.wind_1min_ms,
                wind_10min_ms=req.wind_10min_ms,
                diameter_km=req.diameter_km,
                month=req.month,
                max_steps=80,
            )
            if len(predicted) >= 5 and _is_plausible(predicted, req.start_lat, req.start_lng):
                method = "ml"
                meta = get_model_meta()
                logger.info("GBM 예측 채택 (오차 %.1f km)", meta.get("pos_error_mean_km", 0))
            else:
                logger.warning("GBM 예측 기각 → 물리 모델")
                predicted = []
        except Exception as e:
            logger.warning("GBM 예측 실패 → 물리 모델: %s", e)
            predicted = []

    # ── 3순위: 물리 모델 (최후 폴백) ────────────────────────
    if not predicted:
        from app.services.prediction_service import predict_track
        predicted = predict_track(
            start_lat=req.start_lat,
            start_lng=req.start_lng,
            pressure=req.pressure,
            sst=req.sst,
            max_steps=80,
        )
        method = "physics"
        logger.info("물리 모델 채택 (최후 폴백)")

    # ── Claude AI 설명 ───────────────────────────────────────
    explanation = ""
    try:
        explanation = await claude_service.generate_prediction_explanation(
            req=req,
            predicted=predicted,
            analogs=display_analogs,
        )
    except Exception as e:
        logger.warning("AI 설명 생성 실패 (경로 정상 반환): %s", e)
        method_label = {
            "lstm":            "LSTM 딥러닝",
            "ml":              "GBM 머신러닝",
            "analog_blending": "유사 태풍 블렌딩",
            "physics":         "물리 모델",
        }.get(method, "예측 모델")
        explanation = (
            f"AI 설명을 일시적으로 생성할 수 없습니다. "
            f"예측 경로는 {method_label} 방식으로 "
            f"{len(blend_analogs)}개 과거 태풍 데이터를 참조하여 산출되었습니다."
        )

    return PredictResponse(
        predicted_track=predicted,
        analogs=display_analogs,
        ai_explanation=explanation,
        prediction_method=method,
    )
