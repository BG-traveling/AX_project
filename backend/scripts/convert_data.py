"""
태풍 데이터 전처리 스크립트
사용법: python convert_data.py [--source kma|ibtracs]

입력 파일 (둘 중 하나):
  - backend/data/typhoons_raw.csv   (기상청 태풍경로 CSV)
  - backend/data/ibtracs_wp.csv     (IBTrACS 서태평양 CSV)

출력:
  - backend/data/typhoons.json
"""

import csv
import json
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent / "data"


# ──────────────────────────────────────────
# 강도 분류 (최대풍속 m/s 기준)
# ──────────────────────────────────────────
def classify_intensity(wind_ms: float) -> str:
    if wind_ms < 17:
        return "TD"   # 열대저압부
    elif wind_ms < 25:
        return "TS"   # 열대폭풍
    elif wind_ms < 33:
        return "TY"   # 태풍
    else:
        return "STY"  # 강한 태풍


# ──────────────────────────────────────────
# IBTrACS CSV 파싱
# 컬럼: SID, SEASON, NUMBER, BASIN, SUBBASIN, NAME, ISO_TIME,
#        NATURE, LAT, LON, WMO_WIND, WMO_PRES, ...
# ──────────────────────────────────────────
def parse_ibtracs(filepath: Path) -> list:
    typhoons = defaultdict(lambda: {
        "id": "", "name_ko": "", "name_en": "",
        "year": 0, "season_no": 0, "track": []
    })

    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        next(reader)  # IBTrACS 두 번째 줄은 단위 행 → 스킵

        for row in reader:
            basin = row.get("BASIN", "").strip()
            if basin not in ("WP", "EP"):  # 서태평양만
                continue

            sid = row.get("SID", "").strip()
            season = row.get("SEASON", "").strip()
            name = row.get("NAME", "").strip().upper()
            iso_time = row.get("ISO_TIME", "").strip()
            lat = row.get("LAT", "").strip()
            lon = row.get("LON", "").strip()
            wind = row.get("WMO_WIND", "").strip()
            pres = row.get("WMO_PRES", "").strip()
            number = row.get("NUMBER", "").strip()

            if not lat or not lon or not iso_time:
                continue
            try:
                lat_f = float(lat)
                lon_f = float(lon)
                year = int(season)
            except ValueError:
                continue

            wind_f = float(wind) * 0.514444 if wind else 0  # kt → m/s
            pres_i = int(float(pres)) if pres else 0

            point = {
                "datetime": iso_time,
                "lat": round(lat_f, 1),
                "lng": round(lon_f, 1),
                "pressure": pres_i,
                "wind_speed": round(wind_f, 1),
                "intensity": classify_intensity(wind_f),
            }

            if not typhoons[sid]["id"]:
                typhoons[sid].update({
                    "id": f"{season}-{name or sid}",
                    "name_en": name or "UNNAMED",
                    "name_ko": "",
                    "year": year,
                    "season_no": int(number) if number else 0,
                })

            typhoons[sid]["track"].append(point)

    result = list(typhoons.values())
    result.sort(key=lambda x: (x["year"], x["season_no"]))
    return result


# ──────────────────────────────────────────
# 기상청 태풍경로 CSV 파싱
# 기상청 파일 구조는 다운로드 후 실제 컬럼명 확인 필요
# 아래는 일반적인 컬럼 예시 기준
# ──────────────────────────────────────────
def parse_kma(filepath: Path) -> list:
    typhoons = defaultdict(lambda: {
        "id": "", "name_ko": "", "name_en": "",
        "year": 0, "season_no": 0, "track": []
    })

    with open(filepath, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 기상청 컬럼 매핑 (다운로드 후 실제 헤더로 수정 필요)
            try:
                typ_id = row.get("태풍번호") or row.get("TYP_SEQ", "")
                year = int(row.get("년도") or row.get("YEAR", 0))
                name_ko = row.get("태풍명(한글)") or row.get("TYP_NAME", "")
                name_en = row.get("태풍명(영문)") or row.get("TYP_EN", "")
                lat = float(row.get("위도") or row.get("LAT", 0))
                lon = float(row.get("경도") or row.get("LON", 0))
                pres = int(row.get("중심기압(hPa)") or row.get("PRESSURE", 0))
                wind = float(row.get("최대풍속(m/s)") or row.get("WIND_SPEED", 0))
                dt = row.get("시각") or row.get("DATETIME", "")
                seq = int(row.get("순번") or row.get("NO", 0))
            except (ValueError, TypeError):
                continue

            sid = f"{year}-{typ_id}"
            point = {
                "datetime": dt,
                "lat": round(lat, 1),
                "lng": round(lon, 1),
                "pressure": pres,
                "wind_speed": round(wind, 1),
                "intensity": classify_intensity(wind),
            }

            if not typhoons[sid]["id"]:
                typhoons[sid].update({
                    "id": f"{year}-{name_en.upper() or typ_id}",
                    "name_ko": name_ko,
                    "name_en": name_en.upper(),
                    "year": year,
                    "season_no": seq,
                })
            typhoons[sid]["track"].append(point)

    result = list(typhoons.values())
    result.sort(key=lambda x: (x["year"], x["season_no"]))
    return result


# ──────────────────────────────────────────
# 메인
# ──────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["kma", "ibtracs"], default="ibtracs")
    args = parser.parse_args()

    if args.source == "ibtracs":
        src = BASE_DIR / "ibtracs_wp.csv"
        print(f"IBTrACS 파싱 중: {src}")
        data = parse_ibtracs(src)
    else:
        src = BASE_DIR / "typhoons_raw.csv"
        print(f"기상청 CSV 파싱 중: {src}")
        data = parse_kma(src)

    out = BASE_DIR / "typhoons.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"typhoons": data}, f, ensure_ascii=False, indent=2)

    print(f"완료: {len(data)}개 태풍 → {out}")
    if data:
        sample = data[-1]
        print(f"샘플 (마지막): {sample['name_en']} {sample['year']}, "
              f"경로 {len(sample['track'])}개 관측점")


if __name__ == "__main__":
    main()
