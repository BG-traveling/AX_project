import logging
from fastapi import APIRouter
from app.models.schemas import PredictRequest, PredictResponse, CompareResponse, ModelTrack
from app.services.blend_service import find_analogs_extended, blend_predict
from app.services.ml_prediction_service import ml_predict, ml_available, get_model_meta
from app.services.lstm_prediction_service import lstm_predict, lstm_available, get_lstm_meta
from app.services import claude_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/predict", tags=["predict"])


def _is_plausible(predicted: list, start_lat: float, start_lng: float,
                  mode: str = "analog") -> bool:
    """
    물리적 타당성 검사.
    서태평양 저위도 태풍(lat<25, lng>125)이 48h 내에 비정상 방향으로
    이동하면 기각합니다.

    mode="lstm"   : LSTM 전용 — 남향 완전 차단 (Δlat ≥ 0.0)
    mode="gbm"    : GBM 전용 — 남향 2.5° 이내 허용 (Δlat ≥ -2.5)
    mode="analog" : Analog Blending — 남향 5° 이내 허용 (Δlat ≥ -5.0)
    """
    if len(predicted) < 8:
        return True   # 포인트 부족 시 기각 없이 통과
    if start_lat >= 25 or start_lng <= 125:
        return True   # 고위도 또는 서쪽 시작은 다양한 방향 허용

    p0 = predicted[0]
    p8 = predicted[min(8, len(predicted) - 1)]
    net_dlng = p8.lng - p0.lng   # 48h 경도 변화 (양수=동진)
    net_dlat = p8.lat - p0.lat   # 48h 위도 변화 (음수=남진)

    if mode == "lstm":
        lng_limit, lat_limit = 3.0, -1.5   # 1.5° 이상 남진 시 기각
    elif mode == "gbm":
        lng_limit, lat_limit = 3.0, -2.5
    else:  # analog
        lng_limit, lat_limit = 5.0, -5.0

    if net_dlng > lng_limit:
        print(f"[plausible] 동진 기각({mode}): Δlng={net_dlng:.1f} > {lng_limit}", flush=True)
        return False
    if net_dlat < lat_limit:
        print(f"[plausible] 남진 기각({mode}): Δlat={net_dlat:.1f} < {lat_limit}", flush=True)
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
    import time
    t0 = time.time()
    print(f"[predict] 요청 수신 lat={req.start_lat} lng={req.start_lng} pres={req.pressure}", flush=True)

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
    print(f"[predict] analogs 탐색 완료 {len(blend_analogs)}개 ({time.time()-t0:.1f}s)", flush=True)

    predicted = []

    # ── 0순위: LSTM (앙상블 3개 모두 로드된 경우만) ─────────
    if lstm_available():
        print(f"[predict] LSTM 추론 시작 ({time.time()-t0:.1f}s)", flush=True)
        try:
            import asyncio
            from concurrent.futures import ThreadPoolExecutor

            def _run_lstm():
                return lstm_predict(
                    start_lat=req.start_lat,
                    start_lng=req.start_lng,
                    pressure=req.pressure,
                    sst=req.sst,
                    month=req.month,
                    max_steps=80,
                )

            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as executor:
                predicted = await asyncio.wait_for(
                    loop.run_in_executor(executor, _run_lstm),
                    timeout=20.0,
                )

            print(f"[predict] LSTM 추론 완료 ({time.time()-t0:.1f}s)", flush=True)
            if len(predicted) >= 5:
                p0, p8 = predicted[0], predicted[min(8, len(predicted)-1)]
                print(f"[predict] LSTM 방향: Δlat={p8.lat-p0.lat:.2f} Δlng={p8.lng-p0.lng:.2f}", flush=True)
            if len(predicted) >= 5 and _is_plausible(predicted, req.start_lat, req.start_lng,
                                                       mode="lstm"):
                method = "lstm"
                meta = get_lstm_meta()
                logger.info(
                    "LSTM 예측 채택 — 6h:%.1fkm 24h:%.1fkm 72h:%.1fkm",
                    meta.get("km_error_6h", 0),
                    meta.get("km_error_24h", 0),
                    meta.get("km_error_72h", 0),
                )
            else:
                print("[predict] LSTM 기각 → Analog Blending", flush=True)
                predicted = []
        except asyncio.TimeoutError:
            print(f"[predict] LSTM 타임아웃(>20s) → Analog Blending", flush=True)
            predicted = []
        except Exception as e:
            print(f"[predict] LSTM 예외 → Analog Blending: {e}", flush=True)
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
        if len(predicted) >= 5 and _is_plausible(predicted, req.start_lat, req.start_lng,
                                                   mode="analog"):
            method = "analog_blending"
            print(f"[predict] Analog Blending 채택 ({len(blend_analogs)}개 유사 태풍)", flush=True)
        else:
            print("[predict] Analog Blending 기각 → GBM", flush=True)
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
            if len(predicted) >= 5 and _is_plausible(predicted, req.start_lat, req.start_lng,
                                                       mode="gbm"):
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
            steps=80,
        )
        method = "physics"
        logger.info("물리 모델 채택 (최후 폴백)")

    # ── Claude AI 설명 ───────────────────────────────────────
    print(f"[predict] 예측 완료 method={method} points={len(predicted)} ({time.time()-t0:.1f}s)", flush=True)
    explanation = ""
    try:
        explanation = await claude_service.generate_prediction_explanation(
            req=req,
            predicted=predicted,
            analogs=display_analogs,
        )
    except Exception as e:
        print(f"[predict] AI 설명 생성 실패: {type(e).__name__}: {e}", flush=True)
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


