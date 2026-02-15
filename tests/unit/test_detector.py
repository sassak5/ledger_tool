"""ユニットテスト — detector (フォーマット検出)"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.detector import detect
from src.core.models import FormatNotMatchedError
from src.core.ruleset.loader import load_all_rules
from tests.conftest import FIXTURES_DIR, RULES_DIR


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def rule_configs():
    return load_all_rules(RULES_DIR)


# ---------------------------------------------------------------------------
# 5-1: MUFJ CSV → 検出
# ---------------------------------------------------------------------------
class TestMufjDetection:
    def test_mufj_detected(self, rule_configs):
        result = detect(str(FIXTURES_DIR / "mufj_sample.csv"), rule_configs)
        assert result.format_id == "mufj_table_v1"
        assert result.source_kind == "bank_statement"


# ---------------------------------------------------------------------------
# 5-2: 愛知銀行 CSV → 検出
# ---------------------------------------------------------------------------
class TestAichibankDetection:
    def test_aichibank_detected(self, rule_configs):
        result = detect(str(FIXTURES_DIR / "aichibank_sample.csv"), rule_configs)
        assert result.format_id == "aichibank_table_v1"
        assert result.source_kind == "bank_statement"


# ---------------------------------------------------------------------------
# 5-3: Amazon TSV → 検出
# ---------------------------------------------------------------------------
class TestAmazonDetection:
    def test_amazon_detected(self, rule_configs):
        result = detect(str(FIXTURES_DIR / "amazon_sample.tsv"), rule_configs)
        assert result.source_kind == "amazon_settlement_report"
        assert result.format_id == "amazon_settlement_v1"


# ---------------------------------------------------------------------------
# 5-4: 不明ヘッダ → FormatNotMatchedError
# ---------------------------------------------------------------------------
class TestUnknownFormat:
    def test_random_csv_raises(self, rule_configs):
        with pytest.raises(FormatNotMatchedError):
            detect(str(FIXTURES_DIR / "random.csv"), rule_configs)


# ---------------------------------------------------------------------------
# 5-5: 空ファイル → FormatNotMatchedError
# ---------------------------------------------------------------------------
class TestEmptyFile:
    def test_empty_file_raises(self, rule_configs):
        with pytest.raises(FormatNotMatchedError):
            detect(str(FIXTURES_DIR / "empty.csv"), rule_configs)


# ---------------------------------------------------------------------------
# 5-6: UTF-8 エンコーディング
# ---------------------------------------------------------------------------
class TestEncodingUtf8:
    def test_utf8_encoding(self, rule_configs):
        result = detect(str(FIXTURES_DIR / "mufj_sample.csv"), rule_configs)
        assert result.encoding == "utf-8"


# ---------------------------------------------------------------------------
# 5-7: CP932 エンコーディング
# ---------------------------------------------------------------------------
class TestEncodingCp932:
    def test_cp932_encoding(self, rule_configs):
        result = detect(str(FIXTURES_DIR / "mufj_cp932.csv"), rule_configs)
        assert result.encoding == "cp932"
        assert result.format_id == "mufj_table_v1"
