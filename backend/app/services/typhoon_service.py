import json
from functools import lru_cache
from pathlib import Path
from app.core.config import settings
from app.models.schemas import TyphoonSummary, TyphoonDetail, TrackPoint

@lru_cache(maxsize=1)
def _load_data() -> dict:
    """typhoons.json을 한 번만 메모리에 로드 (앱 시작 시 캐싱)"""
    path = settings.DATA_PATH
    if not path.exists():
        raise FileNotFoundError(f"데이터 파일 없음: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def get_typhoon_list(year: int | None = None, name: str | None = None) -> list[TyphoonSummary]:
    """태풍 목록 조회 (연도/이름 필터)"""
    data = _load_data()
    results = []
    for t in data["typhoons"]:
        if year and t["year"] != year:
            continue
        if name and name.upper() not in t["name_en"].upper():
            continue
        results.append(TyphoonSummary(
            id=t["id"],
            name_en=t["name_en"],
            year=t["year"],
            season_no=t["season_no"],
            track_count=len(t["track"]),
        ))
    return results

def get_typhoon_years() -> list[int]:
    """보유 연도 목록 반환"""
    data = _load_data()
    years = sorted({t["year"] for t in data["typhoons"]}, reverse=True)
    return years

def get_typhoon_detail(typhoon_id: str) -> TyphoonDetail | None:
    """특정 태풍 상세 경로 조회"""
    data = _load_data()
    for t in data["typhoons"]:
        if t["id"] == typhoon_id:
            return TyphoonDetail(
                id=t["id"],
                name_en=t["name_en"],
                year=t["year"],
                season_no=t["season_no"],
                track_count=len(t["track"]),
                track=[TrackPoint(**p) for p in t["track"]],
            )
    return None
