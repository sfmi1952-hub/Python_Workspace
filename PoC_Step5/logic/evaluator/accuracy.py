"""담보단위 집합(set) 비교 기반 정확도 평가.

비교 방식:
  1. 정답지와 추출 결과를 (상품코드, 담보PMID, 담보명) 기준으로 그룹화
  2. 각 담보 그룹 내에서 FILL_COLUMNS 값으로 튜플 집합(set) 생성
  3. 두 집합을 비교 → 일치/누락/초과 항목 산출
  4. 순서 무관, 내용만 일치하면 정답 처리
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

ALL_COLUMNS = [
    "상품코드", "담보PMID", "담보명", "담보구분",
    "보기", "보기구분", "납기", "납기구분",
    "시작연령", "시작연령유형", "끝연령", "끝연령유형",
]

ID_COLUMNS = ["상품코드", "담보PMID", "담보명"]

FILL_COLUMNS = [
    "담보구분", "보기", "보기구분", "납기", "납기구분",
    "시작연령", "시작연령유형", "끝연령", "끝연령유형",
]


@dataclass
class CoverageResult:
    """단일 담보에 대한 비교 결과."""
    coverage_key: str           # "상품코드|담보PMID|담보명"
    gt_count: int               # 정답지 행 수
    ext_count: int              # 추출 행 수
    matched_count: int          # 일치 행 수
    missing: List[tuple]        # 정답에만 있는 항목
    extra: List[tuple]          # 추출에만 있는 항목
    is_perfect: bool            # 완전 일치 여부


@dataclass
class AccuracyMetrics:
    # 전체 행 단위
    total_rows_expected: int = 0
    total_rows_extracted: int = 0
    total_rows_matched: int = 0         # 집합 교집합 총 행 수
    row_match_rate: float = 0.0         # matched / expected

    # 담보 단위
    total_coverages: int = 0            # 정답지 담보 수
    perfect_coverages: int = 0          # 집합 완전 일치 담보 수
    coverage_perfect_rate: float = 0.0  # perfect / total

    # 담보별 상세
    coverage_results: List[CoverageResult] = field(default_factory=list)

    # 필드별 정확도 (매칭된 행 기준)
    field_accuracy: Dict[str, float] = field(default_factory=dict)

    # 누락/초과 요약
    missing_rows: List[dict] = field(default_factory=list)
    extra_rows: List[dict] = field(default_factory=list)

    # 호환용 (report_generator에서 사용)
    exact_match_count: int = 0
    exact_match_rate: float = 0.0
    coverage_completeness: float = 0.0
    field_mismatches: List[dict] = field(default_factory=list)


class AccuracyEvaluator:
    """담보단위 집합 비교 기반 평가기."""

    def compare(
        self, extracted_path: str, ground_truth_path: str
    ) -> AccuracyMetrics:
        df_ext = self._load_and_normalize(extracted_path)
        df_gt = self._load_and_normalize(ground_truth_path)

        metrics = AccuracyMetrics(
            total_rows_expected=len(df_gt),
            total_rows_extracted=len(df_ext),
        )

        if df_gt.empty:
            logger.warning("Ground truth is empty")
            return metrics

        # 담보별 그룹화
        gt_groups = self._group_by_coverage(df_gt)
        ext_groups = self._group_by_coverage(df_ext)

        all_keys = set(gt_groups.keys())
        metrics.total_coverages = len(all_keys)

        total_matched = 0
        coverage_results: List[CoverageResult] = []

        for cov_key in sorted(all_keys):
            gt_set = gt_groups.get(cov_key, set())
            ext_set = ext_groups.get(cov_key, set())

            matched = gt_set & ext_set
            missing = gt_set - ext_set
            extra = ext_set - gt_set
            is_perfect = (gt_set == ext_set)

            cr = CoverageResult(
                coverage_key=cov_key,
                gt_count=len(gt_set),
                ext_count=len(ext_set),
                matched_count=len(matched),
                missing=sorted(missing),
                extra=sorted(extra),
                is_perfect=is_perfect,
            )
            coverage_results.append(cr)

            total_matched += len(matched)
            if is_perfect:
                metrics.perfect_coverages += 1

            # 누락/초과 행을 dict로 변환 (리포트용)
            id_parts = cov_key.split("|")
            for tup in missing:
                metrics.missing_rows.append(
                    self._tuple_to_dict(id_parts, tup)
                )
            for tup in extra:
                metrics.extra_rows.append(
                    self._tuple_to_dict(id_parts, tup)
                )

        metrics.coverage_results = coverage_results
        metrics.total_rows_matched = total_matched
        metrics.row_match_rate = (
            total_matched / len(df_gt) if len(df_gt) > 0 else 0.0
        )
        metrics.coverage_perfect_rate = (
            metrics.perfect_coverages / metrics.total_coverages
            if metrics.total_coverages > 0 else 0.0
        )

        # 필드별 정확도 (매칭된 행에서 각 필드가 얼마나 맞는지)
        metrics.field_accuracy = self._compute_field_accuracy(
            gt_groups, ext_groups
        )

        # 담보 커버리지 (추출에 등장한 담보 비율)
        if all_keys:
            ext_coverage_keys = set(ext_groups.keys())
            metrics.coverage_completeness = (
                len(all_keys & ext_coverage_keys) / len(all_keys)
            )

        # 호환용 필드 (report_generator에서 사용)
        metrics.exact_match_count = total_matched
        metrics.exact_match_rate = metrics.row_match_rate

        return metrics

    def _load_and_normalize(self, path: str) -> pd.DataFrame:
        """Load Excel and normalize column values."""
        df = pd.read_excel(path, engine="openpyxl")
        available = [c for c in ALL_COLUMNS if c in df.columns]
        df = df[available].copy()

        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"nan": "", "None": ""})

        return df.reset_index(drop=True)

    def _group_by_coverage(
        self, df: pd.DataFrame
    ) -> Dict[str, Set[tuple]]:
        """담보별로 FILL_COLUMNS 값 튜플의 집합을 생성.

        Returns:
            {"상품코드|담보PMID|담보명": {(담보구분,보기,보기구분,...), ...}}
        """
        groups: Dict[str, Set[tuple]] = {}
        for _, row in df.iterrows():
            key = self._coverage_key(row)
            fill_tuple = tuple(
                str(row.get(col, "")).strip() for col in FILL_COLUMNS
            )
            if key not in groups:
                groups[key] = set()
            groups[key].add(fill_tuple)
        return groups

    def _coverage_key(self, row: pd.Series) -> str:
        parts = [str(row.get(col, "")).strip() for col in ID_COLUMNS]
        return "|".join(parts)

    def _tuple_to_dict(self, id_parts: list, fill_tuple: tuple) -> dict:
        """튜플을 읽기 쉬운 dict로 변환."""
        d = {}
        for i, col in enumerate(ID_COLUMNS):
            d[col] = id_parts[i] if i < len(id_parts) else ""
        for i, col in enumerate(FILL_COLUMNS):
            d[col] = fill_tuple[i] if i < len(fill_tuple) else ""
        return d

    def _compute_field_accuracy(
        self,
        gt_groups: Dict[str, Set[tuple]],
        ext_groups: Dict[str, Set[tuple]],
    ) -> Dict[str, float]:
        """매칭된 행들에서 각 필드별 정확도를 계산.

        매칭된 행 = 교집합에 속하는 행 (모든 필드가 일치하므로 100%).
        → 대신 담보별로 '부분 매칭'을 해서 필드별 정확도를 산출.

        방법: 각 담보에서 정답 행 하나씩에 대해, 추출 집합에서
        가장 많은 필드가 일치하는 행을 찾아 best-match 하고,
        필드별 일치 수를 누적.
        """
        field_match_counts = {col: 0 for col in FILL_COLUMNS}
        total_gt_rows = 0

        for cov_key in gt_groups:
            gt_set = gt_groups[cov_key]
            ext_set = ext_groups.get(cov_key, set())

            if not ext_set:
                total_gt_rows += len(gt_set)
                continue

            ext_list = list(ext_set)

            for gt_tuple in gt_set:
                total_gt_rows += 1

                # 이미 완전 일치하는 항목이 있으면 모든 필드 +1
                if gt_tuple in ext_set:
                    for col in FILL_COLUMNS:
                        field_match_counts[col] += 1
                    continue

                # Best match: 가장 많은 필드가 일치하는 추출 행 찾기
                best_field_matches = [False] * len(FILL_COLUMNS)
                best_count = 0

                for ext_tuple in ext_list:
                    matches = [
                        gt_tuple[i] == ext_tuple[i]
                        for i in range(len(FILL_COLUMNS))
                    ]
                    count = sum(matches)
                    if count > best_count:
                        best_count = count
                        best_field_matches = matches

                for i, col in enumerate(FILL_COLUMNS):
                    if best_field_matches[i]:
                        field_match_counts[col] += 1

        result = {}
        for col in FILL_COLUMNS:
            result[col] = (
                field_match_counts[col] / total_gt_rows
                if total_gt_rows > 0 else 0.0
            )

        return result
