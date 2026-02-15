"""結合テスト — pipeline end-to-end"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.core.pipeline import run as pipeline_run
from src.core.models import PipelineResult, RuleSetValidationError, FormatNotMatchedError
from tests.conftest import FIXTURES_DIR, RULES_DIR


# ---------------------------------------------------------------------------
# 8-1: 銀行CSV → 仕訳 end-to-end
# ---------------------------------------------------------------------------
class TestBankEndToEnd:
    def test_mufj_pipeline(self, tmp_path: Path):
        result = pipeline_run(
            file_paths=[str(FIXTURES_DIR / "mufj_sample.csv")],
            rules_dir=str(RULES_DIR),
            output_base_dir=str(tmp_path),
        )
        assert isinstance(result, PipelineResult)
        assert result.summary.total_count >= 1
        assert result.summary.ledger_count >= 1
        assert len(result.drafts) >= 1

        # 具体的な仕訳確認: 振込手数料→支払手数料
        fee_drafts = [d for d in result.drafts if d.debit_account == "支払手数料"]
        assert len(fee_drafts) >= 1


# ---------------------------------------------------------------------------
# 8-2: Amazon TSV → 仕訳 end-to-end
# ---------------------------------------------------------------------------
class TestAmazonEndToEnd:
    def test_amazon_pipeline(self, tmp_path: Path):
        result = pipeline_run(
            file_paths=[str(FIXTURES_DIR / "amazon_sample.tsv")],
            rules_dir=str(RULES_DIR),
            output_base_dir=str(tmp_path),
        )
        assert isinstance(result, PipelineResult)
        assert result.summary.total_count >= 1
        assert len(result.drafts) >= 1

        # Amazon 仕訳に partner が設定されている
        for d in result.drafts:
            assert d.partner == "Amazon.co.jp"


# ---------------------------------------------------------------------------
# 8-3: 混在入力 (銀行 + Amazon)
# ---------------------------------------------------------------------------
class TestMixedInput:
    def test_bank_and_amazon_together(self, tmp_path: Path):
        result = pipeline_run(
            file_paths=[
                str(FIXTURES_DIR / "mufj_sample.csv"),
                str(FIXTURES_DIR / "amazon_sample.tsv"),
            ],
            rules_dir=str(RULES_DIR),
            output_base_dir=str(tmp_path),
        )
        assert isinstance(result, PipelineResult)
        # 両方のソースから仕訳が生成されている
        source_types = set()
        for t in result.transactions:
            source_types.add(t.source_type)
        assert "bank" in source_types
        assert "amazon" in source_types


# ---------------------------------------------------------------------------
# 8-4: エンコーディング揺れ (CP932)
# ---------------------------------------------------------------------------
class TestEncodingVariation:
    def test_cp932_bank_processes(self, tmp_path: Path):
        result = pipeline_run(
            file_paths=[str(FIXTURES_DIR / "mufj_cp932.csv")],
            rules_dir=str(RULES_DIR),
            output_base_dir=str(tmp_path),
        )
        assert isinstance(result, PipelineResult)
        assert result.summary.total_count >= 1


# ---------------------------------------------------------------------------
# 8-5: 空ファイル入力 → error, クラッシュしない
# ---------------------------------------------------------------------------
class TestEmptyFileInput:
    def test_empty_file_no_crash(self, tmp_path: Path):
        result = pipeline_run(
            file_paths=[str(FIXTURES_DIR / "empty.csv")],
            rules_dir=str(RULES_DIR),
            output_base_dir=str(tmp_path),
        )
        assert isinstance(result, PipelineResult)
        assert result.summary.error_count >= 1


# ---------------------------------------------------------------------------
# 8-6: 不正フォーマット入力 → error 集約
# ---------------------------------------------------------------------------
class TestInvalidFormatInput:
    def test_random_csv_error_collected(self, tmp_path: Path):
        result = pipeline_run(
            file_paths=[str(FIXTURES_DIR / "random.csv")],
            rules_dir=str(RULES_DIR),
            output_base_dir=str(tmp_path),
        )
        assert isinstance(result, PipelineResult)
        assert result.summary.error_count >= 1
        assert result.summary.ledger_count == 0


# ---------------------------------------------------------------------------
# 8-7: 出力ファイル生成確認
# ---------------------------------------------------------------------------
class TestOutputFiles:
    def test_all_output_files_exist(self, tmp_path: Path):
        result = pipeline_run(
            file_paths=[str(FIXTURES_DIR / "mufj_sample.csv")],
            rules_dir=str(RULES_DIR),
            output_base_dir=str(tmp_path),
        )
        # outputs/<timestamp>/ 配下を探す
        subdirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(subdirs) == 1

        out_dir = subdirs[0]
        expected_files = [
            "normalized_transactions.csv",
            "ledger_draft.csv",
            "error_report.csv",
            "smart_import.csv",
            "run_log.txt",
        ]
        for fname in expected_files:
            fpath = out_dir / fname
            assert fpath.exists(), f"{fname} が存在しません"

        # smart_import.csv が UTF-8 で読めてヘッダがある
        with open(out_dir / "smart_import.csv", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            assert "取引日" in header


# ---------------------------------------------------------------------------
# 8-8: ledger_mapping.yml 欠損
# ---------------------------------------------------------------------------
class TestMissingLedgerMapping:
    def test_missing_mapping_raises(self, tmp_path: Path):
        # rules_dir に ledger_mapping.yml が無い → エラー
        empty_rules = tmp_path / "rules_empty"
        empty_rules.mkdir()

        # 銀行YAML だけコピー (detect は通るように)
        import shutil
        shutil.copy(RULES_DIR / "bank_format_mufj.yml", empty_rules / "bank_format_mufj.yml")

        with pytest.raises(RuleSetValidationError):
            pipeline_run(
                file_paths=[str(FIXTURES_DIR / "mufj_sample.csv")],
                rules_dir=str(empty_rules),
                output_base_dir=str(tmp_path / "out"),
            )
