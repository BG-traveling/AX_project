"""
IBTrACS WP CSV → typhoons_v2.json (강화 버전)

기존 필드 유지 + 3개 추가:
  - wind_1min_ms  : USA_WIND (1분 지속풍속, kt→m/s)
  - wind_10min_ms : WMO_WIND (10분 지속풍속, kt→m/s)
  - r34_km        : 34kt 반경 최대값 (태풍 최대직경 근사, nmi→km) / 2 = 최대반경

직경(diameter) = max(R34_NE, R34_SE, R34_SW, R34_NW) * 1.852 * 2
  → 없을 경우 RMW 기반 추정치 사용

실행: python scripts/enhance_data.py
출력: backend/data/typhoons_v2.json
"""

import csv
import json
import math
import os
import sys
from pathlib import Path

KT_TO_MS = 0.5144
NMI_TO_KM = 1.852

CSV_PATH = Path(__file__).parent.parent / "data" / "ibtracs.WP.list.v04r01.csv"
OUT_PATH = Path(__file__).parent.parent / "data" / "typhoons_v2.json"


def safe_float(val, factor=1.0):
    """숫자 변환, 실패 시 None"""
    try:
        v = float(val)
        if v <= -99 or v == 0:
            return None
        return round(v * factor, 2)
    except (ValueError, TypeError):
        return None


def best_val(*vals):
    """여러 후보 중 첫 번째 유효한 값 반환"""
    for v in vals:
        if v is not None:
            return v
    return None


def classify_intensity(wind_ms):
    if wind_ms is None:
        return "TD"
    if wind_ms < 17:
        return "TD"
    if wind_ms < 25:
        return "TS"
    if wind_ms < 33:
        return "TY"
    return "STY"


def parse_csv():
    typhoons = {}
    order = []

    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        headers = next(reader)   # row 1: column names
        next(reader)             # row 2: units (skip)

        col = {h.strip(): i for i, h in enumerate(headers)}

        for row in reader:
            sid = row[col["SID"]].strip()
            if not sid:
                continue

            # ── 태풍 기본 정보 ──
            if sid not in typhoons:
                name = row[col["NAME"]].strip() or "UNNAMED"
                try:
                    year = int(row[col["SEASON"]].strip())
                    season_no = int(row[col["NUMBER"]].strip())
                except ValueError:
                    continue
                typhoons[sid] = {
                    "id": sid,
                    "name_en": name,
                    "year": year,
                    "season_no": season_no,
                    "track": [],
                }
                order.append(sid)

            # ── 트랙 포인트 ──
            try:
                lat = float(row[col["LAT"]].strip())
                lng = float(row[col["LON"]].strip())
            except ValueError:
                continue

            dt = row[col["ISO_TIME"]].strip()

            # 풍속 (m/s)
            wind_1min = best_val(
                safe_float(row[col["USA_WIND"]], KT_TO_MS),
                safe_float(row[col["CMA_WIND"]] if "CMA_WIND" in col else None, KT_TO_MS),
                safe_float(row[col["HKO_WIND"]] if "HKO_WIND" in col else None, KT_TO_MS),
            )
            wind_10min = best_val(
                safe_float(row[col["WMO_WIND"]], KT_TO_MS),
                safe_float(row[col["TOKYO_WIND"]] if "TOKYO_WIND" in col else None, KT_TO_MS),
                safe_float(row[col["KMA_WIND"]] if "KMA_WIND" in col else None, KT_TO_MS),
            )

            # 기압 (hPa)
            pressure = best_val(
                safe_float(row[col["USA_PRES"]]),
                safe_float(row[col["WMO_PRES"]]),
            )

            # 1분 풍속 없으면 10분에서 역산 (10min / 0.88)
            if wind_1min is None and wind_10min is not None:
                wind_1min = round(wind_10min / 0.88, 2)
            # 10분 풍속 없으면 1분에서 환산
            if wind_10min is None and wind_1min is not None:
                wind_10min = round(wind_1min * 0.88, 2)

            # 기압 없고 풍속 있을 경우 역산 추정
            if pressure is None and wind_1min is not None and wind_1min > 0:
                pressure = round(1010 - (wind_1min / 3.92) ** (1/0.644), 0)

            # 최대직경 (km) = max(R34 4분면) * 1.852 * 2
            r34_vals = []
            for quad in ["USA_R34_NE", "USA_R34_SE", "USA_R34_SW", "USA_R34_NW"]:
                v = safe_float(row[col[quad]] if quad in col else None, NMI_TO_KM)
                if v:
                    r34_vals.append(v)

            if r34_vals:
                max_r34 = max(r34_vals)
                diameter_km = round(max_r34 * 2, 0)
            else:
                # RMW 기반 추정 (작은 값이지만 없는 것보다 나음)
                rmw = safe_float(row[col["USA_RMW"]] if "USA_RMW" in col else None, NMI_TO_KM)
                diameter_km = round(rmw * 2, 0) if rmw else None

            wind_ref = wind_1min or wind_10min
            intensity = classify_intensity(wind_ref)

            point = {
                "dt": dt,
                "lat": lat,
                "lng": lng,
                "wind_ms": wind_ref,
                "wind_1min_ms": wind_1min,
                "wind_10min_ms": wind_10min,
                "pressure": int(pressure) if pressure else None,
                "intensity": intensity,
                "diameter_km": int(diameter_km) if diameter_km else None,
            }
            typhoons[sid]["track"].append(point)

    # track_count 추가
    result = []
    for sid in order:
        t = typhoons[sid]
        t["track_count"] = len(t["track"])
        result.append(t)

    return result


def main():
    print(f"CSV 파싱 시작: {CSV_PATH}")
    typhoons = parse_csv()
    total_points = sum(len(t["track"]) for t in typhoons)
    print(f"태풍 수: {len(typhoons):,}")
    print(f"트랙 포인트: {total_points:,}")

    # 통계
    has_1min = sum(1 for t in typhoons for p in t["track"] if p["wind_1min_ms"])
    has_10min = sum(1 for t in typhoons for p in t["track"] if p["wind_10min_ms"])
    has_diam = sum(1 for t in typhoons for p in t["track"] if p["diameter_km"])
    print(f"1분 풍속 완성도: {has_1min/total_points*100:.1f}%")
    print(f"10분 풍속 완성도: {has_10min/total_points*100:.1f}%")
    print(f"최대직경 완성도: {has_diam/total_points*100:.1f}%")

    OUT_PATH.parent.mkdir(exist_ok=True)
    print(f"저장 중: {OUT_PATH}")
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"typhoons": typhoons}, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = OUT_PATH.stat().st_size / 1024 / 1024
    print(f"완료! 파일 크기: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
