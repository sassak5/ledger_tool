"""E2Eテスト — GUI操作

CustomTkinter のウィンドウを直接開くとCI環境で失敗するため、
ここでは pipeline_run の呼び出しとGUIの「入力→出力」の整合性を
ヘッドレスに検証する。

実際のGUI描画テスト (9-1 のウィジェット確認) は手動テスト想定。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import FIXTURES_DIR, RULES_DIR


# ---------------------------------------------------------------------------
# 9-1: ファイル選択→変換→結果取得 (pipeline経由で疑似確認)
# ---------------------------------------------------------------------------
class TestFileSelectConvert:
    def test_pipeline_called_with_correct_args(self, tmp_path: Path):
        """GUIの変換ボタン押下相当: pipeline_run が正しい引数で呼ばれ結果が返る"""
        from src.core.pipeline import run as pipeline_run

        result = pipeline_run(
            file_paths=[str(FIXTURES_DIR / "mufj_sample.csv")],
            rules_dir=str(RULES_DIR),
            output_base_dir=str(tmp_path),
        )
        # GUI表示に必要なデータが揃っている
        assert result.summary is not None
        assert result.drafts is not None
        assert result.errors is not None
        assert result.transactions is not None

        # サマリタブ用データ
        assert result.summary.total_count >= 1
        assert result.summary.run_at != ""

        # 仕訳確認タブ用データ
        assert len(result.drafts) >= 1
        for d in result.drafts:
            assert d.date != ""
            assert d.debit_account != ""
            assert d.credit_account != ""


# ---------------------------------------------------------------------------
# 9-2: エラーファイル→エラー/警告タブ相当のデータ
# ---------------------------------------------------------------------------
class TestErrorDisplay:
    def test_error_file_produces_errors(self, tmp_path: Path):
        """不正CSVを投入→エラーが集約される（GUIエラータブ表示用）"""
        from src.core.pipeline import run as pipeline_run

        result = pipeline_run(
            file_paths=[str(FIXTURES_DIR / "random.csv")],
            rules_dir=str(RULES_DIR),
            output_base_dir=str(tmp_path),
        )
        assert result.summary.error_count >= 1
        error_msgs = [e for e in result.errors if e.level == "error"]
        assert len(error_msgs) >= 1


# ---------------------------------------------------------------------------
# 9-3: 出力フォルダ存在確認 (変換後)
# ---------------------------------------------------------------------------
class TestOutputFolder:
    def test_output_dir_created(self, tmp_path: Path):
        """変換後に出力フォルダが作成されている"""
        from src.core.pipeline import run as pipeline_run

        pipeline_run(
            file_paths=[str(FIXTURES_DIR / "mufj_sample.csv")],
            rules_dir=str(RULES_DIR),
            output_base_dir=str(tmp_path),
        )
        subdirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(subdirs) >= 1
        # 5ファイル存在
        out_dir = subdirs[0]
        assert len(list(out_dir.iterdir())) == 5


# ---------------------------------------------------------------------------
# 9-4: ファイル未選択で変換 (空リスト)
# ---------------------------------------------------------------------------
class TestNoFileSelected:
    def test_empty_file_list(self, tmp_path: Path):
        """ファイル未選択 → 0件処理、クラッシュしない"""
        from src.core.pipeline import run as pipeline_run

        result = pipeline_run(
            file_paths=[],
            rules_dir=str(RULES_DIR),
            output_base_dir=str(tmp_path),
        )
        assert result.summary.total_count == 0
        assert result.summary.ledger_count == 0
