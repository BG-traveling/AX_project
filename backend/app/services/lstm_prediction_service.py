"""
LSTM Seq2Seq + Attention 추론 서비스
====================================
train_lstm.py로 훈련된 앙상블 모델 3개를 평균하여 태풍 경로를 예측합니다.

시작점 1개만 있는 경우:
  과거 4스텝 warm-up을 물리 모델 기반으로 합성 → LSTM 입력 생성
  → auto-regressive 40스텝 예측

3단계 폴백 체인에서 최우선(0순위)으로 사용됩니다.
"""

import math
import json
import logging
from pathlib import Path
from typing import Optional

from app.models.schemas import PredictedPoint

logger = logging.getLogger(__name__)

DATA_DIR   = Path(__file__).parent.parent.parent / "data"
PAST_STEPS = 4
HIDDEN_SIZES = [48, 64, 96]

# 정규화 범위 (train_lstm.py와 동일)
LAT_MIN, LAT_MAX   =  0.0,  60.0
LNG_MIN, LNG_MAX   = 70.0, 210.0
PRES_MIN, PRES_MAX = 850.0, 1010.0

# 모델 캐시 (성공 로드 시에만 저장)
_models_cache: list | None = None
_meta_cache: dict = {}


def _pressure_to_wind(pres: float) -> float:
    delta = max(0.0, 1010 - pres)
    return min(85.0, delta ** 0.644 * 3.92)


def _classify(wind: float) -> str:
    if wind < 17: return "TD"
    if wind < 25: return "TS"
    if wind < 33: return "TY"
    return "STY"


def _norm(v, lo, hi): return (v - lo) / (hi - lo)


def _make_feat(lat, lng, pres, dlat, dlng, dpres, month):
    sin_m = math.sin(2 * math.pi * month / 12)
    cos_m = math.cos(2 * math.pi * month / 12)
    return [
        dlat, dlng, dpres,
        _norm(lat,  LAT_MIN,  LAT_MAX),
        _norm(lng,  LNG_MIN,  LNG_MAX),
        _norm(pres, PRES_MIN, PRES_MAX),
        sin_m, cos_m,
    ]


# ── 모델 정의 (train_lstm.py와 동일 구조) ───────────────────
def _build_model(hidden_size: int):
    import torch.nn as nn

    class BahdanauAttention(nn.Module):
        def __init__(self, h):
            super().__init__()
            self.W1 = nn.Linear(h, h)
            self.W2 = nn.Linear(h, h)
            self.v  = nn.Linear(h, 1, bias=False)
        def forward(self, dec_h, enc_out):
            dec_e = dec_h.unsqueeze(1).expand_as(enc_out)
            scores = self.v(torch.tanh(self.W1(enc_out) + self.W2(dec_e))).squeeze(-1)
            w = torch.softmax(scores, dim=1)
            return (w.unsqueeze(-1) * enc_out).sum(1), w

    class Seq2Seq(nn.Module):
        def __init__(self, h):
            super().__init__()
            self.encoder   = nn.LSTM(8, h, 2, batch_first=True, dropout=0.2)
            self.decoder   = nn.LSTM(3 + h, h, 2, batch_first=True, dropout=0.2)
            self.attention = BahdanauAttention(h)           # train_lstm.py와 동일
            self.out_track = nn.Sequential(nn.Linear(h*2, h), nn.ReLU(), nn.Linear(h, 3))  # train_lstm.py와 동일
        def encode(self, src):
            return self.encoder(src)
        def decode_step(self, dec_inp, hc, enc_out):
            h, c = hc
            ctx, _ = self.attention(h[-1], enc_out)
            dec_in = torch.cat([dec_inp, ctx], dim=1).unsqueeze(1)
            out, (h, c) = self.decoder(dec_in, (h, c))
            pred = self.out_track(torch.cat([out.squeeze(1), ctx], dim=1))
            return pred, (h, c)

    return Seq2Seq(hidden_size)


def _load_models():
    global _models_cache, _meta_cache
    if _models_cache is not None:
        return _models_cache

    try:
        import torch
    except ImportError:
        logger.warning("PyTorch 미설치 — LSTM 사용 불가")
        return None

    # 전역 torch 참조 저장
    global torch
    import torch as _torch
    torch = _torch

    paths = [DATA_DIR / f"lstm_model_h{h}.pt" for h in HIDDEN_SIZES]
    if not all(p.exists() for p in paths):
        logger.info("LSTM 모델 파일 없음 → scripts/train_lstm.py 실행 필요")
        return None

    try:
        device = torch.device("cpu")
        loaded = []
        for h, p in zip(HIDDEN_SIZES, paths):
            m = _build_model(h)
            m.load_state_dict(torch.load(p, map_location=device, weights_only=True))
            m.eval()
            loaded.append(m)

        meta_path = DATA_DIR / "lstm_meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                _meta_cache = json.load(f)
            logger.info(
                "LSTM 앙상블 로드 완료 — 6h:%.1fkm 24h:%.1fkm 72h:%.1fkm",
                _meta_cache.get("km_error_6h", 0),
                _meta_cache.get("km_error_24h", 0),
                _meta_cache.get("km_error_72h", 0),
            )

        _models_cache = loaded
        return _models_cache
    except Exception as e:
        logger.error("LSTM 모델 로드 실패: %s", e)
        return None


