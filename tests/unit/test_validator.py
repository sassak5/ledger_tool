"""ユニットテスト — validator (バリデーション)"""

from __future__ import annotations


from src.core.models import NormalizedTransaction
from src.core.validator import validate


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _make_txn(
    *,
    date: str = "2025-01-15",
    amount_out: int = 0,
    amount_in: int = 0,
    row_id: str = "test_1",
) -> NormalizedTransaction:
    return NormalizedTransaction(
        source_type="bank",
        source_name="mufj",
        row_id=row_id,
        date=date,
        summary="テスト",
        details="",
        amount_out=amount_out,
        amount_in=amount_in,
        balance=None,
        memo="",
        extra={},
        raw={},
    )


# ---------------------------------------------------------------------------
# 4-1: 正常通過
# ---------------------------------------------------------------------------
class TestNormalPass:
    def test_valid_transaction_passes(self):
        txn = _make_txn(amount_in=10000)
        valid, errors = validate([txn])
        assert len(valid) == 1
        assert len([e for e in errors if e.level == "error"]) == 0


# ---------------------------------------------------------------------------
# 4-2: date 空 → error, valid 除外
# ---------------------------------------------------------------------------
class TestDateEmpty:
    def test_empty_date_excluded(self):
        txn = _make_txn(date="", amount_in=1000)
        valid, errors = validate([txn])
        assert len(valid) == 0
        errs = [e for e in errors if e.level == "error"]
        assert len(errs) == 1
        assert "日付" in errs[0].message

    def test_whitespace_date_excluded(self):
        txn = _make_txn(date="   ", amount_in=1000)
        valid, errors = validate([txn])
        assert len(valid) == 0


# ---------------------------------------------------------------------------
# 4-3: 入出金同時に正 → warn, valid に残る
# ---------------------------------------------------------------------------
class TestBothPositive:
    def test_both_positive_warn_but_stays(self):
        txn = _make_txn(amount_out=500, amount_in=1000)
        valid, errors = validate([txn])

        assert len(valid) == 1  # valid に残る
        warns = [e for e in errors if e.level == "warn"]
        assert any("同時" in w.message for w in warns)


# ---------------------------------------------------------------------------
# 4-4: 金額両方0 → warn, valid に残る
# ---------------------------------------------------------------------------
class TestBothZero:
    def test_both_zero_warn_but_stays(self):
        txn = _make_txn(amount_out=0, amount_in=0)
        valid, errors = validate([txn])

        assert len(valid) == 1  # valid に残る
        warns = [e for e in errors if e.level == "warn"]
        assert any("両方0" in w.message for w in warns)
