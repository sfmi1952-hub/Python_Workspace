"""
관리자 API 라우트
- 시스템 상태 조회
- Provider 설정
- 감사 로그
- 저장소 관리
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config.settings import settings
from db.session import get_db
from db.models import Policy, ExtractionResult, ReviewQueue, AuditLog, TransferLog
from api.schemas import (
    SystemStatus,
    ProviderStatus,
    ConfigureProviderRequest,
    MessageResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/status", response_model=SystemStatus)
def system_status(db: Session = Depends(get_db)):
    """시스템 전체 상태 조회"""
    from modules.m5_extraction_engine.model_router import list_configured_providers

    providers = []
    for p in list_configured_providers():
        providers.append(ProviderStatus(
            name=p["name"],
            configured=p["configured"],
            model_name=p.get("model", ""),
        ))

    total_policies = db.query(Policy).count()
    total_extractions = db.query(ExtractionResult).count()
    pending_reviews = db.query(ReviewQueue).filter(ReviewQueue.status == "pending").count()

    return SystemStatus(
        providers=providers,
        db_status="ok",
        storage_path=str(settings.storage_dir),
        total_policies=total_policies,
        total_extractions=total_extractions,
        pending_reviews=pending_reviews,
    )


@router.post("/configure-provider", response_model=MessageResponse)
def configure_provider_api(req: ConfigureProviderRequest):
    """Provider API 키 설정"""
    from modules.m5_extraction_engine.model_router import configure_provider

    try:
        configure_provider(req.provider, api_key=req.api_key)
        return MessageResponse(
            message=f"{req.provider} Provider 설정 완료",
            success=True,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/providers")
def list_providers():
    """사용 가능한 Provider 목록"""
    from modules.m5_extraction_engine.model_router import list_configured_providers
    return list_configured_providers()


@router.get("/audit-logs")
def get_audit_logs(
    event_type: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """감사 로그 조회"""
    query = db.query(AuditLog)
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)

    logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "event_type": log.event_type,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "actor": log.actor,
            "action": log.action,
            "details": log.details,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/transfer-logs")
def get_transfer_logs(
    status: str = "",
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """전송 로그 조회"""
    query = db.query(TransferLog)
    if status:
        query = query.filter(TransferLog.status == status)

    logs = query.order_by(TransferLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "filename": log.filename,
            "file_size": log.file_size,
            "direction": log.direction,
            "status": log.status,
            "checksum_sha256": log.checksum_sha256,
            "retry_count": log.retry_count,
            "error_message": log.error_message,
            "transferred_at": log.transferred_at.isoformat() if log.transferred_at else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/storage")
def storage_info():
    """저장소 정보"""
    from modules.m2_storage.storage import PolicyStorage

    storage = PolicyStorage()
    products = storage.list_products()

    return {
        "storage_path": str(settings.storage_dir),
        "total_products": len(products),
        "products": [
            {
                "product_code": p.product_code,
                "product_name": p.product_name,
                "product_type": p.product_type,
                "version": p.version,
                "status": p.status,
                "stored_at": p.stored_at,
            }
            for p in products
        ],
    }


@router.get("/settings")
def get_settings():
    """현재 설정 조회 (민감 정보 마스킹)"""
    return {
        "database_url": settings.database_url.split("///")[0] + "///***",
        "storage_dir": str(settings.storage_dir),
        "export_dir": str(settings.export_dir),
        "auto_confirm_threshold": settings.auto_confirm_threshold,
        "default_provider": settings.default_provider,
        "sftp_host": settings.sftp_host or "(미설정)",
        "crawler_target_url": settings.crawler_target_url,
    }