@router.post("/compare", response_model=CompareResponse)
async def compare_typhoon_predictions(req: PredictRequest):
    """
    모든 가용 예측 모델 결과를 동시에 반환 — 모델 비교용
    폴백 없이 각 모델을 독립 실행합니다.
    """
    import time
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    t0 = time.time()
    print(f"[compare] 비교 요청 lat={req.start_lat} lng={req.start_lng}", flush=True)
    tracks: list[ModelTrack] = []

    # 1. Analog Blending (항상 가용)
    blend_analogs, _ = find_analogs_extended(
        start_lat=req.start_lat, start_lng=req.start_lng,
        pressure=req.pressure, month=req.month, top_n=10, display_n=3,
    )
    analog_track = blend_predict(
        start_lat=req.start_lat, start_lng=req.start_lng,
        pressure=req.pressure, sst=req.sst, analogs=blend_analogs, max_steps=80,
    )
    tracks.append(ModelTrack(
        method="analog_blending", label="📊 유사 태풍 블렌딩", track=analog_track,
    ))
    print(f"[compare] Analog Blending 완료 ({time.time()-t0:.1f}s)", flush=True)

    # 2. GBM ML (가용 시)
    if ml_available():
        try:
            ml_track = ml_predict(
                start_lat=req.start_lat, start_lng=req.start_lng,
                pressure=req.pressure, sst=req.sst,
                wind_1min_ms=req.wind_1min_ms, wind_10min_ms=req.wind_10min_ms,
                diameter_km=req.diameter_km, month=req.month, max_steps=80,
            )
            if len(ml_track) >= 5:
                tracks.append(ModelTrack(method="ml", label="🤖 GBM 머신러닝", track=ml_track))
            print(f"[compare] GBM 완료 ({time.time()-t0:.1f}s)", flush=True)
        except Exception as e:
            print(f"[compare] GBM 실패: {e}", flush=True)

    # 3. LSTM (가용 시, 타임아웃 20s)
    if lstm_available():
        try:
            def _run_lstm():
                return lstm_predict(
                    start_lat=req.start_lat, start_lng=req.start_lng,
                    pressure=req.pressure, sst=req.sst, month=req.month, max_steps=80,
                )
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as executor:
                lstm_track = await asyncio.wait_for(
                    loop.run_in_executor(executor, _run_lstm), timeout=20.0,
                )
            if len(lstm_track) >= 5:
                tracks.append(ModelTrack(method="lstm", label="🧠 LSTM 딥러닝", track=lstm_track))
            print(f"[compare] LSTM 완료 ({time.time()-t0:.1f}s)", flush=True)
        except asyncio.TimeoutError:
            print("[compare] LSTM 타임아웃 — 생략", flush=True)
        except Exception as e:
            print(f"[compare] LSTM 실패: {e}", flush=True)

    # 4. 물리 모델 (항상 가용)
    from app.services.prediction_service import predict_track
    phys_track = predict_track(
        start_lat=req.start_lat, start_lng=req.start_lng,
        pressure=req.pressure, sst=req.sst, steps=80,
    )
    tracks.append(ModelTrack(method="physics", label="⚙️ 물리 모델", track=phys_track))
    print(f"[compare] 물리 모델 완료 ({time.time()-t0:.1f}s)", flush=True)

    return CompareResponse(tracks=tracks)
