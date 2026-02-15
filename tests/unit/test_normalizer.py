"""ユニットテスト — normalizer (正規化)"""

from __future__ import annotations

from src.core.models import RawRecord
from src.core.normalizer import normalize, normalize_bank, normalize_amazon


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _bank_record(
    *,
    date: str = "2025/01/15",
    amount_out: str = "",
    amount_in: str = "",
    summary: str = "テスト",
    balance: str = "",
    row_number: int = 1,
) -> RawRecord:
    return RawRecord(
        source_kind="bank_statement",
        format_id="mufj_table_v1",
        row_number=row_number,
        fields={
            "date": date,
            "amount_out": amount_out,
            "amount_in": amount_in,
            "summary": summary,
            "balance": balance,
        },
        raw_line={},
    )


def _amazon_record(
    *,
    date: str = "2025/01/20",
    bucket_name: str = "商品代金",
    amount: str = "50000",
    settlement_id: str = "S001",
    row_number: int = 1,
) -> RawRecord:
    return RawRecord(
        source_kind="amazon_settlement_report",
        format_id="amazon_settlement_v1",
        row_number=row_number,
        fields={
            "date": date,
            "bucket_name": bucket_name,
            "amount": amount,
            "settlement_id": settlement_id,
        },
        raw_line={},
    )


# ---------------------------------------------------------------------------
# 3-1 ~ 3-3: 日付フォーマット揺れ
# ---------------------------------------------------------------------------
class TestDateParsing:
    def test_slash_format(self):
        rec = _bank_record(date="2025/01/15")
        txn, errs = normalize_bank(rec, {})
        assert txn is not None
        assert txn.date == "2025-01-15"

    def test_hyphen_format(self):
        rec = _bank_record(date="2025-01-15")
        txn, errs = normalize_bank(rec, {})
        assert txn is not None
        assert txn.date == "2025-01-15"

    def test_dot_format(self):
        rec = _bank_record(date="2025.01.15")
        txn, errs = normalize_bank(rec, {})
        assert txn is not None
        assert txn.date == "2025-01-15"

    # 3-4: パース不能
    def test_invalid_date_returns_error(self):
        rec = _bank_record(date="abc")
        txn, errs = normalize_bank(rec, {})
        assert txn is None
        assert len(errs) == 1
        assert errs[0].level == "error"
        assert "日付" in errs[0].message


# ---------------------------------------------------------------------------
# 3-5 ~ 3-9: 金額パース揺れ
# ---------------------------------------------------------------------------
class TestAmountParsing:
    # 3-5: カンマ除去
    def test_comma_removal(self):
        rec = _bank_record(amount_out="1,234")
        txn, errs = normalize_bank(rec, {})
        assert txn is not None
        assert txn.amount_out == 1234

    # 3-6: 通貨記号除去
    def test_currency_symbol(self):
        rec = _bank_record(amount_in="¥5,000")
        txn, errs = normalize_bank(rec, {})
        assert txn is not None
        assert txn.amount_in == 5000

    # 3-7: 括弧負値 → abs
    def test_parentheses_negative(self):
        rec = _bank_record(amount_out="(500)")
        txn, errs = normalize_bank(rec, {})
        assert txn is not None
        assert txn.amount_out == 500  # abs

    # 3-8: 空文字→0
    def test_empty_string_is_zero(self):
        rec = _bank_record(amount_out="", amount_in="10000")
        txn, errs = normalize_bank(rec, {})
        assert txn is not None
        assert txn.amount_out == 0
        assert txn.amount_in == 10000

    # 3-9: パース不能
    def test_invalid_amount_returns_error(self):
        rec = _bank_record(amount_out="abc円")
        txn, errs = normalize_bank(rec, {})
        assert txn is None
        assert len(errs) == 1
        assert errs[0].level == "error"


# ---------------------------------------------------------------------------
# 3-10, 3-11: Amazon 符号判定
# ---------------------------------------------------------------------------
class TestAmazonAmountSign:
    def test_negative_amount_to_outflow(self):
        rec = _amazon_record(amount="-1500")
        txn, errs = normalize_amazon(rec, {})
        assert txn is not None
        assert txn.amount_out == 1500
        assert txn.amount_in == 0

    def test_positive_amount_to_inflow(self):
        rec = _amazon_record(amount="3000")
        txn, errs = normalize_amazon(rec, {})
        assert txn is not None
        assert txn.amount_in == 3000
        assert txn.amount_out == 0


# ---------------------------------------------------------------------------
# 3-12: 未知 source_kind
# ---------------------------------------------------------------------------
class TestUnknownSourceKind:
    def test_unknown_source_kind_error(self):
        rec = RawRecord(
            source_kind="unknown_format",
            format_id="xxx",
            row_number=1,
            fields={},
            raw_line={},
        )
        txns, errs = normalize([rec], {})
        assert len(txns) == 0
        assert len(errs) == 1
        assert "未対応" in errs[0].message
