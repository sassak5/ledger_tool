"""ユニットテスト — load_mapping_config (YAML読み込み)"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.core.ledger_generator import load_mapping_config, LedgerMappingConfig
from src.core.models import RuleSetValidationError
from tests.conftest import LEDGER_MAPPING_YML


# ---------------------------------------------------------------------------
# 2-1: 正常読み込み
# ---------------------------------------------------------------------------
class TestNormalLoad:
    def test_all_fields_populated(self):
        cfg = load_mapping_config(LEDGER_MAPPING_YML)

        assert cfg.description_max_length == 100
        assert cfg.bank_inflow_debit == "普通預金"
        assert cfg.bank_inflow_credit == "売上高"
        assert cfg.bank_outflow_credit == "普通預金"
        assert cfg.bank_outflow_unknown_debit == "未分類"
        assert cfg.amazon_default_partner == "Amazon.co.jp"
        assert cfg.amazon_unknown_debit == "未分類"
        assert cfg.amazon_unknown_credit == "売掛金"


# ---------------------------------------------------------------------------
# 2-2: キーワードルール件数
# ---------------------------------------------------------------------------
class TestKeywordCounts:
    def test_outflow_keyword_accounts_count(self):
        cfg = load_mapping_config(LEDGER_MAPPING_YML)
        assert len(cfg.bank_outflow_keyword_accounts) == 7

    def test_tag_keywords_count(self):
        cfg = load_mapping_config(LEDGER_MAPPING_YML)
        assert len(cfg.bank_tag_keywords) == 2

    def test_inflow_overrides_count(self):
        cfg = load_mapping_config(LEDGER_MAPPING_YML)
        assert len(cfg.bank_inflow_overrides) == 1


# ---------------------------------------------------------------------------
# 2-3: bucket_accounts 変換
# ---------------------------------------------------------------------------
class TestBucketAccounts:
    def test_bucket_tuple_conversion(self):
        cfg = load_mapping_config(LEDGER_MAPPING_YML)
        assert cfg.amazon_bucket_accounts["商品代金"] == ("売掛金", "売上高")
        assert cfg.amazon_bucket_accounts["税金"] == ("売掛金", "仮受消費税")
        assert len(cfg.amazon_bucket_accounts) == 7


# ---------------------------------------------------------------------------
# 2-4: 不正 bucket_accounts 無視
# ---------------------------------------------------------------------------
class TestInvalidBucketSkip:
    def test_single_element_list_skipped(self, tmp_path: Path):
        yml_data = {
            "version": 1,
            "kind": "ledger_mapping",
            "amazon": {
                "bucket_accounts": {
                    "正常": ["売掛金", "売上高"],
                    "不正": ["売掛金"],  # 要素1個
                },
            },
        }
        yml_path = tmp_path / "test.yml"
        yml_path.write_text(yaml.dump(yml_data, allow_unicode=True), encoding="utf-8")
        cfg = load_mapping_config(yml_path)

        assert "正常" in cfg.amazon_bucket_accounts
        assert "不正" not in cfg.amazon_bucket_accounts


# ---------------------------------------------------------------------------
# 2-5: YAML キー欠損時デフォルト
# ---------------------------------------------------------------------------
class TestMissingKeysDefaults:
    def test_empty_bank_section(self, tmp_path: Path):
        yml_data = {"version": 1, "kind": "ledger_mapping"}
        yml_path = tmp_path / "minimal.yml"
        yml_path.write_text(yaml.dump(yml_data, allow_unicode=True), encoding="utf-8")
        cfg = load_mapping_config(yml_path)

        assert cfg.bank_inflow_debit == "普通預金"
        assert cfg.bank_inflow_credit == "売上高"
        assert cfg.bank_outflow_credit == "普通預金"
        assert cfg.amazon_default_partner == "Amazon.co.jp"
        assert cfg.description_max_length == 100


# ---------------------------------------------------------------------------
# 2-6: 存在しないYAMLパス
# ---------------------------------------------------------------------------
class TestMissingFile:
    def test_nonexistent_path_raises(self):
        with pytest.raises(RuleSetValidationError):
            load_mapping_config("/nonexistent/path/missing.yml")
