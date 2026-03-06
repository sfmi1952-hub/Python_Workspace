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
        try:
            print(entry)
        except UnicodeEncodeError:
            print(entry.encode("utf-8", errors="replace").decode("ascii", errors="replace"))

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
        from modules.m1_crawler.crawler import PolicyCrawler

        storage = PolicyStorage()

        # extraction_input/ 디렉토리에서 PDF+Excel 쌍을 스캔하여 M2에 등록
        input_dir = settings.extraction_input_dir
        registered = 0
        if input_dir.exists():
            for folder in sorted(input_dir.iterdir()):
                if not folder.is_dir():
                    continue
                pdfs = [f for f in folder.glob("*.pdf") if not f.name.startswith("~$")]
                excels = [f for f in folder.glob("*.xlsx") if not f.name.startswith("~$")]
                if not pdfs:
                    continue

                pdf_path = str(pdfs[0])
                excel_path = str(excels[0]) if excels else None
                p_name = folder.name
                p_type = product_type or PolicyCrawler._infer_type(pdfs[0])
                p_code = PolicyCrawler._generate_code(p_name)
                version = PolicyCrawler._detect_version(pdfs[0])

                # 이미 등록된 건인지 확인
                existing = storage.get_meta(p_type, p_name, version)
                if existing:
                    self._log(f"  > [M2] 이미 등록됨: {p_name}/{version}")
                    continue

                storage.store(
                    pdf_path=pdf_path,
                    product_type=p_type,
                    product_name=p_name,
                    version=version,
                    product_code=p_code,
                    excel_path=excel_path,
                    logger=self._log,
                )
                registered += 1

        if registered:
            self._log(f"[M2] extraction_input에서 {registered}건 신규 등록")

        # rag_references/ 디렉토리에서 PDF+Excel 정답 페어셋을 M2에 등록 (entry_type=reference)
        ref_dir = settings.rag_references_dir
        ref_registered = 0
        if ref_dir.exists():
            ref_pdfs = [f for f in sorted(ref_dir.iterdir())
                        if f.suffix.lower() == ".pdf" and not f.name.startswith("~$")]
            for pdf_file in ref_pdfs:
                # 같은 이름의 Excel 찾기
                stem = pdf_file.stem
                excel_candidates = [
                    f for f in ref_dir.glob("*.xlsx")
                    if f.stem == stem and not f.name.startswith("~$")
                ]
                excel_path = str(excel_candidates[0]) if excel_candidates else None

                p_name = stem
                p_type = "reference"
                p_code = PolicyCrawler._generate_code(p_name)
                version = PolicyCrawler._detect_version(pdf_file)

                existing = storage.get_meta(p_type, p_name, version)
                if existing:
                    self._log(f"  > [M2] RAG 참조 이미 등록됨: {p_name}")
                    continue

                storage.store(
                    pdf_path=str(pdf_file),
                    product_type=p_type,
                    product_name=p_name,
                    version=version,
                    product_code=p_code,
                    excel_path=excel_path,
                    entry_type="reference",
                    logger=self._log,
                )
                ref_registered += 1

        if ref_registered:
            self._log(f"[M2] rag_references에서 {ref_registered}건 참조 등록")

        policies = storage.list_products(product_type=product_type)
        self.current_run["stats"]["stored"] = len(policies)
        self._log(f"[M2] 저장소 약관: {len(policies)}건 (target: {sum(1 for p in policies if p.entry_type == 'target')}, reference: {sum(1 for p in policies if p.entry_type == 'reference')})")
        return policies

    async def _step_preprocess(self, db: Session, policies: list, run_id: str) -> list:
        self._update_step("preprocess", 3)
        from modules.m2_storage.storage import PolicyStorage
        from modules.m3_preprocessor.preprocessor import Preprocessor

        storage = PolicyStorage()
        preprocessor = Preprocessor()
        count = 0

        target_count = 0
        ref_count = 0
        for meta in policies:
            pdf_path = storage.get_pdf_path(meta.product_type, meta.product_name, meta.version)
            if not pdf_path:
                continue

            # 이미 전처리된 건은 스킵
            policy_dir = storage._get_policy_dir(meta.product_type, meta.product_name, meta.version)
            if (policy_dir / "preprocessed.json").exists():
                label = "target" if meta.entry_type == "target" else "reference"
                self._log(f"  > [M3] 이미 전처리됨 ({label}): {meta.product_name}")
                if meta.entry_type == "reference":
                    ref_count += 1
                else:
                    target_count += 1
                continue

            try:
                result = preprocessor.preprocess(pdf_path, logger=self._log)
                storage.save_preprocessed(
                    meta.product_type, meta.product_name, meta.version, result
                )
                if meta.entry_type == "reference":
                    ref_count += 1
                    self._log(f"  > [M3] RAG 참조 전처리 완료: {meta.product_name}")
                else:
                    target_count += 1
            except Exception as e:
                self._log(f"  > 전처리 오류 ({meta.product_name}): {e}")

        self.current_run["stats"]["preprocessed"] = target_count
        self.current_run["stats"]["rag_preprocessed"] = ref_count
        self._log(f"[M3] 전처리 완료: target={target_count}, reference={ref_count}")

        return policies

    async def _step_index(self, db: Session, policies: list, provider: str, run_id: str):
        self._update_step("index", 4)
        from modules.m4_rag_indexer.indexer import RAGIndexer
        from modules.m2_storage.storage import PolicyStorage

        storage = PolicyStorage()
        indexer = RAGIndexer()
        target_count = 0
        ref_count = 0

        for meta in policies:
            pdf_path = storage.get_pdf_path(meta.product_type, meta.product_name, meta.version)
            if not pdf_path:
                continue
            try:
                if meta.entry_type == "reference":
                    # RAG 참조 파일: PDF + Excel을 함께 인덱싱
                    ref_file_paths = [pdf_path]
                    excel_path = storage.get_excel_path(meta.product_type, meta.product_name, meta.version)
                    if excel_path:
                        ref_file_paths.append(excel_path)
                    indexer.index_reference_files(ref_file_paths, name=f"ref_{meta.product_code}", logger=self._log)
                    ref_count += 1
                else:
                    indexer.index_policy(pdf_path, product_code=meta.product_code, logger=self._log)
                    target_count += 1
            except Exception as e:
                self._log(f"  > 인덱싱 오류 ({meta.product_name}): {e}")

        self.current_run["stats"]["indexed"] = target_count
        self._log(f"[M4] 인덱싱 완료: target={target_count}, reference={ref_count}")

    async def _step_extract(
        self, db: Session, policies: list, provider: str,
        ensemble: bool, secondary_provider: Optional[str], run_id: str
    ) -> list:
        self._update_step("extract", 5)
        self._log(f"[M5] 추출 시작 (provider={provider}, ensemble={ensemble})")

        from modules.m5_extraction_engine.engine import ExtractionEngine
        from modules.m5_extraction_engine.model_router import get_provider
        from modules.m2_storage.storage import PolicyStorage

        try:
            primary = get_provider(provider)
        except Exception as e:
            self._log(f"  > Provider 설정 오류: {e}")
            self.current_run["stats"]["extracted"] = 0
            return []

        engine = ExtractionEngine(primary)
        storage = PolicyStorage()

        # 매핑 테이블 자동 로드
        mapping_dir = settings.data_dir / "mapping_tables"
        mapping_files = [str(f) for f in mapping_dir.glob("*.xlsx")] if mapping_dir.exists() else []
        self._log(f"  > 매핑 테이블: {len(mapping_files)}개")

        # M2에서 reference 타입의 PDF+Excel을 ref_files로 수집
        ref_files = []
        ref_policies = [m for m in policies if m.entry_type == "reference"]
        for ref_meta in ref_policies:
            ref_pdf = storage.get_pdf_path(ref_meta.product_type, ref_meta.product_name, ref_meta.version)
            ref_excel = storage.get_excel_path(ref_meta.product_type, ref_meta.product_name, ref_meta.version)
            if ref_pdf:
                ref_files.append(ref_pdf)
            if ref_excel:
                ref_files.append(ref_excel)
        self._log(f"  > RAG 참조 파일 (M2 reference): {len(ref_files)}개 ({len(ref_policies)}개 페어)")

        # target만 추출 대상
        target_policies = [m for m in policies if m.entry_type == "target"]

        all_results = []
        for meta in target_policies:
            # Excel이 있는 건만 추출 대상
            excel_path = storage.get_excel_path(meta.product_type, meta.product_name, meta.version)
            if not excel_path:
                self._log(f"  > [SKIP] Excel 없음: {meta.product_name}")
                continue

            pdf_path = storage.get_pdf_path(meta.product_type, meta.product_name, meta.version)
            if not pdf_path:
                self._log(f"  > [SKIP] PDF 없음: {meta.product_name}")
                continue

            self._log(f"  > 추출 대상: {meta.product_name}")
            try:
                result = engine.process(
                    target_pdf=pdf_path,
                    target_excel=excel_path,
                    mapping_files=mapping_files,
                    ref_files=ref_files,
                    logger=self._log,
                )

                if "error" in result:
                    self._log(f"  > 추출 오류: {result['error']}")
                else:
                    extraction_results = result.get("results", [])
                    all_results.extend(extraction_results)
                    self._log(f"  > 추출 완료: {len(extraction_results)}건")
                    self._log(f"  > 결과 ZIP: {result.get('file_path', '')}")
            except Exception as e:
                self._log(f"  > 추출 실패 ({meta.product_name}): {e}")

        self.current_run["stats"]["extracted"] = len(all_results)
        return all_results

    async def _step_map(self, db: Session, results: list, run_id: str) -> list:
        self._update_step("map", 6)
        self._log("[M6] 코드 매핑 (추출 결과에 이미 적용됨)")
        self.current_run["stats"]["mapped"] = len(results)
        return results

    async def _step_validate(self, db: Session, run_id: str) -> dict:
        self._update_step("validate", 7)
        from modules.m7_validation.validator import ValidationEngine
        from db.models import ExtractionResult

        validator = ValidationEngine()

        # pending 상태의 추출 결과를 조회하여 배치 검증
        pending_results = (
            db.query(ExtractionResult)
            .filter(ExtractionResult.verification_status == "pending")
            .all()
        )
        if pending_results:
            stats = validator.validate_batch(pending_results, db)
            self._log(f"[M7] 검증 완료: {stats}")
        else:
            stats = {"auto_confirmed": 0, "review_needed": 0}
            self._log("[M7] 검증 대상 없음")

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
