from fastapi import APIRouter, HTTPException
from app.models.schemas import FeedbackRequest, FeedbackResponse
from app.services import typhoon_service, claude_service

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

@router.post("", response_model=FeedbackResponse)
async def create_feedback(req: FeedbackRequest):
    """사용자 예측 경로 → Claude AI 피드백 생성"""
    typhoon = typhoon_service.get_typhoon_detail(req.typhoon_id)
    if not typhoon:
        raise HTTPException(status_code=404, detail=f"태풍 없음: {req.typhoon_id}")

    actual_track = [{"lat": p.lat, "lng": p.lng} for p in typhoon.track]
    return await claude_service.generate_feedback(req, actual_track)
