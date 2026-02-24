"""
M4: RAG 인덱싱 모듈 (rag-indexer)
약관·정답셋·매핑테이블을 벡터 스토어에 인덱싱

- OpenAI File Search API Vector Store 관리
- Gemini File Upload 관리
- 전처리된 청크 인덱싱
- 상품별·담보별 검색 스코프 태깅
"""
import os
from dataclasses import dataclass

from config.settings import settings


@dataclass
class IndexEntry:
    source_file: str
    entry_type: str     # policy / answer_set / mapping_table / guideline
    product_code: str
    chunk_index: int
    text_preview: str


class RAGIndexer:
    """RAG 인덱싱 관리자"""

    def __init__(self, provider=None):
        self.provider = provider
        self._vector_stores = {}  # name → vs_id

    def index_policy(self, pdf_path: str, product_code: str, logger=print) -> str:
        """약관 PDF를 벡터 스토어에 인덱싱합니다."""
        if not self.provider:
            logger("[M4] Provider 미설정 — 인덱싱 스킵")
            return ""

        store_name = f"policy_{product_code}"

        if self.provider.supports_vector_store():
            # OpenAI Vector Store 방식
            vs = self.provider.create_vector_store(name=store_name, logger=logger)
            self.provider.upload_to_vector_store(vs.id, pdf_path, logger=logger)
            self._vector_stores[store_name] = vs.id
            logger(f"[M4] Vector Store 인덱싱 완료: {store_name} → {vs.id}")
            return vs.id

        elif self.provider.supports_file_upload():
            # Gemini File Upload 방식
            file_ref = self.provider.upload_file(pdf_path, mime_type="application/pdf", logger=logger)
            self._vector_stores[store_name] = file_ref
            logger(f"[M4] File Upload 인덱싱 완료: {store_name}")
            return str(file_ref)

        return ""

    def index_reference_files(self, file_paths: list, name: str, logger=print) -> str:
        """참조 파일셋(정답셋, 가이드라인)을 인덱싱합니다."""
        if not self.provider or not file_paths:
            return ""

        if self.provider.supports_vector_store():
            vs = self.provider.create_vector_store(name=name, logger=logger)
            for path in file_paths:
                self.provider.upload_to_vector_store(vs.id, path, logger=logger)
            self._vector_stores[name] = vs.id
            logger(f"[M4] 참조 파일 인덱싱 완료: {name} ({len(file_paths)}개 파일)")
            return vs.id

        return ""

    def index_mapping_table(self, excel_path: str, name: str, logger=print) -> str:
        """매핑 테이블을 LLM 질의응답용으로 인덱싱합니다."""
        if not self.provider:
            return ""

        if self.provider.supports_vector_store():
            vs = self.provider.create_vector_store(name=f"mapping_{name}", logger=logger)
            self.provider.upload_to_vector_store(vs.id, excel_path, logger=logger)
            self._vector_stores[f"mapping_{name}"] = vs.id
            return vs.id

        return ""

    def get_vector_store_id(self, name: str) -> str | None:
        return self._vector_stores.get(name)

    def cleanup(self, logger=print):
        """모든 Vector Store 정리"""
        if not self.provider or not hasattr(self.provider, "delete_vector_store"):
            return

        for name, vs_id in self._vector_stores.items():
            try:
                if isinstance(vs_id, str):
                    self.provider.delete_vector_store(vs_id, logger=logger)
            except Exception:
                pass

        self._vector_stores.clear()
        logger("[M4] Vector Store 정리 완료")
