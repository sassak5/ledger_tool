"""ユニットテスト — ledger_generator (仕訳生成)"""

from __future__ import annotations

import pytest

from src.core.models import NormalizedTransaction, LedgerDraft, ValidationError
from src.core.ledger_generator import (
    generate,
    load_mapping_config,
    LedgerMappingConfig,
)

from tests.conftest import LEDGER_MAPPING_YML


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _cfg() -> LedgerMappingConfig:
    """実際の ledger_mapping.yml からConfig取得"""
    return load_mapping_config(LEDGER_MAPPING_YML)


def _make_bank_txn(
    *,
    amount_out: int = 0,
    amount_in: int = 0,
    summary: str = "",
    details: str = "",
    row_id: str = "test_1",
) -> NormalizedTransaction:
    return NormalizedTransaction(
        source_type="bank",
        source_name="mufj",
        row_id=row_id,
        date="2025-01-15",
        summary=summary,
        details=details,
        amount_out=amount_out,
        amount_in=amount_in,
        balance=None,
        memo="",
        extra={},
        raw={},
    )


def _make_amazon_txn(
    *,
    bucket_name: str = "",
    amount_out: int = 0,
    amount_in: int = 0,
    details: str = "settlement: S001",
    row_id: str = "amazon_1",
) -> NormalizedTransaction:
    return NormalizedTransaction(
        source_type="amazon",
        source_name="amazon_settlement",
        row_id=row_id,
        date="2025-01-20",
        summary=bucket_name,
        details=details,
        amount_out=amount_out,
        amount_in=amount_in,
        balance=None,
        memo="",
        extra={"bucket_name": bucket_name, "settlement_id": "S001"},
        raw={},
    )


# ---------------------------------------------------------------------------
# 1-1: 銀行入金→正常仕訳
# ---------------------------------------------------------------------------
class TestBankInflow:
    def test_normal_inflow(self):
        cfg = _cfg()
        txn = _make_bank_txn(amount_in=10000, summary="カ）テスト")
        drafts, _ = generate([txn], cfg)

        assert len(drafts) == 1
        d = drafts[0]
        assert d.debit_account == "普通預金"
        assert d.credit_account == "売上高"
        assert d.debit_amount == 10000
        assert d.credit_amount == 10000

    # 1-4: 入金例外 override (ATM)
    def test_inflow_override_atm(self):
        cfg = _cfg()
        txn = _make_bank_txn(amount_in=50000, summary="ATMニユウキン")
        drafts, _ = generate([txn], cfg)

        assert len(drafts) == 1
        assert drafts[0].credit_account == "事業主借り"
        assert drafts[0].debit_account == "普通預金"


# ---------------------------------------------------------------------------
# 1-2, 1-3: 銀行出金→キーワードマッチ / 未分類
# ---------------------------------------------------------------------------
class TestBankOutflow:
    # 1-2
    def test_keyword_match_fee(self):
        cfg = _cfg()
        txn = _make_bank_txn(amount_out=440, summary="振込手数料")
        drafts, _ = generate([txn], cfg)

        assert len(drafts) == 1
        assert drafts[0].debit_account == "支払手数料"
        assert drafts[0].credit_account == "普通預金"

    @pytest.mark.parametrize("summary,expected", [
        ("利息", "支払利息"),
        ("家賃", "地代家賃"),
        ("水道料金", "水道光熱費"),
        ("電気代", "水道光熱費"),
        ("ガス代", "水道光熱費"),
        ("通信費用", "通信費"),
        ("保険料", "保険料"),
    ])
    def test_keyword_variants(self, summary: str, expected: str):
        cfg = _cfg()
        txn = _make_bank_txn(amount_out=1000, summary=summary)
        drafts, _ = generate([txn], cfg)
        assert drafts[0].debit_account == expected

    # 1-3: 未分類フォールバック
    def test_unknown_category(self):
        cfg = _cfg()
        txn = _make_bank_txn(amount_out=5000, summary="ナゾノシハライ")
        drafts, errors = generate([txn], cfg)

        assert len(drafts) == 1
        assert drafts[0].debit_account == "未分類"
        warns = [e for e in errors if e.level == "warn"]
        assert len(warns) >= 1


# ---------------------------------------------------------------------------
# 1-5: 金額両方0→スキップ
# ---------------------------------------------------------------------------
class TestZeroAmount:
    def test_both_zero_skips(self):
        cfg = _cfg()
        txn = _make_bank_txn(amount_out=0, amount_in=0, summary="テスト")
        drafts, errors = generate([txn], cfg)

        assert len(drafts) == 0
        warns = [e for e in errors if e.level == "warn"]
        assert len(warns) == 1
        assert "0" in warns[0].message


