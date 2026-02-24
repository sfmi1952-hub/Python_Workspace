"""
M5: LLM Provider 추상 인터페이스
모든 Provider(Gemini, OpenAI, Claude)가 구현해야 하는 공통 인터페이스
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    """통합 LLM 응답 객체"""
    text: str
    model_used: str
    provider: str
    usage: Optional[dict] = None


class BaseLLMProvider(ABC):
    """LLM Provider 추상 기반 클래스"""

    provider_name: str = "base"

    @abstractmethod
    def configure(self, api_key: str):
        """API 키 설정 및 클라이언트 초기화"""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """현재 사용 중인 모델명 반환"""
        ...

    @abstractmethod
    def generate(self, prompt: str, files: list = None, **kwargs) -> LLMResponse:
        """
        텍스트 생성 (통합 인터페이스)
        - prompt: 프롬프트 텍스트
        - files: 첨부 파일 목록 (Provider별 처리 방식 상이)
        """
        ...

    @abstractmethod
    def upload_file(self, path: str, mime_type: str = None, logger=print) -> object:
        """파일 업로드 (Provider별 구현)"""
        ...

    @abstractmethod
    def cleanup_file(self, file_ref: object):
        """업로드된 파일 정리"""
        ...

    def supports_file_upload(self) -> bool:
        """파일 직접 업로드 지원 여부"""
        return True

    def supports_vector_store(self) -> bool:
        """Vector Store(RAG) 지원 여부"""
        return False
