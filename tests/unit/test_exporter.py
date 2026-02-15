"""ユニットテスト — exporter (出力)"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.core.models import LedgerDraft, NormalizedTransaction, ValidationError
from src.core.exporter import (
    export_smart_import,
    export_ledger_draft,
    export_error_report,
)


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _make_draft(
    *,
    date: str = "2025-01-15",
    debit_account: str = "支払手数料",
    debit_amount: int = 440,
    credit_account: str = "普通預金",
    credit_amount: int = 440,
    description: str = "振込手数料",
    partner: str = "",
    tags: list[str] | None = None,
) -> LedgerDraft:
    return LedgerDraft(
        date=date,
        debit_account=debit_account,
        debit_amount=debit_amount,
        credit_account=credit_account,
        credit_amount=credit_amount,
        description=description,
        partner=partner,
        source_row_id="test_1",
        tags=tags or ["bank"],
    )


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """CSVを読みヘッダとデータを返す"""
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    return fieldnames, rows


# ---------------------------------------------------------------------------
# 7-1: smart_import.csv 日付形式
# ---------------------------------------------------------------------------
class TestSmartImportDate:
    def test_date_format_slash(self, tmp_path: Path):
        draft = _make_draft(date="2025-01-15")
        path = tmp_path / "smart_import.csv"
        export_smart_import(path, [draft])

        _, rows = _read_csv(path)
        assert rows[0]["取引日"] == "2025/01/15"


# ---------------------------------------------------------------------------
# 7-2: smart_import ヘッダ
# ---------------------------------------------------------------------------
class TestSmartImportHeaders:
    def test_all_headers_present(self, tmp_path: Path):
        path = tmp_path / "smart_import.csv"
        export_smart_import(path, [_make_draft()])

        expected = ["取引日", "借方勘定科目", "借方金額", "貸方勘定科目", "貸方金額", "摘要", "取引先", "備考"]
        headers, _ = _read_csv(path)
        assert headers == expected


# ---------------------------------------------------------------------------
# 7-3: 0件でもヘッダ出力
# ---------------------------------------------------------------------------
class TestEmptyExport:
    def test_empty_drafts_header_only(self, tmp_path: Path):
        path = tmp_path / "smart_import.csv"
        export_smart_import(path, [])

        headers, rows = _read_csv(path)
        assert len(headers) > 0
        assert len(rows) == 0

    def test_empty_errors_header_only(self, tmp_path: Path):
        path = tmp_path / "error_report.csv"
        export_error_report(path, [])

        headers, rows = _read_csv(path)
        assert len(headers) > 0
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# 7-4: tags 結合
# ---------------------------------------------------------------------------
class TestTagJoin:
    def test_tags_comma_joined(self, tmp_path: Path):
        draft = _make_draft(tags=["bank", "fee"])
        path = tmp_path / "ledger_draft.csv"
        export_ledger_draft(path, [draft])

        _, rows = _read_csv(path)
        assert rows[0]["tags"] == "bank,fee"
