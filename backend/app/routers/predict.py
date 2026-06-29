import logging
from fastapi import APIRouter
from app.models.schemas import PredictRequest, PredictResponse
from app.services.blend_service import find_analogs_extended, blend_predict
from app.services.ml_prediction_service import ml_predict, ml_available, get_model_meta
from app.services.lstm_prediction_service import lstm_predict, lstm_available, get_lstm_meta
from app.services import claude_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/predict", tags=["predict"])


@router.post("", response_model=PredictResponse)
async def predict_typhoon(req: PredictRequest):
    """
    태풍 경로 예측 — 4단계 폴백 체인

    0순위: LSTM Seq2Seq + Attention (딥러닝, train_lstm.py 실행 시)
           과거 시계열 패턴 학습, 재귀곡 포착에 가장 뛰어남
    1순위: GBM ML 모델 (GradientBoosting, train_model.py 실행 시)
           단일 스텝 예측, 빠름
    2순위: Analog Blending (유사 태풍 실데이터 가중 평균)
    3순위: 물리 모델 (최후 폴백)
    """
    method = "analog_blending"

    # 유사 태풍 탐색 (항상 실행 — 표시용 + Blending 폴백)
    blend_analogs, display_analogs = find_analogs_extended(
        start_lat=req.start_lat,
        start_lng=req.start_lng,
        pressure=req.pressure,
        month=req.month,
        top_n=10,
        display_n=3,
    )

    predicted = []

    # ── 0순위: LSTM ──────────────────────────────────────
    if lstm_available():
        try:
            predicted = lstm_predict(
                start_lat=req.start_lat,
                start_lng=req.start_lng,
                pressure=req.pressure,
                sst=req.sst,
                month=req.month,
                max_steps=40,
            )
            if len(predicted) >= 5:
                method = "lstm"
                meta = get_lstm_meta()
                logger.info(
                    "LSTM 예측 사용 (6h오차 %.1f km)",
                    meta.get("km_error_6h", 0),
                )
            else:
                logger.warning("LSTM 예측 경로 짧음(%d) → 다음 폴백", len(predicted))
                predicted = []
        except Exception as e:
            logger.warning("LSTM 예측 실패 → 다음 폴백: %s", e)
            predicted = []

    # ── 1순위: GBM ML ───────────────────────────────────
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
                max_steps=40,
            )
            if len(predicted) >= 5:
                method = "ml"
                meta = get_model_meta()
                logger.info(
                    "GBM 예측 사용 (오차 %.1f km, 스킬 +%.1f%%)",
                    meta.get("pos_error_mean_km", 0),
                    meta.get("skill_score_pct", 0),
                )
            else:
                logger.warning("GBM 예측 경로 짧음(%d) → Analog Blending", len(predicted))
                predicted = []
        except Exception as e:
            logger.warning("GBM 예측 실패 → Analog Blending: %s", e)
            predicted = []

    # ── 2순위: Analog Blending ───────────────────────────
    if not predicted:
        predicted = blend_predict(
            start_lat=req.start_lat,
            start_lng=req.start_lng,
            pressure=req.pressure,
            sst=req.sst,
            analogs=blend_analogs,
            max_steps=40,
        )
        method = "analog_blending"
        # 물리 모델 폴백은 blend_predict 내부에서 자동 처리

    # ── Claude AI 설명 ───────────────────────────────────
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
            "ml":              "ML 머신러닝",
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
