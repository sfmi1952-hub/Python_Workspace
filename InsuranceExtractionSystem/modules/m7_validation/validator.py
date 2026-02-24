"""
M7: 검증·리뷰 모듈 (validation-hitl)
추출 결과 검증 + Human-in-the-Loop 리뷰 관리

- Confidence >= 95%: 자동 확정 → Output DB 직행
- Confidence < 95%: HITL 리뷰 큐에 등록
- 리뷰 워크플로우 (승인/반려/수정)
- 수정 데이터 피드백 축적
"""
import datetime
from typing import Optional

from sqlalchemy.orm import Session

from config.settings import settings
from db.models import ExtractionResult, ReviewQueue, AuditLog


class ValidationEngine:
    """추출 결과 검증 + HITL 관리"""

    def __init__(self, threshold: float = None):
        self.threshold = threshold or settings.auto_confirm_threshold

    def validate_result(self, result: ExtractionResult, db: Session) -> str:
        """
        단일 추출 결과를 검증합니다.
        Returns: "auto_confirmed" | "review_needed"
        """
        conf = result.confidence or 0.0

        if conf >= self.threshold:
            result.verification_status = "auto_confirmed"
            self._log_audit(db, "validation", "result", result.id, "system",
                            "auto_confirmed", f"Confidence {conf:.3f} >= {self.threshold}")
            return "auto_confirmed"
        else:
            result.verification_status = "review_needed"
            # HITL 리뷰 큐에 등록
            review = ReviewQueue(
                result_id=result.id,
                status="pending",
                original_code=result.diagnosis_code,  # 예시 — 실제로는 해당 속성
            )
            db.add(review)
            self._log_audit(db, "validation", "result", result.id, "system",
                            "review_queued", f"Confidence {conf:.3f} < {self.threshold}")
            return "review_needed"

    def validate_batch(self, results: list[ExtractionResult], db: Session) -> dict:
        """배치 검증. Returns: {"auto_confirmed": N, "review_needed": M}"""
        stats = {"auto_confirmed": 0, "review_needed": 0}
        for result in results:
            status = self.validate_result(result, db)
            stats[status] += 1
        db.commit()
        return stats

    def get_review_queue(self, db: Session, status: str = "pending",
                         limit: int = 50, offset: int = 0) -> list[dict]:
        """리뷰 대기 목록을 조회합니다."""
        query = (
            db.query(ReviewQueue)
            .filter(ReviewQueue.status == status)
            .order_by(ReviewQueue.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = []
        for review in query.all():
            result = review.result
            items.append({
                "review_id": review.id,
                "result_id": result.id,
                "benefit_name": result.benefit_name,
                "template_name": result.template_name,
                "diagnosis_code": result.diagnosis_code,
                "confidence": result.confidence,
                "confidence_label": result.confidence_label,
                "source": result.source,
                "ref_page": result.ref_page,
                "ref_sentence": result.ref_sentence,
                "status": review.status,
                "created_at": review.created_at.isoformat() if review.created_at else "",
            })
        return items

    def approve_review(self, review_id: int, reviewer: str, db: Session,
                       corrected_code: str = None, comment: str = None) -> dict:
        """리뷰 승인"""
        review = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
        if not review:
            return {"error": "Review not found"}

        review.status = "approved"
        review.reviewer = reviewer
        review.review_comment = comment
        review.reviewed_at = datetime.datetime.utcnow()

        result = review.result
        if corrected_code:
            review.corrected_code = corrected_code
            # 수정된 코드 반영 (실제로는 해당 속성 필드에 매핑 필요)
            result.diagnosis_code = corrected_code

        result.verification_status = "approved"
        self._log_audit(db, "review", "result", result.id, reviewer,
                        "approved", f"corrected={corrected_code}, comment={comment}")
        db.commit()
        return {"status": "approved", "review_id": review_id}

    def reject_review(self, review_id: int, reviewer: str, reason: str, db: Session) -> dict:
        """리뷰 반려"""
        review = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
        if not review:
            return {"error": "Review not found"}

        review.status = "rejected"
        review.reviewer = reviewer
        review.review_comment = reason
        review.reviewed_at = datetime.datetime.utcnow()
        review.result.verification_status = "rejected"

        self._log_audit(db, "review", "result", review.result_id, reviewer,
                        "rejected", f"reason={reason}")
        db.commit()
        return {"status": "rejected", "review_id": review_id}

    @staticmethod
    def _log_audit(db: Session, event_type: str, entity_type: str,
                   entity_id: int, actor: str, action: str, details: str):
        db.add(AuditLog(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            action=action,
            details=details,
        ))
