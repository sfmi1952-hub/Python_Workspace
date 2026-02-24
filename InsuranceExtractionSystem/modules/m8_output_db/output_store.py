"""
M8: Output DB (사외)
추출 완료된 정형데이터 저장 + CSV Export

- 추출 결과 DB 저장
- 확정 건만 CSV 생성 (상품 단위)
- 전송 대기 큐 관리
"""
import csv
import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from config.settings import settings
from db.models import ExtractionResult, TransferLog, AuditLog


# CSV 출력 컬럼 정의
CSV_COLUMNS = [
    "product_code", "benefit_code", "benefit_name",
    "sub_benefit_code", "template_name",
    "diagnosis_code", "exemption_code", "edi_code",
    "hospital_grade", "hospital_class", "accident_type",
    "admission_limit", "min_admission", "coverage_period",
    "confidence", "confidence_label", "source",
    "ref_page", "verification_status",
    "extracted_at", "provider_used",
]


class OutputStore:
    """Output DB + CSV Export"""

    def __init__(self, export_dir: Path = None):
        self.export_dir = export_dir or settings.export_dir
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def save_results(self, results: list[dict], policy_id: int, db: Session) -> int:
        """추출 결과를 DB에 저장합니다. Returns: 저장 건수"""
        count = 0
        for r in results:
            row = ExtractionResult(
                policy_id=policy_id,
                product_code=r.get("product_code", ""),
                benefit_name=r.get("benefit_name", ""),
                template_name=r.get("template_name", ""),
                diagnosis_code=r.get("inferred_code", "") if r.get("attribute") == "Inferred_Diagnosis_Code" else None,
                exemption_code=r.get("inferred_code", "") if r.get("attribute") == "Inferred_Exemption_Code" else None,
                edi_code=r.get("inferred_code", "") if r.get("attribute") == "Inferred_EDI_Code" else None,
                hospital_grade=r.get("inferred_code", "") if r.get("attribute") == "Inferred_Hospital_Grade" else None,
                hospital_class=r.get("inferred_code", "") if r.get("attribute") == "Inferred_Hospital_Class" else None,
                accident_type=r.get("inferred_code", "") if r.get("attribute") == "Inferred_Accident_Type" else None,
                admission_limit=r.get("inferred_code", "") if r.get("attribute") == "Inferred_Admission_Limit" else None,
                min_admission=r.get("inferred_code", "") if r.get("attribute") == "Inferred_Min_Admission" else None,
                coverage_period=r.get("inferred_code", "") if r.get("attribute") == "Inferred_Coverage_Period" else None,
                confidence_label=r.get("confidence", ""),
                source=r.get("source", ""),
                ref_page=r.get("ref_page", ""),
                ref_sentence=r.get("ref_sentence", ""),
                provider_used=r.get("provider", ""),
                verification_status="pending",
            )
            db.add(row)
            count += 1

        db.commit()
        return count

    def export_csv(self, product_code: str, db: Session) -> str:
        """
        확정 건만 상품 단위 CSV로 생성합니다.
        Returns: CSV 파일 경로
        """
        results = (
            db.query(ExtractionResult)
            .filter(
                ExtractionResult.product_code == product_code,
                ExtractionResult.verification_status.in_(["auto_confirmed", "approved"]),
                ExtractionResult.is_exported == False,
            )
            .all()
        )

        if not results:
            return ""

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{product_code}_{timestamp}.csv"
        filepath = self.export_dir / filename

        with open(str(filepath), "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for r in results:
                writer.writerow({
                    "product_code": r.product_code,
                    "benefit_code": r.benefit_code or "",
                    "benefit_name": r.benefit_name or "",
                    "sub_benefit_code": r.sub_benefit_code or "",
                    "template_name": r.template_name or "",
                    "diagnosis_code": r.diagnosis_code or "",
                    "exemption_code": r.exemption_code or "",
                    "edi_code": r.edi_code or "",
                    "hospital_grade": r.hospital_grade or "",
                    "hospital_class": r.hospital_class or "",
                    "accident_type": r.accident_type or "",
                    "admission_limit": r.admission_limit or "",
                    "min_admission": r.min_admission or "",
                    "coverage_period": r.coverage_period or "",
                    "confidence": r.confidence or "",
                    "confidence_label": r.confidence_label or "",
                    "source": r.source or "",
                    "ref_page": r.ref_page or "",
                    "verification_status": r.verification_status or "",
                    "extracted_at": r.extracted_at.isoformat() if r.extracted_at else "",
                    "provider_used": r.provider_used or "",
                })
                # 내보내기 완료 표시
                r.is_exported = True
                r.exported_at = datetime.datetime.utcnow()

        db.commit()

        # 전송 로그
        db.add(TransferLog(
            filename=filename,
            file_size=filepath.stat().st_size,
            direction="outbound",
            status="pending",
        ))
        db.commit()

        return str(filepath)

    def get_pending_exports(self, db: Session) -> list[str]:
        """전송 대기 중인 CSV 파일 목록"""
        logs = (
            db.query(TransferLog)
            .filter(TransferLog.status == "pending", TransferLog.direction == "outbound")
            .all()
        )
        return [str(self.export_dir / log.filename) for log in logs]
