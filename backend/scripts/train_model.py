"""
TyphoonPath ML 훈련 스크립트
================================
IBTrACS 실데이터 기반 태풍 경로/강도 예측 모델 훈련

[예측 방식]
  입력 피처(현재 상태) → 예측(다음 6시간 이동량 dlat, dlng + 기압 변화)
  반복적으로 20스텝(120시간) 예측

[사용 모델]
  GradientBoostingRegressor (scikit-learn)
  - 과거 적용 사례: ECMWF 통계 후처리, SHIPS 강도 예측 등
  - 테이블형 데이터에 강함, 해석 가능, 과적합 억제

[출력]
  backend/data/track_model_lat.pkl  (위도 이동 예측)
  backend/data/track_model_lng.pkl  (경도 이동 예측)
  backend/data/pres_model.pkl       (기압 변화 예측)
  backend/data/model_meta.json      (피처 목록, 성능 지표)

실행:
  pip install scikit-learn joblib numpy
  python scripts/train_model.py

"""

import json
import math
import os
import sys
from pathlib import Path

try:
    import numpy as np
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    import joblib
except ImportError as e:
    print(f"[ERROR] 필요한 패키지 없음: {e}")
    print("설치: pip install scikit-learn joblib numpy")
    sys.exit(1)

BASE = Path(__file__).parent.parent
DATA_DIR = BASE / "data"


def load_typhoons():
    """typhoons_v2.json 우선, 없으면 typhoons.json 사용"""
    v2 = DATA_DIR / "typhoons_v2.json"
    v1 = DATA_DIR / "typhoons.json"
    path = v2 if v2.exists() else v1
    print(f"데이터 로드: {path.name}")
    with open(path) as f:
        return json.load(f)["typhoons"]


def build_features(typhoons):
    """
    피처 엔지니어링:
    각 태풍의 연속 3-포인트(i-1, i, i+1)를 이용해 학습 샘플 생성.

    피처 (X):
      lat, lng,
      pressure (hPa),
      wind_1min_ms (없으면 wind_ms 사용),
      wind_10min_ms (없으면 wind_ms * 0.88),
      diameter_km (없으면 300 기본값),
      month (1~12),
      prev_dlat (이전 스텝 위도 이동량) — 관성(persistence) 가장 중요한 피처
      prev_dlng (이전 스텝 경도 이동량)
      lat_sin_month (위도 × sin(월/12*2π) — 계절 교호작용)
      lat_cos_month (위도 × cos(월/12*2π))

    타겟 (y):
      dlat  (다음 6h 위도 변화)
      dlng  (다음 6h 경도 변화)
      dpres (다음 6h 기압 변화 — 강도 예측용)
    """
    X, y_lat, y_lng, y_pres = [], [], [], []
    skipped = 0

    for t in typhoons:
        track = t["track"]
        if len(track) < 3:
            continue

        try:
            month = int(track[0]["dt"][5:7])
        except Exception:
            continue

        for i in range(1, len(track) - 1):
            prev = track[i - 1]
            cur  = track[i]
            nxt  = track[i + 1]

            # 필수 필드
            try:
                lat  = float(cur["lat"])
                lng  = float(cur["lng"])
                pres = float(cur.get("pressure") or 985)
            except Exception:
                skipped += 1
                continue

            # 풍속 (없으면 기압에서 추정)
            w1 = cur.get("wind_1min_ms") or cur.get("wind_ms")
            w10 = cur.get("wind_10min_ms")
            if w1 is None:
                w1 = max(0.0, max(0.0, 1010 - pres) ** 0.644 * 3.92)
            if w10 is None:
                w10 = w1 * 0.88

            # 직경 (없으면 기본값 300km)
            diam = cur.get("diameter_km") or 300.0

            # 이전 이동 벡터 (persistence)
            try:
                prev_dlat = float(cur["lat"]) - float(prev["lat"])
                prev_dlng = float(cur["lng"]) - float(prev["lng"])
            except Exception:
                skipped += 1
                continue

            # 다음 이동 벡터 (타겟)
            try:
                next_dlat = float(nxt["lat"]) - float(cur["lat"])
                next_dlng = float(nxt["lng"]) - float(cur["lng"])
                next_pres = float(nxt.get("pressure") or pres) - pres
            except Exception:
                skipped += 1
                continue

            # 이상값 필터 (6시간 내 10도 이상 이동은 오류)
            if abs(next_dlat) > 10 or abs(next_dlng) > 10:
                skipped += 1
                continue

            # 계절 교호작용
            rad = 2 * math.pi * month / 12
            lat_sin = lat * math.sin(rad)
            lat_cos = lat * math.cos(rad)

            X.append([lat, lng, pres, w1, w10, diam, month,
                      prev_dlat, prev_dlng, lat_sin, lat_cos])
            y_lat.append(next_dlat)
            y_lng.append(next_dlng)
            y_pres.append(next_pres)

    print(f"학습 샘플: {len(X):,}개 (제외: {skipped:,}개)")
    return (np.array(X, dtype=np.float32),
            np.array(y_lat),
            np.array(y_lng),
            np.array(y_pres))


