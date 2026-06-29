from fastapi import APIRouter, HTTPException, Query
from app.services import typhoon_service
from app.models.schemas import TyphoonSummary, TyphoonDetail

router = APIRouter(prefix="/api/typhoons", tags=["typhoons"])

@router.get("/years", response_model=list[int])
def get_years():
    """보유 연도 목록"""
    return typhoon_service.get_typhoon_years()

@router.get("", response_model=list[TyphoonSummary])
def list_typhoons(
    year: int | None = Query(None, description="연도 필터"),
    name: str | None = Query(None, description="이름 필터 (부분 일치)"),
):
    """태풍 목록 조회"""
    return typhoon_service.get_typhoon_list(year=year, name=name)

@router.get("/{typhoon_id}", response_model=TyphoonDetail)
def get_typhoon(typhoon_id: str):
    """특정 태풍 상세 경로"""
    result = typhoon_service.get_typhoon_detail(typhoon_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"태풍 없음: {typhoon_id}")
    return result