# ---------------------------------------------------------------------------
# 1-6: description 切り捨て
# ---------------------------------------------------------------------------
class TestDescriptionTruncation:
    def test_truncate_at_max_length(self):
        cfg = _cfg()
        long_summary = "あ" * 101
        txn = _make_bank_txn(amount_in=1000, summary=long_summary)
        drafts, _ = generate([txn], cfg)

        assert len(drafts[0].description) <= cfg.description_max_length


# ---------------------------------------------------------------------------
# 1-7 ~ 1-9: タグ
# ---------------------------------------------------------------------------
class TestBankTags:
    # 1-9: base_tags
    def test_base_tag_bank(self):
        cfg = _cfg()
        txn = _make_bank_txn(amount_in=1000, summary="普通の入金")
        drafts, _ = generate([txn], cfg)
        assert "bank" in drafts[0].tags

    # 1-7: 手数料→fee
    def test_tag_fee(self):
        cfg = _cfg()
        txn = _make_bank_txn(amount_out=440, summary="振込手数料")
        drafts, _ = generate([txn], cfg)
        assert "fee" in drafts[0].tags

    # 1-8: 振替→transfer
    def test_tag_transfer(self):
        cfg = _cfg()
        txn = _make_bank_txn(amount_out=10000, summary="口座振替")
        drafts, _ = generate([txn], cfg)
        assert "transfer" in drafts[0].tags


# ---------------------------------------------------------------------------
# 1-10 ~ 1-14: Amazon
# ---------------------------------------------------------------------------
class TestAmazonLedger:
    # 1-10: バケット正常
    def test_bucket_product(self):
        cfg = _cfg()
        txn = _make_amazon_txn(bucket_name="商品代金", amount_in=50000)
        drafts, _ = generate([txn], cfg)

        assert len(drafts) == 1
        assert drafts[0].debit_account == "売掛金"
        assert drafts[0].credit_account == "売上高"

    # 1-11: 未知バケット→未分類 + warn
    def test_unknown_bucket(self):
        cfg = _cfg()
        txn = _make_amazon_txn(bucket_name="新しいバケット", amount_in=1000)
        drafts, errors = generate([txn], cfg)

        assert drafts[0].debit_account == "未分類"
        assert drafts[0].credit_account == "売掛金"
        warns = [e for e in errors if e.level == "warn"]
        assert len(warns) >= 1

    # 1-12: unmapped → warn出さない
    def test_unmapped_no_warn(self):
        cfg = _cfg()
        txn = _make_amazon_txn(bucket_name="unmapped", amount_in=100)
        drafts, errors = generate([txn], cfg)

        assert drafts[0].debit_account == "未分類"
        warns = [e for e in errors if e.level == "warn" and "バケット" in e.message]
        assert len(warns) == 0

    # 1-13: partner
    def test_amazon_partner(self):
        cfg = _cfg()
        txn = _make_amazon_txn(bucket_name="商品代金", amount_in=1000)
        drafts, _ = generate([txn], cfg)
        assert drafts[0].partner == "Amazon.co.jp"

    # 1-14: 手数料タグ
    def test_amazon_fee_tag(self):
        cfg = _cfg()
        txn = _make_amazon_txn(bucket_name="Amazon手数料", amount_out=8000)
        drafts, _ = generate([txn], cfg)
        assert "fee" in drafts[0].tags
        assert "amazon" in drafts[0].tags


# ---------------------------------------------------------------------------
# 1-15: 複数txn混在
# ---------------------------------------------------------------------------
class TestMixedTransactions:
    def test_bank_and_amazon_mixed(self):
        cfg = _cfg()
        txns = [
            _make_bank_txn(amount_in=10000, summary="入金1", row_id="b1"),
            _make_bank_txn(amount_out=500, summary="手数料", row_id="b2"),
            _make_amazon_txn(bucket_name="商品代金", amount_in=20000, row_id="a1"),
        ]
        drafts, _ = generate(txns, cfg)
        assert len(drafts) == 3


# ---------------------------------------------------------------------------
# 1-16: 未知source_type → bank扱い
# ---------------------------------------------------------------------------
class TestUnknownSourceType:
    def test_creditcard_falls_back_to_bank(self):
        cfg = _cfg()
        txn = NormalizedTransaction(
            source_type="creditcard",
            source_name="unknown_card",
            row_id="cc_1",
            date="2025-03-01",
            summary="テスト",
            details="",
            amount_out=3000,
            amount_in=0,
            balance=None,
            memo="",
            extra={},
            raw={},
        )
        drafts, _ = generate([txn], cfg)
        assert len(drafts) == 1
        # bank のロジックが使われている
        assert drafts[0].credit_account == "普通預金"