FEATURE_NAMES = [
    "lat", "lng", "pressure", "wind_1min_ms", "wind_10min_ms",
    "diameter_km", "month", "prev_dlat", "prev_dlng",
    "lat_sin_month", "lat_cos_month"
]


def train_model(X_tr, y_tr, name):
    """GradientBoosting 훈련"""
    print(f"  [{name}] GradientBoosting 훈련 중...")
    model = GradientBoostingRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        min_samples_leaf=10,
        random_state=42,
        verbose=0,
    )
    model.fit(X_tr, y_tr)
    return model


def evaluate(model, X_te, y_te, name, unit="deg"):
    mae = mean_absolute_error(y_te, model.predict(X_te))
    if unit == "km":
        mae_km = mae * 111.0
        print(f"  [{name}] MAE = {mae:.4f}° → {mae_km:.1f} km")
        return mae_km
    else:
        print(f"  [{name}] MAE = {mae:.4f} {unit}")
        return mae


def main():
    print("=" * 50)
    print("TyphoonPath ML 모델 훈련")
    print("=" * 50)

    typhoons = load_typhoons()
    print(f"태풍 수: {len(typhoons):,}")

    print("\n[1] 피처 엔지니어링...")
    X, y_lat, y_lng, y_pres = build_features(typhoons)

    print("\n[2] 훈련/테스트 분리 (80/20)...")
    X_tr, X_te, yl_tr, yl_te, yn_tr, yn_te, yp_tr, yp_te = train_test_split(
        X, y_lat, y_lng, y_pres,
        test_size=0.2, random_state=42
    )
    print(f"  훈련: {len(X_tr):,}개  |  테스트: {len(X_te):,}개")

    print("\n[3] 모델 훈련...")
    m_lat  = train_model(X_tr, yl_tr, "dlat")
    m_lng  = train_model(X_tr, yn_tr, "dlng")
    m_pres = train_model(X_tr, yp_tr, "dpres")

    print("\n[4] 성능 평가...")
    mae_lat  = evaluate(m_lat,  X_te, yl_te, "dlat",  "km")
    mae_lng  = evaluate(m_lng,  X_te, yn_te, "dlng",  "km")
    mae_pres = evaluate(m_pres, X_te, yp_te, "dpres", "hPa")

    # 결합 위치 오차 (sqrt(dlat^2 + dlng^2) in km)
    pred_lat = m_lat.predict(X_te)
    pred_lng = m_lng.predict(X_te)
    pos_errors = np.sqrt(((pred_lat - yl_te) * 111) ** 2 +
                         ((pred_lng - yn_te) * 111 * np.cos(np.radians(X_te[:, 0]))) ** 2)
    print(f"  [위치] 평균 오차: {pos_errors.mean():.1f} km  (중앙값: {np.median(pos_errors):.1f} km)")

    # Persistence 기준 (이전 이동 그대로 가는 경우)
    pers_lat  = X_te[:, 7]   # prev_dlat
    pers_lng  = X_te[:, 8]   # prev_dlng
    pers_err  = np.sqrt(((pers_lat - yl_te) * 111) ** 2 +
                        ((pers_lng - yn_te) * 111 * np.cos(np.radians(X_te[:, 0]))) ** 2)
    print(f"  [Persistence 기준] 평균 오차: {pers_err.mean():.1f} km")
    skill = (1 - pos_errors.mean() / pers_err.mean()) * 100
    print(f"  [스킬 스코어] Persistence 대비 {skill:.1f}% 개선")

    # 피처 중요도 top-5
    print("\n  [피처 중요도 top-5 (dlat 모델)]")
    imp = sorted(zip(FEATURE_NAMES, m_lat.feature_importances_), key=lambda x: -x[1])
    for name, score in imp[:5]:
        print(f"    {name:20s}: {score:.4f}")

    print("\n[5] 모델 저장...")
    DATA_DIR.mkdir(exist_ok=True)
    joblib.dump(m_lat,  DATA_DIR / "track_model_lat.pkl")
    joblib.dump(m_lng,  DATA_DIR / "track_model_lng.pkl")
    joblib.dump(m_pres, DATA_DIR / "pres_model.pkl")

    meta = {
        "features": FEATURE_NAMES,
        "n_train": len(X_tr),
        "n_test": len(X_te),
        "mae_lat_km": round(float(mae_lat), 2),
        "mae_lng_km": round(float(mae_lng), 2),
        "mae_pres_hpa": round(float(mae_pres), 3),
        "pos_error_mean_km": round(float(pos_errors.mean()), 2),
        "pos_error_median_km": round(float(np.median(pos_errors)), 2),
        "persistence_error_km": round(float(pers_err.mean()), 2),
        "skill_score_pct": round(float(skill), 1),
        "model_type": "GradientBoostingRegressor",
        "n_estimators": 300,
    }
    with open(DATA_DIR / "model_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"  저장 완료: {DATA_DIR}")
    print("\n" + "=" * 50)
    print("훈련 완료!")
    print(f"  6시간 위치 예측 오차: {pos_errors.mean():.1f} km")
    print(f"  (120시간 예측 시 누적 오차 약 {pos_errors.mean()*20/1000*0.6:.0f}~{pos_errors.mean()*20/1000:.0f}천 km 범위)")
    print("=" * 50)


if __name__ == "__main__":
    main()
