"""
M5: AI 추출 엔진 (Core) — 추출 오케스트레이터
PoC_Step3 DiagnosisMapper.process() 리팩토링 + Multi-Provider 지원
"""
import os
import json
import re
import time
import zipfile
import traceback
from pathlib import Path

import pandas as pd

from config.settings import settings
from .providers.base import BaseLLMProvider, LLMResponse
from .prompts import ATTRIBUTE_CONFIGS, build_phase1_prompt, build_phase2_prompt


class ExtractionEngine:
    """AI 기반 약관 정보 추출 엔진"""

    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider

    # ── JSON 파싱 유틸리티 ────────────────────────────────────────────────

    @staticmethod
    def parse_json_response(raw_text: str, logger=print) -> list:
        if not raw_text:
            return []
        cleaned = re.sub(r"```(?:json)?", "", raw_text).strip()
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1:
            logger("  > [JSON] 배열 마커를 찾을 수 없습니다.")
            return []
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as e:
            logger(f"  > [JSON] 파싱 실패: {e}")
            objects = re.findall(r"\{[^{}]*\}", cleaned, re.DOTALL)
            results = []
            for obj_str in objects:
                try:
                    results.append(json.loads(obj_str))
                except Exception:
                    pass
            if results:
                logger(f"  > [JSON] 정규식 복구: {len(results)}개 객체 추출")
            return results

    def parse_json_with_llm_retry(self, raw_text: str, logger=print) -> list:
        result = self.parse_json_response(raw_text, logger)
        if result:
            return result
        logger("  > [JSON] 1차 파싱 실패 — LLM 수정 요청 재시도...")
        fix_prompt = (
            "아래 텍스트는 유효하지 않은 JSON입니다. "
            "올바른 JSON 배열([ { ... }, ... ])만 출력하세요. 다른 설명 없이 JSON만:\n\n"
            + raw_text[:2000]
        )
        try:
            fix_resp = self.provider.generate(fix_prompt)
            result = self.parse_json_response(fix_resp.text, logger)
            if result:
                logger(f"  > [JSON] LLM 수정 후 파싱 성공: {len(result)}개")
            return result
        except Exception as e:
            logger(f"  > [JSON] LLM 수정 재시도 실패: {e}")
            return []

    # ── 매핑 컨텍스트 선택 ────────────────────────────────────────────────

    @staticmethod
    def select_mapping_context(config: dict, maps_by_name: dict) -> str:
        patterns = config.get("mapping_files", [])
        if not patterns:
            return "해당 속성에 대한 매핑 테이블이 없습니다."
        selected = []
        for fname, content in maps_by_name.items():
            if any(p.lower() in fname.lower() for p in patterns):
                selected.append(content)
        if selected:
            return "\n".join(selected)
        return f"[주의] '{config['name']}' 관련 매핑 파일을 찾지 못했습니다."

    # ── 참조 파일 그룹핑 ─────────────────────────────────────────────────

    @staticmethod
    def group_files_by_pair(file_paths: list) -> dict:
        groups = {}
        for f in file_paths:
            folder = os.path.dirname(os.path.abspath(f))
            group_key = os.path.basename(folder) or "default_group"
            groups.setdefault(group_key, []).append(f)
        if len(groups) == 1 and len(next(iter(groups.values()))) > 1:
            only_group = next(iter(groups.values()))
            groups = {}
            for f in only_group:
                base = os.path.splitext(os.path.basename(f))[0]
                groups.setdefault(base, []).append(f)
        return groups

    # ── 텍스트 폴백 (Phase 1) ────────────────────────────────────────────

    def _phase1_text_fallback(self, paths, rule_prompt, extracted_logics, group_name, logger):
        from modules.m3_preprocessor.preprocessor import Preprocessor
        preprocessor = Preprocessor()
        MAX_CHARS = 100_000
        fallback_text = ""
        for p in paths:
            if len(fallback_text) >= MAX_CHARS:
                break
            ext = os.path.splitext(p)[1].lower()
            extracted = ""
            try:
                if ext == ".pdf":
                    extracted = preprocessor.extract_text(p, logger=logger)
                elif ext in [".xlsx", ".xls"]:
                    extracted = pd.read_excel(p).to_csv(index=False)
                else:
                    with open(p, "r", encoding="utf-8", errors="ignore") as tx:
                        extracted = tx.read()
            except Exception:
                pass
            if extracted:
                allowed = MAX_CHARS - len(fallback_text)
                fallback_text += f"\n=== {os.path.basename(p)} ===\n{extracted[:allowed]}\n"

        if fallback_text:
            combined = rule_prompt + "\n\n--- 참조 문서 내용 ---\n" + fallback_text
            try:
                fb_resp = self.provider.generate(combined, timeout=600)
                if fb_resp.text and "관련 내용 없음" not in fb_resp.text:
                    extracted_logics.append(
                        f"=== [Logic from {group_name} (Fallback)] ===\n{fb_resp.text}"
                    )
                    logger(f"  > Fallback Logic 추출: {group_name}")
            except Exception as fe:
                logger(f"  > Fallback 실패: {fe}")

    # ── 메인 추출 파이프라인 ──────────────────────────────────────────────

    def process(
        self,
        target_pdf: str,
        target_excel: str,
        mapping_files: list,
        ref_files: list = None,
        logger=print,
    ) -> dict:
        """
        9개 속성 추출 실행
        Returns: {"file_path": zip_path} 또는 {"error": "..."}
        """
        ref_files = ref_files or []
        try:
            # 입력 로드
            df = pd.read_excel(target_excel)
            if "세부담보템플릿명" not in df.columns:
                return {"error": "Target Excel에 '세부담보템플릿명' 컬럼이 없습니다."}

            benefits_data = (
                df[["담보명_출력물명칭", "세부담보템플릿명"]].dropna().to_dict(orient="records")
            )

            # 매핑 파일 로드
            if not isinstance(mapping_files, list):
                mapping_files = [mapping_files]

            maps_by_name = {}
            logger(f"Processing {len(mapping_files)} Mapping Files...")
            for mf in mapping_files:
                try:
                    df_map = pd.read_excel(mf)
                    df_map = df_map.dropna(how="all", axis=0).dropna(how="all", axis=1)
                    csv_clean = df_map.to_csv(index=False)
                    fname = os.path.basename(mf)
                    maps_by_name[fname] = f"\n\n=== 매핑 테이블: {fname} ===\n{csv_clean}\n"
                except Exception as e:
                    logger(f"Warning: {mf} 로드 실패: {e}")

            # 파일 업로드 (Provider 방식에 따라)
            uploaded_files = []
            vector_store_ids = []

            if self.provider.supports_file_upload():
                pdf_ref = self.provider.upload_file(target_pdf, mime_type="application/pdf", logger=logger)
                uploaded_files.append(pdf_ref)
            elif self.provider.supports_vector_store():
                vs = self.provider.create_vector_store(name="target_policy", logger=logger)
                vector_store_ids.append(vs.id)
                self.provider.upload_to_vector_store(vs.id, target_pdf, logger=logger)

            # 참조 파일 그룹핑
            grouped_refs = self.group_files_by_pair(ref_files) if ref_files else {}

            result_dir = settings.result_dir
            result_dir.mkdir(parents=True, exist_ok=True)
            generated_files = []

            all_items_str = "\n".join(
                f"[{i+1}] 담보명: {b['담보명_출력물명칭']} / 세부담보템플릿명: {b['세부담보템플릿명']}"
                for i, b in enumerate(benefits_data)
            )

            # ── 속성별 격리 루프 ──────────────────────────────────────────
            all_extraction_results = []

            for idx, config in enumerate(ATTRIBUTE_CONFIGS):
                attr_key = config["key"]
                attr_name = config["name"]
                safe_name = attr_key.replace("Inferred_", "")

                logger(f"\n{'='*55}")
                logger(f"[{idx+1}/{len(ATTRIBUTE_CONFIGS)}] {attr_name}")
                logger(f"{'='*55}")

                df_attr = df.copy()
                for col in [attr_key, "Code_Mapping_Reason", "Confidence", "Source", "Ref_Page"]:
                    if col not in df_attr.columns:
                        df_attr[col] = ""

                relevant_context = self.select_mapping_context(config, maps_by_name)

                # ── Phase 1: 로직 추출 ────────────────────────────────────
                cached_path = result_dir / f"Logic_{safe_name}.txt"
                extracted_logics = []

                if grouped_refs:
                    logger(f"Phase 1 (Logic): {attr_name} 규칙 추출 중...")
                    for group_name, paths in grouped_refs.items():
                        try:
                            rule_prompt = build_phase1_prompt(config, group_name, relevant_context)
                            # 참조 파일 업로드 + Phase 1 호출
                            ref_uploaded = []
                            try:
                                if self.provider.supports_file_upload():
                                    for p in paths:
                                        ref_uploaded.append(self.provider.upload_file(p, logger=logger))
                                    resp = self.provider.generate(rule_prompt, files=ref_uploaded, timeout=600)
                                else:
                                    # 텍스트 폴백
                                    self._phase1_text_fallback(
                                        paths, rule_prompt, extracted_logics, group_name, logger
                                    )
                                    continue

                                if resp.text and "관련 내용 없음" not in resp.text:
                                    parsed = self.parse_json_response(resp.text, logger)
                                    if parsed:
                                        extracted_logics.append(
                                            f"=== [Logic from {group_name}] ===\n"
                                            + json.dumps(parsed, ensure_ascii=False, indent=2)
                                        )
                                    else:
                                        extracted_logics.append(
                                            f"=== [Logic from {group_name}] ===\n{resp.text}"
                                        )
                                    logger(f"  > Logic 추출 완료: {group_name}")
                            except Exception as e:
                                logger(f"  > 파일 업로드 실패 ({e}). 텍스트 폴백...")
                                self._phase1_text_fallback(paths, rule_prompt, extracted_logics, group_name, logger)
                            finally:
                                for rf in ref_uploaded:
                                    self.provider.cleanup_file(rf)
                                time.sleep(5)
                        except Exception as ge:
                            logger(f"  > Phase 1 오류 ({group_name}): {ge}")

                    logic_content = (
                        "\n\n".join(extracted_logics) if extracted_logics
                        else "추출된 로직 없음. 표준 보험/의료 지식 활용."
                    )
                    cached_path.write_text(f"=== Logic for {attr_name} ===\n\n{logic_content}", encoding="utf-8")
                    generated_files.append((f"Logic_{safe_name}.txt", str(cached_path)))
                else:
                    if cached_path.exists():
                        logic_content = cached_path.read_text(encoding="utf-8")
                        logger(f"Phase 1 Skip: 캐시 로드 — Logic_{safe_name}.txt")
                    else:
                        logic_content = "추출된 로직 없음. 표준 보험/의료 지식 활용."

                # ── Phase 2: 속성 추론 ────────────────────────────────────
                logger(f"Phase 2 (Inference): {attr_name} 추론 중...")
                prompt = build_phase2_prompt(config, logic_content, all_items_str, relevant_context)

                batch_results = []
                try:
                    kwargs = {"timeout": 1000}
                    if vector_store_ids:
                        kwargs["vector_store_ids"] = vector_store_ids

                    resp = self.provider.generate(
                        prompt,
                        files=uploaded_files if self.provider.supports_file_upload() else None,
                        **kwargs,
                    )

                    logger(f"  > [DEBUG] 응답 첫 500자: {resp.text[:500] if resp.text else '(empty)'}")
                    batch_results = self.parse_json_with_llm_retry(resp.text, logger)

                except Exception as ie:
                    logger(f"  > 추론 실패 ({attr_name}): {ie}")
                    logger(f"  > [DEBUG] {traceback.format_exc()}")

                logger(f"  > API 응답: {len(batch_results)}건")

                # ── 결과 매칭 ─────────────────────────────────────────────
                res_dict = {}
                for r in batch_results:
                    key = (str(r.get("benefit_name", "")).strip(), str(r.get("template_name", "")).strip())
                    res_dict[key] = r

                def find_match(row):
                    bn = str(row["담보명_출력물명칭"]).strip()
                    tn = str(row["세부담보템플릿명"]).strip()
                    if (bn, tn) in res_dict:
                        return res_dict[(bn, tn)]
                    for (rb, rt), val in res_dict.items():
                        if (rb in bn or bn in rb) and (rt in tn or tn in rt):
                            return val
                    return {}

                match_cache = {i: find_match(row) for i, row in df_attr.iterrows()}

                df_attr[attr_key] = [match_cache[i].get("inferred_code", "") for i in df_attr.index]
                df_attr["Confidence"] = [match_cache[i].get("confidence", "") for i in df_attr.index]
                df_attr["Source"] = [match_cache[i].get("source", "") for i in df_attr.index]
                df_attr["Ref_Page"] = [match_cache[i].get("ref_page", "") for i in df_attr.index]

                def make_reason(i):
                    m = match_cache[i]
                    sent = m.get("ref_sentence", "")
                    if sent:
                        return f"[{attr_name}] {sent}"
                    if not m:
                        return f"[{attr_name}] [미매칭: API 응답에서 해당 담보를 찾지 못함]"
                    return ""

                df_attr["Code_Mapping_Reason"] = [make_reason(i) for i in df_attr.index]

                matched = sum(1 for m in match_cache.values() if m)
                logger(f"  > 매칭: {matched}/{len(df_attr)}건")

                # 저장
                exc_path = result_dir / f"Result_{safe_name}.xlsx"
                df_attr.to_excel(str(exc_path), index=False)
                generated_files.append((f"Result_{safe_name}.xlsx", str(exc_path)))
                logger(f"  > Result_{safe_name}.xlsx 저장 완료")

                # 결과 수집 (DB 저장용)
                for i, row in df_attr.iterrows():
                    m = match_cache[i]
                    if m:
                        all_extraction_results.append({
                            "benefit_name": str(row.get("담보명_출력물명칭", "")),
                            "template_name": str(row.get("세부담보템플릿명", "")),
                            "attribute": attr_key,
                            "inferred_code": m.get("inferred_code", ""),
                            "confidence": m.get("confidence", ""),
                            "source": m.get("source", ""),
                            "ref_page": m.get("ref_page", ""),
                            "ref_sentence": m.get("ref_sentence", ""),
                            "provider": self.provider.provider_name,
                        })

                time.sleep(5)

            # ── 정리 ─────────────────────────────────────────────────────
            for f in uploaded_files:
                self.provider.cleanup_file(f)

            if hasattr(self.provider, "delete_vector_store"):
                for vs_id in vector_store_ids:
                    self.provider.delete_vector_store(vs_id, logger=logger)

            # ZIP 생성
            zip_path = result_dir / "All_Results.zip"
            with zipfile.ZipFile(str(zip_path), "w") as zf:
                for archive_name, fs_path in generated_files:
                    zf.write(fs_path, arcname=archive_name)

            return {
                "file_path": str(zip_path),
                "results": all_extraction_results,
                "generated_files": [name for name, _ in generated_files],
            }

        except Exception as e:
            logger(f"Error: {e}")
            logger(traceback.format_exc())
            return {"error": str(e)}
