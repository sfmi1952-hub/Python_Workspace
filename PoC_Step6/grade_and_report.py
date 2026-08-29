"""
정답(PoC_Step1) 기준으로 Claude / GPT-OSS 결과를 채점하고,
기존 비교 리포트를 보강한 'Comparison_Report_GRADED_*.xlsx' 를 생성한다.
"""
import os
import sys
import datetime
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RESULT_DIR = os.path.join(PROJECT_ROOT, "data", "result")
ANSWER_PATH = r"C:\Users\Shin-Nyum\Desktop\Python_Workspace\PoC_Step1\data\new\무배당_삼성화재_건강보험_마이헬스_파트너(2508.12)_4종_일반형_SAMPLE.xlsx"
CLAUDE_PATH = os.path.join(RESULT_DIR, "Result_Diagnosis_Code__Claude_Opus_4_7.xlsx")
GPT_PATH = os.path.join(RESULT_DIR, "Result_Diagnosis_Code__GPT_OSS.xlsx")

JOIN_KEYS = ["상품코드", "담보코드", "세부담보코드"]
CODE_COL = "Inferred_Diagnosis_Code"
ANSWER_COL = "진단코드"


def _norm(v):
    """비교용 정규화: NaN/공백/대소문자 차이 흡수."""
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("nan", "none", "<na>"):
        return ""
    return s


def grade(df_pred, df_answer, model_label):
    """예측 DataFrame 을 정답과 행 순서(index) 기준으로 1:1 매칭하여 채점.
    입력 Excel·정답·예측 모두 같은 100건/같은 순서를 전제.
    """
    n = min(len(df_pred), len(df_answer))
    df_pred = df_pred.iloc[:n].reset_index(drop=True)
    df_answer = df_answer.iloc[:n].reset_index(drop=True)

    out = df_answer[JOIN_KEYS + ["담보명_출력물명칭", "세부담보템플릿명", ANSWER_COL]].copy()
    out[f"예측_{model_label}"] = df_pred[CODE_COL].values
    out[f"Conf_{model_label}"] = df_pred["Confidence"].values
    out[f"Source_{model_label}"] = df_pred["Source"].values
    out[f"RefPage_{model_label}"] = df_pred["Ref_Page"].values

    out[f"정답여부_{model_label}"] = [
        "정답" if _norm(p) and _norm(p) == _norm(a) else ("오답" if _norm(p) else "미추론")
        for p, a in zip(out[f"예측_{model_label}"], out[ANSWER_COL])
    ]
    return out


def stats(df, model_label):
    judge = df[f"정답여부_{model_label}"]
    total = len(df)
    correct = int((judge == "정답").sum())
    wrong = int((judge == "오답").sum())
    miss = int((judge == "미추론").sum())
    attempted = correct + wrong
    accuracy = correct / total * 100 if total else 0.0
    precision = correct / attempted * 100 if attempted else 0.0
    coverage = attempted / total * 100 if total else 0.0
    return {
        "모델": model_label,
        "총 건수": total,
        "정답": correct,
        "오답": wrong,
        "미추론": miss,
        "Accuracy(%)": round(accuracy, 1),
        "Coverage(%)": round(coverage, 1),
        "Precision(%)": round(precision, 1),
    }


