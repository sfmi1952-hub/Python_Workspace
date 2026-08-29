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
    excel_file: UploadFile = File(...),
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
        get_provider, get_secondary_provider,
    )
    from modules.m5_extraction_engine.engine import ExtractionEngine
    from modules.m5_extraction_engine.ensemble import EnsembleVerifier

    start_time = time.time()

    # 임시 파일 저장
    tmp_dir = Path(tempfile.mkdtemp(prefix="ies_"))
    try:
        pdf_path = tmp_dir / pdf_file.filename
        pdf_path.write_bytes(await pdf_file.read())

        excel_path = tmp_dir / excel_file.filename
        excel_path.write_bytes(await excel_file.read())

        mapping_paths = []
        if mapping_file:
            mapping_path = tmp_dir / mapping_file.filename
            mapping_path.write_bytes(await mapping_file.read())
            mapping_paths.append(str(mapping_path))

        ref_files = []
        if reference_file:
            reference_path = tmp_dir / reference_file.filename
            reference_path.write_bytes(await reference_file.read())
            ref_files.append(str(reference_path))

        # Provider 초기화
        try:
            primary = get_provider(provider)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Provider 초기화 실패: {e}")

        engine = ExtractionEngine(primary)

        # 추출 실행
        results = engine.process(
            target_pdf=str(pdf_path),
            target_excel=str(excel_path),
            mapping_files=mapping_paths,
            ref_files=ref_files,
        )

        if "error" in results:
            raise HTTPException(status_code=500, detail=results["error"])

        # 결과 변환
        extraction_items = results.get("results", [])
        attr_results = []
        overall_conf = 0.0
        for r in extraction_items:
            conf = r.get("confidence", 0.0)
            if isinstance(conf, str):
                try:
                    conf = float(conf.replace("%", ""))
                except ValueError:
                    conf = 0.0
            attr_results.append(AttributeResult(
                attribute_name=r.get("attribute", ""),
                attribute_label=r.get("benefit_name", ""),
                extracted_value=r.get("inferred_code", ""),
                confidence=conf,
                source=r.get("source", provider),
                reasoning=r.get("ref_sentence", ""),
            ))
            overall_conf += conf

        if attr_results:
            overall_conf /= len(attr_results)

        elapsed = round(time.time() - start_time, 2)

        return ExtractionResponse(
            product_code=product_code,
            benefit_code=benefit_code,
            sub_benefit_code=sub_benefit_code,
            benefit_name=benefit_name,
            results=attr_results,
            overall_confidence=round(overall_conf, 1),
            provider_used=provider,
            ensemble_used=False,
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
