"""
SQLAlchemy ORM 모델 — 약관 추출 시스템 전체 엔티티
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Boolean, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Policy(Base):
    """약관 메타데이터 (M2 저장소 연동)"""
    __tablename__ = "policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_code = Column(String(50), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    product_type = Column(String(50))  # 건강/자동차/화재/생명 등
    version = Column(String(20))
    pdf_path = Column(String(500))
    excel_path = Column(String(500))
    status = Column(String(20), default="pending")  # pending / processing / completed / error
    download_date = Column(DateTime, default=datetime.utcnow)
    source_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    results = relationship("ExtractionResult", back_populates="policy", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_policy_product_version", "product_code", "version", unique=True),
    )


class ExtractionResult(Base):
    """추출 결과 — 상품-담보-세부담보 단위 (M8 Output DB)"""
    __tablename__ = "extraction_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    policy_id = Column(Integer, ForeignKey("policies.id"), nullable=False, index=True)

    # 키 필드
    product_code = Column(String(50), nullable=False)
    benefit_code = Column(String(50))
    benefit_name = Column(String(200))
    sub_benefit_code = Column(String(50))
    template_name = Column(String(200))

    # 추출 속성 (9개)
    diagnosis_code = Column(String(100))       # 진단코드
    exemption_code = Column(String(100))       # 면책코드
    edi_code = Column(String(100))             # EDI코드
    hospital_grade = Column(String(20))        # 병원등급
    hospital_class = Column(String(20))        # 병원분류
    accident_type = Column(String(20))         # 사고유형
    admission_limit = Column(String(20))       # 입원한도일수
    min_admission = Column(String(20))         # 최소입원일수
    coverage_period = Column(String(50))       # 보장기간

    # 메타 필드
    confidence = Column(Float)                 # 0.0 ~ 1.0
    confidence_label = Column(String(10))      # high / medium / low
    source = Column(String(30))                # appendix / policy_text / mapping_table / external_knowledge
    ref_page = Column(String(20))
    ref_sentence = Column(Text)
    provider_used = Column(String(30))         # gemini / openai / claude / ensemble

    # 상태
    verification_status = Column(String(20), default="pending")  # pending / auto_confirmed / review_needed / approved / rejected
    is_exported = Column(Boolean, default=False)
    exported_at = Column(DateTime)

    extracted_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    policy = relationship("Policy", back_populates="results")
    reviews = relationship("ReviewQueue", back_populates="result", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_result_product_benefit", "product_code", "benefit_code", "sub_benefit_code"),
    )


class ReviewQueue(Base):
    """HITL 리뷰 큐 (M7 검증·리뷰 모듈)"""
    __tablename__ = "review_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(Integer, ForeignKey("extraction_results.id"), nullable=False, index=True)
    status = Column(String(20), default="pending")  # pending / in_review / approved / rejected
    reviewer = Column(String(100))
    review_comment = Column(Text)
    original_code = Column(String(100))
    corrected_code = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime)

    result = relationship("ExtractionResult", back_populates="reviews")


class TransferLog(Base):
    """CSV 전송 이력 (GW1 게이트웨이)"""
    __tablename__ = "transfer_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(200), nullable=False)
    file_size = Column(Integer)
    checksum_sha256 = Column(String(64))
    direction = Column(String(10))  # outbound / inbound
    status = Column(String(20))     # pending / transferring / completed / failed
    retry_count = Column(Integer, default=0)
    error_message = Column(Text)
    transferred_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """감사 이력 — 추출·수정·전송 모든 이벤트"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False)   # extraction / review / transfer / sync
    entity_type = Column(String(50))                   # policy / result / transfer
    entity_id = Column(Integer)
    actor = Column(String(100))                        # system / reviewer name
    action = Column(String(50))                        # created / updated / approved / rejected / transferred
    details = Column(Text)                             # JSON 상세 정보
    created_at = Column(DateTime, default=datetime.utcnow)
