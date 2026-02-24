"""
추출 API 라우트
- 단건 추출 (PDF 업로드 + 매핑 테이블)
- 배치 추출 (저장소 기반)
- 결과 조회 / 다운로드
"""
import os
import time
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from config.settings import settings
from db.session import get_db
from db.models import ExtractionResult, Policy, AuditLog
from api.schemas import (
    ExtractionResponse,
    AttributeResult,
    MessageResponse,
)

router = APIRouter(prefix="/extraction", tags=["extraction"])


@router.post("/analyze", response_model=ExtractionResponse)
async def analyze(
    pdf_file: UploadFile = File(...),
    mapping_file: UploadFile = File(None),
    reference_file: UploadFile = File(None),
    product_code: str = Form(""),
    benefit_code: str = Form(""),
    sub_benefit_code: str = Form(""),
    benefit_name: str = Form(""),
    template_name: str = Form(""),
    provider: str = Form("gemini"),
    ensemble: bool = Form(False),
    secondary_provider: str = Form(""),
    db: Session = Depends(get_db),
):
    """단건 약관 추출 분석"""
    from modules.m5_extraction_engine.model_router import (
        get_provider, configure_provider, get_secondary_provider,
    )
    from modules.m5_extraction_engine.engine import ExtractionEngine
    from modules.m5_extraction_engine.ensemble import EnsembleVerifier

    start_time = time.time()

    # 임시 파일 저장
    tmp_dir = Path(tempfile.mkdtemp(prefix="ies_"))
    try:
        pdf_path = tmp_dir / pdf_file.filename
        pdf_path.write_bytes(await pdf_file.read())

        mapping_path = None
        if mapping_file:
            mapping_path = tmp_dir / mapping_file.filename
            mapping_path.write_bytes(await mapping_file.read())

        reference_path = None
        if reference_file:
            reference_path = tmp_dir / reference_file.filename
            reference_path.write_bytes(await reference_file.read())

        # Provider 초기화
        try:
            configure_provider(provider)
            primary = get_provider(provider)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Provider 초기화 실패: {e}")

        engine = ExtractionEngine(primary)

        # 파일 그룹 구성
        file_groups = engine._group_files(
            [str(pdf_path)]
            + ([str(mapping_path)] if mapping_path else [])
            + ([str(reference_path)] if reference_path else []),
        )

        # 추출 실행
        results = engine.process(
            pdf_path=str(pdf_path),
            mapping_path=str(mapping_path) if mapping_path else None,
            reference_path=str(reference_path) if reference_path else None,
            product_code=product_code,
            benefit_code=benefit_code,
            sub_benefit_code=sub_benefit_code,
            benefit_name=benefit_name,
            template_name=template_name,
        )

        # Ensemble 검증
        ensemble_used = False
        if ensemble and secondary_provider:
            try:
                configure_provider(secondary_provider)
                secondary = get_provider(secondary_provider)
                secondary_engine = ExtractionEngine(secondary)

                secondary_results = secondary_engine.process(
                    pdf_path=str(pdf_path),
                    mapping_path=str(mapping_path) if mapping_path else None,
                    reference_path=str(reference_path) if reference_path else None,
                    product_code=product_code,
                    benefit_code=benefit_code,
                    sub_benefit_code=sub_benefit_code,
                    benefit_name=benefit_name,
                    template_name=template_name,
                )

                verifier = EnsembleVerifier()
                results = verifier.verify_batch(results, secondary_results)
                ensemble_used = True
            except Exception as e:
                print(f"[Ensemble] 보조 Provider 오류: {e}")

        # 결과 변환
        attr_results = []
        overall_conf = 0.0
        for r in results:
            conf = r.get("confidence", 0.0)
            if isinstance(conf, str):
                try:
                    conf = float(conf.replace("%", ""))
                except ValueError:
                    conf = 0.0
            attr_results.append(AttributeResult(
                attribute_name=r.get("attribute", ""),
                attribute_label=r.get("label", ""),
                extracted_value=r.get("value", ""),
                confidence=conf,
                source=r.get("source", provider),
                reasoning=r.get("reasoning", ""),
            ))
            overall_conf += conf

        if attr_results:
            overall_conf /= len(attr_results)

        # DB 저장
        for ar in attr_results:
            db.add(ExtractionResult(
                policy_id=None,
                product_code=product_code,
                benefit_code=benefit_code,
                sub_benefit_code=sub_benefit_code,
                benefit_name=benefit_name,
                template_name=template_name,
                attribute_name=ar.attribute_name,
                extracted_value=ar.extracted_value,
                confidence=ar.confidence,
                source=ar.source,
                verification_status="auto_confirmed" if ar.confidence >= settings.auto_confirm_threshold else "pending_review",
            ))
        db.commit()

        elapsed = round(time.time() - start_time, 2)

        return ExtractionResponse(
            product_code=product_code,
            benefit_code=benefit_code,
            sub_benefit_code=sub_benefit_code,
            benefit_name=benefit_name,
            results=attr_results,
            overall_confidence=round(overall_conf, 1),
            provider_used=provider,
            ensemble_used=ensemble_used,
            processing_time=elapsed,
        )

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.get("/results")
def list_results(
    product_code: str = "",
    benefit_code: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    """추출 결과 목록 조회"""
    query = db.query(ExtractionResult)

    if product_code:
        query = query.filter(ExtractionResult.product_code == product_code)
    if benefit_code:
        query = query.filter(ExtractionResult.benefit_code == benefit_code)
    if status:
        query = query.filter(ExtractionResult.verification_status == status)

    total = query.count()
    items = (
        query.order_by(ExtractionResult.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            {
                "id": r.id,
                "product_code": r.product_code,
                "benefit_code": r.benefit_code,
                "sub_benefit_code": r.sub_benefit_code,
                "benefit_name": r.benefit_name,
                "attribute_name": r.attribute_name,
                "extracted_value": r.extracted_value,
                "confidence": r.confidence,
                "source": r.source,
                "verification_status": r.verification_status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/download/{result_id}")
def download_result(result_id: int, db: Session = Depends(get_db)):
    """추출 결과 ZIP 다운로드"""
    result = db.query(ExtractionResult).filter(ExtractionResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다")

    # CSV Export 경로 확인
    export_dir = settings.export_dir
    csv_files = sorted(export_dir.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
    if csv_files:
        return FileResponse(str(csv_files[0]), filename=csv_files[0].name)

    raise HTTPException(status_code=404, detail="내보내기 파일이 없습니다")