def lstm_available() -> bool:
    import os
    if os.getenv("DISABLE_LSTM", "").lower() in ("1", "true", "yes"):
        return False
    return _load_models() is not None


def get_lstm_meta() -> dict:
    _load_models()
    return _meta_cache


# ── warm-up: 물리 기반 과거 4스텝 합성 ─────────────────────
def _synthetic_warmup(start_lat, start_lng, pressure, month) -> list[list[float]]:
    """
    시작점 1개에서 PAST_STEPS개 합성 이력을 생성.
    위도별 전형적인 이동 방향을 역산해 '과거 위치'를 추정.
    """
    if start_lat < 22:
        step_dlat, step_dlng = -0.6,  1.0   # 남서 방향에서 왔다고 가정
    elif start_lat < 28:
        step_dlat, step_dlng = -0.8,  0.4
    else:
        step_dlat, step_dlng = -1.2, -0.5

    # 과거 위치 추산 (역방향)
    track_lat  = [start_lat  + step_dlat * (PAST_STEPS - i) for i in range(PAST_STEPS)]
    track_lng  = [start_lng  + step_dlng * (PAST_STEPS - i) for i in range(PAST_STEPS)]
    track_pres = [min(1010, pressure + 1.5 * (PAST_STEPS - i)) for i in range(PAST_STEPS)]

    feats = []
    for i in range(PAST_STEPS):
        dlat  = step_dlat if i > 0 else 0.0
        dlng  = step_dlng if i > 0 else 0.0
        dpres = -1.5 if i > 0 else 0.0
        feats.append(_make_feat(
            track_lat[i], track_lng[i], track_pres[i],
            dlat, dlng, dpres, month,
        ))
    return feats


# ── 메인 예측 ────────────────────────────────────────────────
def lstm_predict(
    start_lat: float,
    start_lng: float,
    pressure: float,
    sst: float,
    month: int,
    max_steps: int = 80,   # 훈련 40스텝 초과분은 자동회귀로 연장 (정확도 다소 감소)
) -> list[PredictedPoint]:
    models = _load_models()
    if models is None:
        return []

    # warm-up 시퀀스 생성
    src_feats = _synthetic_warmup(start_lat, start_lng, pressure, month)
    src_tensor = torch.tensor([src_feats], dtype=torch.float32)  # [1, 4, 8]

    # 앙상블 예측
    all_preds = []
    for model in models:
        with torch.no_grad():
            enc_out, (h, c) = model.encode(src_tensor)
            dec_inp = src_tensor[:, -1, :3]   # 마지막 스텝 dlat,dlng,dpres
            step_preds = []
            for _ in range(max_steps):
                pred, (h, c) = model.decode_step(dec_inp, (h, c), enc_out)
                step_preds.append(pred)
                dec_inp = pred.detach()
            all_preds.append(torch.stack(step_preds, dim=1))  # [1, steps, 3]

    # 앙상블 평균
    ensemble = torch.stack(all_preds).mean(0).squeeze(0)  # [steps, 3]

    # 누적 위치 복원
    track: list[PredictedPoint] = []
    lat, lng, pres = start_lat, start_lng, pressure

    for step in range(max_steps):
        wind      = _pressure_to_wind(pres)
        intensity = _classify(wind)

        track.append(PredictedPoint(
            lat=round(lat, 3), lng=round(lng, 3),
            pressure=round(pres, 1), wind_ms=round(wind, 1),
            intensity=intensity, hour=step * 6,
        ))

        # 소멸/범위 이탈
        if pres >= 1008 or lat > 65 or lat < -5 or lng > 215 or lng < 55:
            break

        dlat  = float(ensemble[step, 0])
        dlng  = float(ensemble[step, 1])
        dpres_raw = float(ensemble[step, 2])

        # 현실적 기압 변화 제약 (blend_service와 동일 로직)
        if step < 4:
            dpres = max(-2.0, min(1.5, dpres_raw))
        elif lat > 35:
            dpres = max(1.5, dpres_raw, (lat - 30) * 0.2)
        elif lat > 25:
            dpres = max(0.5, dpres_raw)
        else:
            dpres = min(0.8, dpres_raw) if sst >= 28 else max(0.8, dpres_raw)

        lat  = round(lat  + dlat,  3)
        lng  = round(lng  + dlng,  3)
        pres = round(min(1010, pres + dpres), 1)

    return track
