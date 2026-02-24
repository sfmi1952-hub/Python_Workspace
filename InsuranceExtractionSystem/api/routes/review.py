"""
HITL 리뷰 API 라우트
- 리뷰 대기 목록 조회
- 승인 / 반려
- 리뷰 통계
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.session import get_db
from db.models import ReviewQueue, ExtractionResult, AuditLog
from api.schemas import ReviewDecision, ReviewListResponse, ReviewItem, MessageResponse

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/pending", response_model=ReviewListResponse)
def list_pending(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """리뷰 대기 목록 조회"""
    query = db.query(ReviewQueue).filter(ReviewQueue.status == "pending")
    total = query.count()

    items = (
        query.order_by(ReviewQueue.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    review_items = []
    for q in items:
        er = db.query(ExtractionResult).filter(ExtractionResult.id == q.extraction_result_id).first()
        review_items.append(ReviewItem(
            id=q.id,
            extraction_result_id=q.extraction_result_id,
            product_code=er.product_code if er else "",
            benefit_name=er.benefit_name if er else "",
            attribute_name=er.attribute_name if er else "",
            extracted_value=er.extracted_value if er else "",
            confidence=er.confidence if er else 0.0,
            status=q.status,
            created_at=q.created_at,
            reviewed_at=q.reviewed_at,
            reviewer=q.reviewer,
        ))

    return ReviewListResponse(
        items=review_items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{review_id}/decide", response_model=MessageResponse)
def decide_review(review_id: int, decision: ReviewDecision, db: Session = Depends(get_db)):
    """리뷰 승인 또는 반려"""
    from modules.m7_validation.validator import ValidationEngine

    queue_item = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
    if not queue_item:
        raise HTTPException(status_code=404, detail="리뷰 항목을 찾을 수 없습니다")

    if queue_item.status != "pending":
        raise HTTPException(status_code=400, detail=f"이미 처리된 항목입니다 (status={queue_item.status})")

    validator = ValidationEngine()

    if decision.action == "approve":
        result = validator.approve_review(
            db=db,
            review_id=review_id,
            reviewer=decision.reviewer,
        )
        return MessageResponse(
            message=f"리뷰 #{review_id} 승인 완료",
            success=True,
            data=result,
        )

    elif decision.action == "reject":
        result = validator.reject_review(
            db=db,
            review_id=review_id,
            corrected_value=decision.corrected_value or "",
            reviewer=decision.reviewer,
        )
        return MessageResponse(
            message=f"리뷰 #{review_id} 반려 — 수정값: {decision.corrected_value}",
            success=True,
            data=result,
        )

    else:
        raise HTTPException(status_code=400, detail="action은 'approve' 또는 'reject'만 가능합니다")


@router.get("/stats")
def review_stats(db: Session = Depends(get_db)):
    """리뷰 통계"""
    pending = db.query(ReviewQueue).filter(ReviewQueue.status == "pending").count()
    approved = db.query(ReviewQueue).filter(ReviewQueue.status == "approved").count()
    rejected = db.query(ReviewQueue).filter(ReviewQueue.status == "rejected").count()

    return {
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "total": pending + approved + rejected,
    }
