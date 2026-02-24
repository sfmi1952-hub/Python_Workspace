"""
파이프라인 오케스트레이터
M1→M2→M3→M4→M5→M6→M7→M8→GW1 순차 실행 + 상태 관리
"""
import asyncio
import datetime
import json
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from config.settings import settings
from db.models import Policy, AuditLog


class PipelineOrchestrator:
    """전체 추출 파이프라인 오케스트레이터"""

    STEPS = [
        "crawl",        # M1: 약관 수집
        "store",        # M2: 저장소 적재
        "preprocess",   # M3: 전처리
        "index",        # M4: RAG 인덱싱
        "extract",      # M5: AI 추출
        "map",          # M6: 코드 매핑
        "validate",     # M7: 검증/HITL
        "output",       # M8: Output DB
        "transfer",     # GW1: 파일 전송
    ]

    def __init__(self):
        self.current_run: Optional[dict] = None
        self._logs: list[str] = []

    def _log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self._logs.append(entry)
        print(entry)

    def get_status(self) -> dict:
        if not self.current_run:
            return {
                "run_id": "",
                "status": "idle",
                "current_step": "",
                "progress": 0.0,
                "started_at": None,
                "completed_at": None,
                "stats": {},
                "logs": [],
            }
        return {**self.current_run, "logs": list(self._logs[-100:])}

    async def run(
        self,
        db: Session,
        product_type: Optional[str] = None,
        provider: str = "gemini",
        ensemble: bool = False,
        secondary_provider: Optional[str] = None,
        skip_crawl: bool = False,
        skip_transfer: bool = False,
    ) -> dict:
        """전체 파이프라인 실행"""
        run_id = uuid.uuid4().hex[:12]
        self.current_run = {
            "run_id": run_id,
            "status": "running",
            "current_step": "",
            "progress": 0.0,
            "started_at": datetime.datetime.now().isoformat(),
            "completed_at": None,
            "stats": {},
        }
        self._logs = []

        self._log(f"=== 파이프라인 시작 (run_id={run_id}) ===")
        self._log(f"  provider={provider}, ensemble={ensemble}, product_type={product_type}")

        try:
            # Step 1: M1 크롤링
            if not skip_crawl:
                await self._step_crawl(db, product_type, run_id)
            else:
                self._log("[SKIP] M1 크롤링 건너뛰기")

            # Step 2: M2 저장
            policies = await self._step_store(db, product_type, run_id)

            # Step 3: M3 전처리
            preprocessed = await self._step_preprocess(db, policies, run_id)

            # Step 4: M4 인덱싱
            await self._step_index(db, policies, provider, run_id)

            # Step 5: M5 추출
            results = await self._step_extract(
                db, policies, provider, ensemble, secondary_provider, run_id
            )

            # Step 6: M6 매핑
            mapped = await self._step_map(db, results, run_id)

            # Step 7: M7 검증
            validated = await self._step_validate(db, run_id)

            # Step 8: M8 Output
            output = await self._step_output(db, run_id)

            # Step 9: GW1 전송
            if not skip_transfer:
                await self._step_transfer(db, run_id)
            else:
                self._log("[SKIP] GW1 전송 건너뛰기")

            self.current_run["status"] = "completed"
            self.current_run["completed_at"] = datetime.datetime.now().isoformat()
            self.current_run["progress"] = 1.0
            self._log(f"=== 파이프라인 완료 ===")

        except Exception as e:
            self.current_run["status"] = "failed"
            self.current_run["completed_at"] = datetime.datetime.now().isoformat()
            self._log(f"=== 파이프라인 실패: {e} ===")

        # 감사 로그
        db.add(AuditLog(
            event_type="pipeline",
            entity_type="pipeline",
            actor="system",
            action=self.current_run["status"],
            details=json.dumps({
                "run_id": run_id,
                "stats": self.current_run.get("stats", {}),
            }),
        ))
        db.commit()

        return self.get_status()

    # ── 개별 단계 ──────────────────────────────────────────────

    async def _step_crawl(self, db: Session, product_type: Optional[str], run_id: str):
        self._update_step("crawl", 1)
        from modules.m1_crawler.crawler import PolicyCrawler

        crawler = PolicyCrawler()
        results = await crawler.crawl(product_type=product_type, logger=self._log)
        self.current_run["stats"]["crawled"] = len(results)

    async def _step_store(self, db: Session, product_type: Optional[str], run_id: str) -> list:
        self._update_step("store", 2)
        from modules.m2_storage.storage import PolicyStorage

        storage = PolicyStorage()
        policies = storage.list_products(product_type=product_type)
        self.current_run["stats"]["stored"] = len(policies)
        self._log(f"[M2] 저장소 약관: {len(policies)}건")
        return policies

    async def _step_preprocess(self, db: Session, policies: list, run_id: str) -> list:
        self._update_step("preprocess", 3)
        from modules.m2_storage.storage import PolicyStorage
        from modules.m3_preprocessor.preprocessor import PolicyPreprocessor

        storage = PolicyStorage()
        preprocessor = PolicyPreprocessor()
        count = 0

        for meta in policies:
            pdf_path = storage.get_pdf_path(meta.product_type, meta.product_name, meta.version)
            if not pdf_path:
                continue
            try:
                result = preprocessor.process(pdf_path, logger=self._log)
                storage.save_preprocessed(
                    meta.product_type, meta.product_name, meta.version, result
                )
                count += 1
            except Exception as e:
                self._log(f"  > 전처리 오류 ({meta.product_name}): {e}")

        self.current_run["stats"]["preprocessed"] = count
        return policies

    async def _step_index(self, db: Session, policies: list, provider: str, run_id: str):
        self._update_step("index", 4)
        from modules.m4_rag_indexer.indexer import RAGIndexer
        from modules.m2_storage.storage import PolicyStorage

        storage = PolicyStorage()
        indexer = RAGIndexer()
        count = 0

        for meta in policies:
            pdf_path = storage.get_pdf_path(meta.product_type, meta.product_name, meta.version)
            if pdf_path:
                try:
                    indexer.index_policy(pdf_path, provider=provider, logger=self._log)
                    count += 1
                except Exception as e:
                    self._log(f"  > 인덱싱 오류 ({meta.product_name}): {e}")

        self.current_run["stats"]["indexed"] = count

    async def _step_extract(
        self, db: Session, policies: list, provider: str,
        ensemble: bool, secondary_provider: Optional[str], run_id: str
    ) -> list:
        self._update_step("extract", 5)
        self._log(f"[M5] 추출 시작 (provider={provider}, ensemble={ensemble})")

        # 실제 구현 시 ExtractionEngine 호출
        # 여기서는 DB에서 extraction 대상 조회
        from modules.m5_extraction_engine.engine import ExtractionEngine
        from modules.m5_extraction_engine.model_router import get_provider, configure_provider

        try:
            primary = get_provider(provider)
            configure_provider(provider)
        except Exception as e:
            self._log(f"  > Provider 설정 오류: {e}")
            self.current_run["stats"]["extracted"] = 0
            return []

        engine = ExtractionEngine(primary)
        self.current_run["stats"]["extracted"] = 0
        self._log(f"  > 추출 엔진 초기화 완료 (실제 추출은 API를 통해 수행)")
        return []

    async def _step_map(self, db: Session, results: list, run_id: str) -> list:
        self._update_step("map", 6)
        self._log("[M6] 코드 매핑 (추출 결과에 이미 적용됨)")
        self.current_run["stats"]["mapped"] = len(results)
        return results

    async def _step_validate(self, db: Session, run_id: str) -> dict:
        self._update_step("validate", 7)
        from modules.m7_validation.validator import ValidationEngine

        validator = ValidationEngine()
        stats = validator.validate_pending(db, logger=self._log)
        self.current_run["stats"]["validated"] = stats
        return stats

    async def _step_output(self, db: Session, run_id: str) -> dict:
        self._update_step("output", 8)
        from modules.m8_output_db.output_store import OutputStore

        store = OutputStore()
        csv_path = store.export_csv(db, logger=self._log)
        self.current_run["stats"]["output_csv"] = csv_path or ""
        return {"csv_path": csv_path}

    async def _step_transfer(self, db: Session, run_id: str):
        self._update_step("transfer", 9)
        from modules.gw1_gateway.transfer import FileTransferGateway

        gw = FileTransferGateway()
        results = gw.transfer_batch(db, logger=self._log)
        self.current_run["stats"]["transferred"] = len(results)

    def _update_step(self, step_name: str, step_num: int):
        total = len(self.STEPS)
        self.current_run["current_step"] = step_name
        self.current_run["progress"] = round((step_num - 1) / total, 2)
        self._log(f"── Step {step_num}/{total}: {step_name} ──")


# 싱글톤 인스턴스
_orchestrator = PipelineOrchestrator()


def get_orchestrator() -> PipelineOrchestrator:
    return _orchestrator
