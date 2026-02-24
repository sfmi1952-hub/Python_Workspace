"""
M5: Ensemble 교차검증 — 2개 이상 LLM 투표 기반 Confidence Score 산출
"""
from dataclasses import dataclass
from typing import Optional

from .providers.base import BaseLLMProvider, LLMResponse
from .engine import ExtractionEngine


@dataclass
class EnsembleResult:
    """Ensemble 검증 결과"""
    final_code: str
    confidence_score: float           # 0.0 ~ 1.0
    confidence_label: str             # high / medium / low
    source: str
    ref_page: str
    ref_sentence: str
    agreement: bool                   # 모델 간 일치 여부
    primary_result: dict
    secondary_result: Optional[dict]
    provider_used: str                # "ensemble" 또는 단일 모델명


class EnsembleVerifier:
    """2개 모델 교차 투표 + Confidence Score 산출"""

    def __init__(self, primary: BaseLLMProvider, secondary: BaseLLMProvider):
        self.primary_engine = ExtractionEngine(primary)
        self.secondary_engine = ExtractionEngine(secondary)

    def verify_single(self, primary_result: dict, secondary_result: dict) -> EnsembleResult:
        """
        단일 담보-속성에 대해 두 모델 결과를 비교하고 최종 판정합니다.
        """
        p_code = str(primary_result.get("inferred_code", "")).strip()
        s_code = str(secondary_result.get("inferred_code", "")).strip()

        p_conf = primary_result.get("confidence", "low")
        s_conf = secondary_result.get("confidence", "low")

        # 일치 여부
        codes_match = self._codes_match(p_code, s_code)

        if codes_match:
            # 완전 일치 → 높은 Confidence
            score = self._conf_to_score(p_conf) * 0.5 + self._conf_to_score(s_conf) * 0.5
            score = min(score + 0.15, 1.0)  # 일치 보너스
            final_code = p_code or s_code
            source = primary_result.get("source", secondary_result.get("source", ""))
            ref_page = primary_result.get("ref_page", "")
            ref_sentence = primary_result.get("ref_sentence", "")
        else:
            # 불일치 → Primary 우선, Confidence 감소
            p_score = self._conf_to_score(p_conf)
            s_score = self._conf_to_score(s_conf)

            if p_score >= s_score:
                final_code = p_code
                source = primary_result.get("source", "")
                ref_page = primary_result.get("ref_page", "")
                ref_sentence = primary_result.get("ref_sentence", "")
                score = p_score * 0.7  # 불일치 페널티
            else:
                final_code = s_code
                source = secondary_result.get("source", "")
                ref_page = secondary_result.get("ref_page", "")
                ref_sentence = secondary_result.get("ref_sentence", "")
                score = s_score * 0.7

        return EnsembleResult(
            final_code=final_code,
            confidence_score=round(score, 3),
            confidence_label=self._score_to_label(score),
            source=source,
            ref_page=ref_page,
            ref_sentence=ref_sentence,
            agreement=codes_match,
            primary_result=primary_result,
            secondary_result=secondary_result,
            provider_used="ensemble",
        )

    def verify_batch(self, primary_results: list, secondary_results: list) -> list[EnsembleResult]:
        """배치 결과 교차 검증"""
        # Secondary를 (benefit, template) 키로 인덱싱
        s_dict = {}
        for r in secondary_results:
            key = (str(r.get("benefit_name", "")).strip(), str(r.get("template_name", "")).strip())
            s_dict[key] = r

        results = []
        for p in primary_results:
            key = (str(p.get("benefit_name", "")).strip(), str(p.get("template_name", "")).strip())
            s = s_dict.get(key, {})
            results.append(self.verify_single(p, s))

        return results

    @staticmethod
    def _codes_match(a: str, b: str) -> bool:
        """두 코드가 실질적으로 일치하는지 (빈칸 포함)"""
        if not a and not b:
            return True
        return a.lower().replace(" ", "") == b.lower().replace(" ", "")

    @staticmethod
    def _conf_to_score(label: str) -> float:
        return {"high": 0.95, "medium": 0.7, "low": 0.4}.get(label, 0.3)

    @staticmethod
    def _score_to_label(score: float) -> str:
        if score >= 0.85:
            return "high"
        elif score >= 0.6:
            return "medium"
        return "low"
