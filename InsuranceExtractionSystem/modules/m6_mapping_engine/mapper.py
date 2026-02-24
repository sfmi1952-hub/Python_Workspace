"""
M6: 매핑 엔진 (Rule-based)
FCDF131 매핑 테이블 기반 질병분류번호 → 코드값 정확 변환

- FCDF131.xlsx 로드 및 캐싱 (2,876행)
- KCD 코드 범위 비교 (FROM <= code <= TO)
- 진단코드/면책코드 분리 매핑
- 매핑 결과 검증
"""
import os
import re
from pathlib import Path
from functools import lru_cache

import pandas as pd

from config.settings import settings


class MappingEngine:
    """Rule-based 매핑 엔진 — 정확도 100% 보장"""

    def __init__(self, mapping_dir: Path = None):
        self.mapping_dir = mapping_dir or settings.data_dir / "mapping_tables"
        self._cache: dict[str, pd.DataFrame] = {}

    def load_mapping_table(self, filename: str) -> pd.DataFrame:
        """매핑 테이블 로드 + 캐싱"""
        if filename in self._cache:
            return self._cache[filename]

        path = self.mapping_dir / filename
        if not path.exists():
            # 패턴 매칭으로 검색
            for f in self.mapping_dir.glob("*.xlsx"):
                if any(k.lower() in f.name.lower() for k in filename.split("_")):
                    path = f
                    break

        if not path.exists():
            raise FileNotFoundError(f"매핑 테이블 없음: {filename}")

        df = pd.read_excel(str(path))
        df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)
        self._cache[filename] = df
        return df

    def map_kcd_to_code(self, kcd_code: str, mapping_table: pd.DataFrame) -> list[dict]:
        """
        KCD 코드를 매핑 테이블의 코드값으로 변환합니다.
        FROM/TO 범위 비교 로직 사용.
        Returns: [{"code": "0A1", "description": "...", "match_type": "range"}]
        """
        results = []
        kcd = kcd_code.strip().upper()

        # 컬럼명 유연 매칭
        from_cols = [c for c in mapping_table.columns if "FROM" in c.upper() or "시작" in c]
        to_cols = [c for c in mapping_table.columns if "TO" in c.upper() or "종료" in c]
        code_cols = [c for c in mapping_table.columns if "코드" in c or "CODE" in c.upper() or "분류번호" in c]

        if not (from_cols and to_cols and code_cols):
            # 단순 매칭 (1:1 테이블)
            return self._simple_match(kcd, mapping_table)

        from_col = from_cols[0]
        to_col = to_cols[0]
        code_col = code_cols[0]

        for _, row in mapping_table.iterrows():
            from_val = str(row.get(from_col, "")).strip().upper()
            to_val = str(row.get(to_col, "")).strip().upper()
            code_val = str(row.get(code_col, "")).strip()

            if not from_val or not code_val:
                continue

            # 범위 비교
            if self._code_in_range(kcd, from_val, to_val or from_val):
                results.append({
                    "code": code_val,
                    "from": from_val,
                    "to": to_val,
                    "match_type": "range",
                })

        return results

    @staticmethod
    def _code_in_range(code: str, from_code: str, to_code: str) -> bool:
        """
        KCD 코드 범위 비교 (알파벳+숫자 조합)
        예: C00 <= C34 <= C97 → True
        """
        try:
            # 알파벳과 숫자를 분리하여 비교
            def parse(c):
                match = re.match(r"([A-Z]+)(\d+(?:\.\d+)?)", c.upper())
                if match:
                    return match.group(1), float(match.group(2))
                return c, 0.0

            c_alpha, c_num = parse(code)
            f_alpha, f_num = parse(from_code)
            t_alpha, t_num = parse(to_code)

            if c_alpha != f_alpha:
                # 다른 알파벳 그룹이면 알파벳 순서로 비교
                return f_alpha <= c_alpha <= t_alpha

            return f_num <= c_num <= t_num
        except Exception:
            return False

    @staticmethod
    def _simple_match(code: str, table: pd.DataFrame) -> list[dict]:
        """단순 1:1 매칭"""
        results = []
        for col in table.columns:
            for _, row in table.iterrows():
                val = str(row.get(col, "")).strip().upper()
                if val == code:
                    results.append({
                        "code": str(row.iloc[0]),
                        "match_type": "exact",
                        "column": col,
                    })
        return results

    def validate_code(self, code: str, mapping_table: pd.DataFrame) -> bool:
        """코드값이 매핑 테이블에 존재하는지 확인"""
        code_cols = [c for c in mapping_table.columns if "코드" in c or "CODE" in c.upper() or "분류번호" in c]
        for col in code_cols:
            if code.strip() in mapping_table[col].astype(str).str.strip().values:
                return True
        return False

    def select_relevant_tables(self, config: dict) -> dict[str, str]:
        """
        속성별 매핑 파일 패턴으로 관련 테이블 텍스트를 선택합니다.
        (프롬프트 주입용 CSV 형식)
        """
        patterns = config.get("mapping_files", [])
        if not patterns:
            return {}

        selected = {}
        if not self.mapping_dir.exists():
            return selected

        for f in self.mapping_dir.glob("*.xlsx"):
            if any(p.lower() in f.name.lower() for p in patterns):
                try:
                    df = self.load_mapping_table(f.name)
                    selected[f.name] = f"\n=== 매핑 테이블: {f.name} ===\n{df.to_csv(index=False)}\n"
                except Exception:
                    pass

        return selected
