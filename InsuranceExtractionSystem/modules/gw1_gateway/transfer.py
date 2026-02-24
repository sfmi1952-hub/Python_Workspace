"""
GW1: 파일 전송 게이트웨이 (file-transfer-gw)
사외 → 사내 CSV 파일 보안 전송

- SFTP 암호화 전송
- SHA-256 체크섬 검증
- IP Whitelist 관리
- 일 1회 배치 또는 이벤트 트리거
- 재전송 로직 (최대 3회)
"""
import hashlib
import datetime
import shutil
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from config.settings import settings
from db.models import TransferLog, AuditLog

try:
    import paramiko
except ImportError:
    paramiko = None


class FileTransferGateway:
    """SFTP 기반 CSV 파일 전송 게이트웨이"""

    MAX_RETRIES = 3

    def __init__(self):
        self.sftp_host = settings.sftp_host
        self.sftp_port = settings.sftp_port
        self.sftp_user = settings.sftp_user
        self.sftp_key_path = settings.sftp_key_path
        self.transfer_dir = settings.transfer_dir
        self.transfer_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_checksum(file_path: str) -> str:
        """SHA-256 체크섬 계산"""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def transfer_file(self, file_path: str, db: Session, logger=print) -> dict:
        """
        CSV 파일을 사내망으로 전송합니다.
        SFTP 미설정 시 로컬 디렉토리 복사로 대체합니다.
        """
        filename = Path(file_path).name
        checksum = self.compute_checksum(file_path)
        file_size = Path(file_path).stat().st_size

        # 전송 로그 업데이트
        log = (
            db.query(TransferLog)
            .filter(TransferLog.filename == filename, TransferLog.status == "pending")
            .first()
        )
        if not log:
            log = TransferLog(filename=filename, file_size=file_size, direction="outbound", status="pending")
            db.add(log)

        log.checksum_sha256 = checksum
        log.status = "transferring"
        db.commit()

        logger(f"[GW1] 전송 시작: {filename} (size={file_size}, checksum={checksum[:16]}...)")

        if self.sftp_host and paramiko:
            # SFTP 전송
            success = self._sftp_transfer(file_path, logger)
        else:
            # 로컬 복사 (개발/테스트용)
            success = self._local_transfer(file_path, logger)

        if success:
            log.status = "completed"
            log.transferred_at = datetime.datetime.utcnow()
            logger(f"  > 전송 완료: {filename}")
        else:
            log.retry_count += 1
            if log.retry_count >= self.MAX_RETRIES:
                log.status = "failed"
                log.error_message = f"Max retries ({self.MAX_RETRIES}) exceeded"
                logger(f"  > 전송 실패 (최대 재시도 초과): {filename}")
            else:
                log.status = "pending"
                logger(f"  > 재시도 대기 ({log.retry_count}/{self.MAX_RETRIES}): {filename}")

        db.add(AuditLog(
            event_type="transfer",
            entity_type="transfer",
            entity_id=log.id,
            actor="system",
            action="transferred" if success else "failed",
            details=f"file={filename}, checksum={checksum}, size={file_size}",
        ))
        db.commit()

        return {"status": log.status, "filename": filename, "checksum": checksum}

    def _sftp_transfer(self, file_path: str, logger=print) -> bool:
        """SFTP를 통한 실제 전송"""
        try:
            transport = paramiko.Transport((self.sftp_host, self.sftp_port))
            if self.sftp_key_path:
                key = paramiko.RSAKey.from_private_key_file(self.sftp_key_path)
                transport.connect(username=self.sftp_user, pkey=key)
            else:
                transport.connect(username=self.sftp_user)

            sftp = paramiko.SFTPClient.from_transport(transport)
            remote_path = f"/incoming/{Path(file_path).name}"
            sftp.put(file_path, remote_path)

            # 체크섬 파일도 전송
            checksum = self.compute_checksum(file_path)
            checksum_file = file_path + ".sha256"
            Path(checksum_file).write_text(checksum)
            sftp.put(checksum_file, remote_path + ".sha256")

            sftp.close()
            transport.close()
            return True
        except Exception as e:
            logger(f"  > SFTP 전송 오류: {e}")
            return False

    def _local_transfer(self, file_path: str, logger=print) -> bool:
        """로컬 디렉토리 복사 (개발용)"""
        try:
            dest = self.transfer_dir / Path(file_path).name
            shutil.copy2(file_path, str(dest))

            # 체크섬 파일
            checksum = self.compute_checksum(file_path)
            (self.transfer_dir / (Path(file_path).name + ".sha256")).write_text(checksum)

            logger(f"  > 로컬 전송 완료: {dest}")
            return True
        except Exception as e:
            logger(f"  > 로컬 전송 오류: {e}")
            return False

    def transfer_batch(self, db: Session, logger=print) -> list[dict]:
        """전송 대기 중인 모든 CSV를 전송합니다."""
        pending = (
            db.query(TransferLog)
            .filter(TransferLog.status == "pending", TransferLog.direction == "outbound")
            .all()
        )

        results = []
        for log in pending:
            file_path = settings.export_dir / log.filename
            if file_path.exists():
                result = self.transfer_file(str(file_path), db, logger)
                results.append(result)

        return results
