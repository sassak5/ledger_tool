"""ユニットテスト — parsers (銀行 / Amazon パーサ)"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.parsers.bank import BankParser
from src.core.parsers.amazon import AmazonParser
from src.core.models import RawRecord
from src.core.ruleset.loader import load_yaml
from tests.conftest import FIXTURES_DIR, RULES_DIR


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mufj_config() -> dict:
    cfg = load_yaml(RULES_DIR / "bank_format_mufj.yml")
    cfg["_encoding"] = "utf-8"
    cfg["_config_path"] = str(RULES_DIR / "bank_format_mufj.yml")
    return cfg


@pytest.fixture
def aichibank_config() -> dict:
    cfg = load_yaml(RULES_DIR / "bank_format_aichibank.yml")
    cfg["_encoding"] = "utf-8"
    cfg["_config_path"] = str(RULES_DIR / "bank_format_aichibank.yml")
    return cfg


@pytest.fixture
def amazon_config() -> dict:
    cfg = load_yaml(RULES_DIR / "amazon_summary_map.yml")
    cfg["_encoding"] = "utf-8"
    cfg["_config_path"] = str(RULES_DIR / "amazon_summary_map.yml")
    return cfg


# ---------------------------------------------------------------------------
# 6-1: 銀行CSV正常パース
# ---------------------------------------------------------------------------
class TestBankParserNormal:
    def test_mufj_parses_3_rows(self, mufj_config):
        parser = BankParser()
        records = parser.parse(str(FIXTURES_DIR / "mufj_sample.csv"), mufj_config)

        assert len(records) == 3
        assert all(isinstance(r, RawRecord) for r in records)
        assert all(r.source_kind == "bank_statement" for r in records)
        # 最初のレコードの日付
        assert records[0].fields["date"] == "2025/01/10"

    def test_aichibank_parses_3_rows(self, aichibank_config):
        parser = BankParser()
        records = parser.parse(str(FIXTURES_DIR / "aichibank_sample.csv"), aichibank_config)

        assert len(records) == 3
        assert records[0].fields["date"] == "2025/02/01"


# ---------------------------------------------------------------------------
# 6-2: 銀行「合計」行スキップ
# ---------------------------------------------------------------------------
class TestBankSkipTotal:
    def test_total_row_skipped(self, mufj_config, tmp_path: Path):
        csv_content = (
            "日付,摘要,摘要内容,支払い金額,預かり金額,差引残高,メモ,未資金化区分,入払区分\n"
            "2025/01/10,テスト,,1000,,500000,,,\n"
            "合計,,,1000,,,,\n"
        )
        csv_path = tmp_path / "with_total.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        parser = BankParser()
        records = parser.parse(str(csv_path), mufj_config)
        assert len(records) == 1


# ---------------------------------------------------------------------------
# 6-3: 銀行空行スキップ
# ---------------------------------------------------------------------------
class TestBankSkipEmpty:
    def test_empty_row_skipped(self, mufj_config, tmp_path: Path):
        csv_content = (
            "日付,摘要,摘要内容,支払い金額,預かり金額,差引残高,メモ,未資金化区分,入払区分\n"
            "2025/01/10,テスト,,1000,,500000,,,\n"
            ",,,,,,,\n"
            "2025/01/11,テスト2,,2000,,498000,,,\n"
        )
        csv_path = tmp_path / "with_empty.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        parser = BankParser()
        records = parser.parse(str(csv_path), mufj_config)
        assert len(records) == 2


# ---------------------------------------------------------------------------
# 6-4: Amazon TSV正常パース
# ---------------------------------------------------------------------------
class TestAmazonParserNormal:
    def test_amazon_parses_buckets(self, amazon_config):
        parser = AmazonParser()
        records = parser.parse(str(FIXTURES_DIR / "amazon_sample.tsv"), amazon_config)

        assert len(records) >= 1
        assert all(isinstance(r, RawRecord) for r in records)
        assert all(r.source_kind == "amazon_settlement_report" for r in records)

        bucket_names = [r.fields.get("bucket_name", "") for r in records]
        assert "商品代金" in bucket_names
        assert "配送料" in bucket_names


# ---------------------------------------------------------------------------
# 6-5: Amazon unmapped バケット
# ---------------------------------------------------------------------------
class TestAmazonUnmapped:
    def test_unmapped_bucket_created(self, amazon_config):
        parser = AmazonParser()
        records = parser.parse(str(FIXTURES_DIR / "amazon_sample.tsv"), amazon_config)

        unmapped = [r for r in records if r.fields.get("bucket_name") == "unmapped"]
        # amazon_sample.tsv には UnknownFee があるので unmapped が1件あるはず
        assert len(unmapped) == 1
        assert unmapped[0].fields.get("unmapped_count") == "1"
