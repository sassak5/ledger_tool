"""パイプライン統括（検出 → パース → 正規化 → バリデーション → 仕訳生成 → 出力）

このモジュールは、入力ファイル群を会計処理向けのデータに変換し、仕訳候補と各種出力を生成する
一連の処理を `run()` で統括する。

処理フロー（モジュール / 役割）:

1. ルール読み込みフロー: loader.py 検出・パース等に必要なルール設定をロードする。

2. 入力ファイル検出フロー: `src/core/detector.py`
    - `detect(file_path, rule_configs)` で、ファイルの種類（source_kind）/ フォーマット（format_id）/
      適用する設定（config_path）/ 文字コード（encoding）を推定する。
    - 検出不能な場合は `DetectionError` を `ValidationError`（level=error）として集約する。

3. パース（レコード化）フロー: `src/core/registry.py` + `src/core/parsers/*`
    - `src/core/parsers` を import することで、各パーサがレジストリに登録される（副作用）。
    - `registry.get(source_kind)` で該当パーサを取得し、`parse(file_path, config)` を実行して
      `RawRecord` のリストを生成する。
    - パースで例外が起きた場合は `ValidationError`（level=error, message=パース失敗）として集約する。

4. 正規化フロー: `src/core/normalizer.py`
    - `normalize(raw_records, context)` で `RawRecord` を `NormalizedTransaction` に変換し、
      値の整形・統一（例: 日付/金額/入出金方向など）を行う。
    - 正規化時のエラー/警告は `ValidationError` として返却され、全体エラーに合算する。

5. バリデーションフロー: `src/core/validator.py`
    - `validate(transactions)` で、必須項目や整合性（型・範囲・ルール違反など）を検証する。
    - 検証に通った取引（valid_txns）と、エラー/警告（ValidationError）に分離する。

6. 仕訳生成フロー: `src/core/ledger_generator.py`
    - `generate(valid_txns)` で、取引から `LedgerDraft`（仕訳候補）を生成する。
    - 生成時のエラー/警告は `ValidationError` として集約する。

7. サマリ集計フロー: `src/core/models.py`（ProcessingSummary / SourceFileInfo 等）
    - 全エラー（error/warn）を集計し、期間（period_start/end）や件数、入出金合計などをまとめる。
    - ファイル別のエラー/警告件数を再集計し、`ProcessingSummary` に格納する。

8. 出力フロー: `src/core/exporter.py`
    - `export_all(output_base_dir, transactions, drafts, errors, summary)` で、
      取引・仕訳候補・エラー・サマリを所定ディレクトリへ出力する。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core import detector, normalizer, validator
from src.core import ledger_generator, exporter
import src.core.parsers  # noqa: F401 — パーサをレジストリに登録
from src.core.models import (
    DetectionError,
    DetectionResult,
     PipelineResult,
    ProcessingSummary,
    RawRecord,
    SourceFileInfo,
    ValidationError,
)
from src.core.registry import registry
from src.core.ruleset import loader

logger = logging.getLogger(__name__)


def run(
    file_paths: list[str],
    rules_dir: str,
    output_base_dir: str,
) -> PipelineResult:
    """パイプライン全体を実行する。

    Args:
        file_paths: GUIで選択したファイルパスのリスト
        rules_dir: rules/ ディレクトリのパス
        output_base_dir: 出力先ベースディレクトリ (outputs/)

    Returns:
        PipelineResult (summary, drafts, errors, transactions)
    """
    run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_errors: list[ValidationError] = []
    all_raw_records: list[RawRecord] = []
    source_files: list[SourceFileInfo] = []

    # --- Step 0: ルール読み込み ---
    rule_configs = loader.load_all_rules(rules_dir)

    # --- Step 1 & 2: ファイルごとに検出 → パース ---
    for fpath in file_paths:
        file_records: list[RawRecord] = []

        # 検出
        try:
            result: DetectionResult = detector.detect(fpath, rule_configs)
        except DetectionError as e:
            all_errors.append(ValidationError(
                row_id=fpath, level="error", field="",
                message=str(e), raw_value=fpath,
            ))
            source_files.append(SourceFileInfo(
                path=fpath, format_id="unknown", source_kind="unknown",
                row_count=0, error_count=1, warn_count=0,
            ))
            continue

        # パーサ取得 & 実行
        try:
            parser_instance = registry.get(result.source_kind)
            config = loader.load_yaml(result.config_path)
            config["_encoding"] = result.encoding
            config["_config_path"] = result.config_path
            file_records = parser_instance.parse(fpath, config)
        except Exception as e:
            all_errors.append(ValidationError(
                row_id=fpath, level="error", field="",
                message=f"パース失敗: {e}", raw_value=fpath,
            ))
            source_files.append(SourceFileInfo(
                path=fpath, format_id=result.format_id,
                source_kind=result.source_kind,
                row_count=0, error_count=1, warn_count=0,
            ))
            continue

        all_raw_records.extend(file_records)# 

        # ファイル単位のエラー集計 (正規化後に更新)
        source_files.append(SourceFileInfo(
            path=fpath,
            format_id=result.format_id,
            source_kind=result.source_kind,
            row_count=len(file_records),
            error_count=0,
            warn_count=0,
        ))

    # --- Step 3: 正規化 ---
    transactions, norm_errors = normalizer.normalize(all_raw_records, {})
    all_errors.extend(norm_errors)

    # --- Step 4: バリデーション ---
    valid_txns, val_errors = validator.validate(transactions)
    all_errors.extend(val_errors)

    # --- Step 5: 仕訳候補生成 ---
    drafts, ledger_errors = ledger_generator.generate(valid_txns)
    all_errors.extend(ledger_errors)

    # --- サマリ集計 ---
    error_count = sum(1 for e in all_errors if e.level == "error")
    warn_count = sum(1 for e in all_errors if e.level == "warn")

    # ファイル別エラー/警告を再集計
    for sf in source_files:
        sf.error_count = sum(
            1 for e in all_errors
            if e.level == "error" and (sf.path in e.row_id or sf.format_id in e.row_id)
        )
        sf.warn_count = sum(
            1 for e in all_errors
            if e.level == "warn" and (sf.path in e.row_id or sf.format_id in e.row_id)
        )

    dates = [t.date for t in valid_txns if t.date]
    period_start = min(dates) if dates else ""
    period_end = max(dates) if dates else ""

    summary = ProcessingSummary(
        period_start=period_start,
        period_end=period_end,
        total_count=len(valid_txns),
        total_in=sum(t.amount_in for t in valid_txns),
        total_out=sum(t.amount_out for t in valid_txns),
        ledger_count=len(drafts),
        error_count=error_count,
        warn_count=warn_count,
        source_files=source_files,
        run_at=run_at,
    )

    # --- Step 6: 出力 ---
    try:
        out_dir = exporter.export_all(
            output_base_dir, transactions, drafts, all_errors, summary,
        )
        logger.info(f"出力完了: {out_dir}")
    except Exception as e:
        logger.error(f"出力失敗: {e}")
        raise

    return PipelineResult(
        summary=summary,
        drafts=drafts,
        errors=all_errors,
        transactions=transactions,
    )
