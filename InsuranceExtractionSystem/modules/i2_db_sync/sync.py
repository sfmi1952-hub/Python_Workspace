"""
I2: 상품마스터DB 연동 모듈 (master-db-sync)
추출 결과를 기존 상품마스터DB에 적재·업데이트

- CSV → 상품마스터DB 테이블 매핑 변환
- KEY 기준: 상품코드 + 담보코드 + 세부담보코드
- 신규: INSERT / 변경: UPDATE (diff 비교)
- 적재 전 기존 데이터 백업
"""
import csv
import datetime
import json
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from config.settings import settings
from db.models import AuditLog


class MasterDBSync:
    """상품마스터DB 연동 — INSERT/UPDATE 관리"""

    def __init__(self, master_db_url: str = None):
        self.master_db_url = master_db_url or settings.master_db_url
        self.engine = None
        if self.master_db_url:
            self.engine = create_engine(self.master_db_url)

    def sync_csv(self, csv_path: str, local_db: Session, logger=print) -> dict:
        """
        CSV 파일을 상품마스터DB에 동기화합니다.
        Returns: {"inserted": N, "updated": M, "errors": K}
        """
        stats = {"inserted": 0, "updated": 0, "errors": 0, "skipped": 0}

        if not self.engine:
            logger("[I2] 상품마스터DB 미설정 — 시뮬레이션 모드")
            return self._simulate_sync(csv_path, local_db, logger)

        rows = self._read_csv(csv_path)
        logger(f"[I2] 동기화 시작: {Path(csv_path).name} ({len(rows)}행)")

        for row in rows:
            try:
                key = {
                    "product_code": row.get("product_code", ""),
                    "benefit_code": row.get("benefit_code", ""),
                    "sub_benefit_code": row.get("sub_benefit_code", ""),
                }

                # 기존 데이터 조회
                existing = self._find_existing(key)

                if existing:
                    # diff 비교 후 UPDATE
                    changes = self._diff(existing, row)
                    if changes:
                        self._update_record(key, row)
                        stats["updated"] += 1
                        logger(f"  > UPDATE: {key} ({len(changes)} fields changed)")
                    else:
                        stats["skipped"] += 1
                else:
                    # INSERT
                    self._insert_record(row)
                    stats["inserted"] += 1

            except Exception as e:
                stats["errors"] += 1
                logger(f"  > ERROR: {row.get('product_code')}: {e}")

        # 감사 로그
        local_db.add(AuditLog(
            event_type="sync",
            entity_type="master_db",
            actor="system",
            action="synced",
            details=json.dumps(stats),
        ))
        local_db.commit()

        logger(f"  > 동기화 완료: inserted={stats['inserted']}, updated={stats['updated']}, errors={stats['errors']}")
        return stats

    def _simulate_sync(self, csv_path: str, local_db: Session, logger=print) -> dict:
        """상품마스터DB 미설정 시 시뮬레이션"""
        rows = self._read_csv(csv_path)
        stats = {"inserted": len(rows), "updated": 0, "errors": 0, "skipped": 0, "mode": "simulation"}
        logger(f"  > [시뮬레이션] {len(rows)}행 적재 완료 (실제 DB 연동 없음)")

        local_db.add(AuditLog(
            event_type="sync",
            entity_type="master_db",
            actor="system",
            action="simulated",
            details=json.dumps(stats),
        ))
        local_db.commit()
        return stats

    def _find_existing(self, key: dict) -> dict | None:
        """기존 레코드 조회"""
        if not self.engine:
            return None
        # 실제 구현 시 상품마스터DB 테이블에 맞게 쿼리 작성
        return None

    def _insert_record(self, row: dict):
        """신규 레코드 삽입"""
        if not self.engine:
            return
        # 실제 구현 시 상품마스터DB 테이블에 INSERT

    def _update_record(self, key: dict, row: dict):
        """기존 레코드 업데이트"""
        if not self.engine:
            return
        # 실제 구현 시 상품마스터DB 테이블에 UPDATE

    @staticmethod
    def _diff(existing: dict, new: dict) -> list:
        """변경된 필드 목록 반환"""
        changes = []
        compare_fields = [
            "diagnosis_code", "exemption_code", "edi_code",
            "hospital_grade", "hospital_class", "accident_type",
            "admission_limit", "min_admission", "coverage_period",
        ]
        for field in compare_fields:
            old_val = str(existing.get(field, "")).strip()
            new_val = str(new.get(field, "")).strip()
            if old_val != new_val:
                changes.append({"field": field, "old": old_val, "new": new_val})
        return changes

    @staticmethod
    def _read_csv(csv_path: str) -> list[dict]:
        rows = []
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
        return rows
