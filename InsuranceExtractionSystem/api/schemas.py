"""
Pydantic 요청/응답 스키마
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ─── Extraction ───────────────────────────────────────────────
class ExtractionRequest(BaseModel):
    """추출 요청 스키마"""
    product_code: str = Field(..., description="상품 코드")
    benefit_code: str = Field(..., description="담보 코드")
    sub_benefit_code: str = Field("", description="세부 담보 코드")
    benefit_name: str = Field(..., description="담보명")
    template_name: str = Field("", description="템플릿명")
    provider: str = Field("gemini", description="LLM Provider (gemini/openai/claude)")
    ensemble: bool = Field(False, description="Ensemble 검증 활성화")
    secondary_provider: Optional[str] = Field(None, description="Ensemble 시 보조 Provider")


class AttributeResult(BaseModel):
    attribute_name: str
    attribute_label: str
    extracted_value: str
    confidence: float
    source: str = ""
    reasoning: str = ""


class ExtractionResponse(BaseModel):
    product_code: str
    benefit_code: str
    sub_benefit_code: str
    benefit_name: str
    results: list[AttributeResult] = []
    overall_confidence: float = 0.0
    provider_used: str = ""
    ensemble_used: bool = False
    processing_time: float = 0.0


class BatchExtractionRequest(BaseModel):
    """배치 추출 요청"""
    provider: str = Field("gemini", description="LLM Provider")
    ensemble: bool = Field(False, description="Ensemble 검증 활성화")
    secondary_provider: Optional[str] = None
    pdf_product_type: str = Field("", description="상품 유형")
    pdf_product_name: str = Field("", description="상품명")
    pdf_version: str = Field("", description="버전")


# ─── Review ───────────────────────────────────────────────────
class ReviewItem(BaseModel):
    id: int
    extraction_result_id: int
    product_code: str
    benefit_name: str
    attribute_name: str
    extracted_value: str
    confidence: float
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewer: Optional[str] = None


class ReviewDecision(BaseModel):
    action: str = Field(..., description="approve / reject")
    corrected_value: Optional[str] = Field(None, description="수정 값 (reject 시)")
    reviewer: str = Field("admin", description="리뷰어")
    comment: str = Field("", description="리뷰 코멘트")


class ReviewListResponse(BaseModel):
    items: list[ReviewItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


# ─── Pipeline ─────────────────────────────────────────────────
class PipelineTriggerRequest(BaseModel):
    """파이프라인 실행 요청"""
    product_type: Optional[str] = Field(None, description="상품유형 필터")
    provider: str = Field("gemini", description="추출에 사용할 Provider")
    ensemble: bool = Field(False, description="Ensemble 모드")
    secondary_provider: Optional[str] = None
    skip_crawl: bool = Field(False, description="크롤링 단계 건너뛰기")
    skip_transfer: bool = Field(False, description="전송 단계 건너뛰기")


class PipelineStatus(BaseModel):
    run_id: str
    status: str  # idle / running / completed / failed
    current_step: str = ""
    progress: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    stats: dict = {}
    logs: list[str] = []


# ─── Admin ────────────────────────────────────────────────────
class ProviderStatus(BaseModel):
    name: str
    configured: bool
    model_name: str = ""


class SystemStatus(BaseModel):
    providers: list[ProviderStatus] = []
    db_status: str = "ok"
    storage_path: str = ""
    total_policies: int = 0
    total_extractions: int = 0
    pending_reviews: int = 0


class ConfigureProviderRequest(BaseModel):
    provider: str
    api_key: str


# ─── Common ──────────────────────────────────────────────────
class MessageResponse(BaseModel):
    message: str
    success: bool = True
    data: Optional[dict] = None
