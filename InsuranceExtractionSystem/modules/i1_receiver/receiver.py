"""
I1: CSV 수신 에이전트 (csv-receiver)
사내망에서 CSV 파일 수신 및 검증

- 수신 디렉토리 모니터링
- CSV 포맷 검증 (컬럼 스키마)
- 데이터 무결성 체크 (건수, 체크섬)
- 수신 완료 ACK 전송
"""
import hashlib
from pathlib import Path

from config.settings import settings
from modules.m8_output_db.output_store import CSV_COLUMNS


REQUIRED_COLUMNS = [
    "product_code", "benefit_name", "template_name",
    "diagnosis_code", "confidence", "verification_status",
]


class CSVReceiver:
    """CSV 수신 + 검증 에이전트"""

    def __init__(self, receive_dir: Path = None):
        self.receive_dir = receive_dir or settings.receive_dir
        self.receive_dir.mkdir(parents=True, exist_ok=True)

    def scan_incoming(self) -> list[Path]:
        """수신 디렉토리에서 미처리 CSV 파일 목록 반환"""
        return sorted(self.receive_dir.glob("*.csv"))

    def validate_csv(self, csv_path: str, logger=print) -> dict:
        """
        CSV 파일 포맷 및 무결성 검증
        Returns: {"valid": bool, "errors": [...], "row_count": N}
        """
        import csv as csv_module

        errors = []
        row_count = 0

        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv_module.DictReader(f)
                columns = reader.fieldnames or []

                # 컬럼 스키마 검증
                missing = [c for c in REQUIRED_COLUMNS if c not in columns]
                if missing:
                    errors.append(f"누락 컬럼: {', '.join(missing)}")

                # 행 검증
                for i, row in enumerate(reader, 1):
                    row_count += 1
                    # 필수 필드 빈값 체크
                    if not row.get("product_code", "").strip():
                        errors.append(f"Row {i}: product_code 누락")
                    if not row.get("benefit_name", "").strip():
                        errors.append(f"Row {i}: benefit_name 누락")

                    if len(errors) > 20:
                        errors.append("... (오류 20개 초과, 중단)")
                        break

        except Exception as e:
            errors.append(f"파일 읽기 오류: {e}")

        # 체크섬 검증
        checksum_path = Path(csv_path + ".sha256")
        if checksum_path.exists():
            expected = checksum_path.read_text().strip()
            actual = self._compute_checksum(csv_path)
            if expected != actual:
                errors.append(f"체크섬 불일치: expected={expected[:16]}... actual={actual[:16]}...")
        else:
            logger(f"  > [경고] 체크섬 파일 없음: {checksum_path.name}")

        valid = len(errors) == 0
        logger(f"[I1] 검증 {'성공' if valid else '실패'}: {Path(csv_path).name} ({row_count}행, {len(errors)}개 오류)")

        return {"valid": valid, "errors": errors, "row_count": row_count}

    def send_ack(self, csv_path: str, success: bool, logger=print):
        """수신 완료 ACK 파일 생성"""
        ack_path = Path(csv_path).with_suffix(".ack")
        status = "OK" if success else "FAILED"
        ack_path.write_text(f"ACK|{Path(csv_path).name}|{status}")
        logger(f"  > ACK 생성: {ack_path.name} ({status})")

    @staticmethod
    def _compute_checksum(file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