def main():
    if not os.path.exists(ANSWER_PATH):
        sys.exit(f"정답 파일 없음: {ANSWER_PATH}")

    df_answer = pd.read_excel(ANSWER_PATH)
    print(f"정답 데이터 로드: {len(df_answer)} 건")

    df_claude = pd.read_excel(CLAUDE_PATH)
    df_gpt = pd.read_excel(GPT_PATH)

    graded_claude = grade(df_claude, df_answer, "Claude")
    graded_gpt = grade(df_gpt, df_answer, "GPTOSS")

    # 두 채점 결과를 한 테이블에 합침 — index 기준 직접 결합 (중복 키 cartesian 방지)
    merged = graded_claude.copy()
    for col in ["예측_GPTOSS", "정답여부_GPTOSS", "Conf_GPTOSS", "Source_GPTOSS", "RefPage_GPTOSS"]:
        merged[col] = graded_gpt[col].values

    # 정답여부 조합 컬럼
    def _cmp(c, g):
        if c == "정답" and g == "정답":
            return "둘 다 정답"
        if c == "정답" and g != "정답":
            return "Claude만 정답"
        if c != "정답" and g == "정답":
            return "GPT-OSS만 정답"
        return "둘 다 오답/미추론"
    merged["비교"] = [_cmp(c, g) for c, g in zip(merged["정답여부_Claude"], merged["정답여부_GPTOSS"])]

    # 통계
    rows = [stats(graded_claude, "Claude"), stats(graded_gpt, "GPTOSS")]
    df_summary = pd.DataFrame(rows)

    # 조합 비교 분포
    combo = merged["비교"].value_counts().reindex(
        ["둘 다 정답", "Claude만 정답", "GPT-OSS만 정답", "둘 다 오답/미추론"], fill_value=0,
    ).reset_index()
    combo.columns = ["구분", "건수"]
    combo["비율(%)"] = (combo["건수"] / combo["건수"].sum() * 100).round(1)

    # 오답 패턴 (Confusion-like: 정답 코드 → 예측 코드)
    def confusion(df, label):
        sub = df[df[f"정답여부_{label}"] == "오답"].copy()
        if sub.empty:
            return pd.DataFrame(columns=["정답코드", "예측코드", "건수"])
        c = (
            sub.groupby([ANSWER_COL, f"예측_{label}"])
            .size().reset_index(name="건수")
            .rename(columns={ANSWER_COL: "정답코드", f"예측_{label}": "예측코드"})
            .sort_values("건수", ascending=False)
        )
        return c

    conf_claude = confusion(graded_claude, "Claude")
    conf_gpt = confusion(graded_gpt, "GPTOSS")

    # 채점 결과 출력
    print("\n=== 채점 요약 ===")
    print(df_summary.to_string(index=False))
    print("\n=== 모델 간 조합 비교 ===")
    print(combo.to_string(index=False))
    print(f"\n[Claude 오답 패턴 상위 5] (총 {len(conf_claude)} 패턴)")
    print(conf_claude.head(5).to_string(index=False))
    print(f"\n[GPT-OSS 오답 패턴 상위 5] (총 {len(conf_gpt)} 패턴)")
    print(conf_gpt.head(5).to_string(index=False))

    # 기존 비교 리포트(FINAL) 를 베이스로 시트 추가
    finals = sorted([f for f in os.listdir(RESULT_DIR) if f.startswith("Comparison_Report_FINAL_") and f.endswith(".xlsx")])
    base_report = os.path.join(RESULT_DIR, finals[-1]) if finals else None

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(RESULT_DIR, f"Comparison_Report_GRADED_{ts}.xlsx")

    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        df_summary.to_excel(xw, sheet_name="채점_요약", index=False)
        combo.to_excel(xw, sheet_name="모델조합_비교", index=False)
        merged.to_excel(xw, sheet_name="정답_채점_상세", index=False)
        conf_claude.to_excel(xw, sheet_name="Claude_오답패턴", index=False)
        conf_gpt.to_excel(xw, sheet_name="GPTOSS_오답패턴", index=False)
        # 기존 FINAL 리포트의 시트들을 그대로 복사
        if base_report:
            xls_base = pd.ExcelFile(base_report)
            for sheet in xls_base.sheet_names:
                df_old = pd.read_excel(base_report, sheet_name=sheet)
                df_old.to_excel(xw, sheet_name=f"prev_{sheet}"[:31], index=False)

    print(f"\n>>> GRADED report: {out_path}")


if __name__ == "__main__":
    main()
