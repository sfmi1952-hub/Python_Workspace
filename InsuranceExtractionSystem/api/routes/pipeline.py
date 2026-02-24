"""
파이프라인 관리 API 라우트
- 전체 파이프라인 트리거
- 실행 상태 조회
- 개별 모듈 실행
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from db.session import get_db
from api.schemas import PipelineTriggerRequest, PipelineStatus, MessageResponse
from pipeline.orchestrator import get_orchestrator

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/trigger", response_model=MessageResponse)
async def trigger_pipeline(
    req: PipelineTriggerRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """전체 파이프라인 실행 트리거"""
    orch = get_orchestrator()

    if orch.current_run and orch.current_run.get("status") == "running":
        raise HTTPException(status_code=409, detail="파이프라인이 이미 실행 중입니다")

    # 백그라운드에서 실행
    background_tasks.add_task(
        _run_pipeline_async,
        product_type=req.product_type,
        provider=req.provider,
        ensemble=req.ensemble,
        secondary_provider=req.secondary_provider,
        skip_crawl=req.skip_crawl,
        skip_transfer=req.skip_transfer,
    )

    return MessageResponse(
        message="파이프라인 실행이 시작되었습니다",
        success=True,
        data={"status": "started"},
    )


async def _run_pipeline_async(**kwargs):
    """별도 DB 세션으로 파이프라인 실행"""
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        orch = get_orchestrator()
        await orch.run(db=db, **kwargs)
    finally:
        db.close()


@router.get("/status", response_model=PipelineStatus)
def get_pipeline_status():
    """파이프라인 실행 상태 조회"""
    orch = get_orchestrator()
    status = orch.get_status()
    return PipelineStatus(**status)


@router.post("/export-csv", response_model=MessageResponse)
def export_csv(db: Session = Depends(get_db)):
    """확정 결과 CSV 내보내기"""
    from modules.m8_output_db.output_store import OutputStore

    store = OutputStore()
    csv_path = store.export_csv(db)

    if csv_path:
        return MessageResponse(
            message=f"CSV 내보내기 완료: {csv_path}",
            success=True,
            data={"csv_path": csv_path},
        )
    return MessageResponse(
        message="내보낼 확정 결과가 없습니다",
        success=False,
    )


@router.post("/transfer", response_model=MessageResponse)
def trigger_transfer(db: Session = Depends(get_db)):
    """GW1 파일 전송 트리거"""
    from modules.gw1_gateway.transfer import FileTransferGateway

    gw = FileTransferGateway()
    results = gw.transfer_batch(db)

    return MessageResponse(
        message=f"전송 완료: {len(results)}건",
        success=True,
        data={"transferred": len(results), "results": results},
    )


@router.post("/validate", response_model=MessageResponse)
def trigger_validation(db: Session = Depends(get_db)):
    """M7 검증 트리거"""
    from modules.m7_validation.validator import ValidationEngine

    validator = ValidationEngine()
    stats = validator.validate_pending(db)

    return MessageResponse(
        message="검증 완료",
        success=True,
        data=stats,
    )
