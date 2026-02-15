"""
ドキュメント最終更新: 2026-02-15

このモジュールは、GUIでユーザーが選ぶ入力ファイルが「銀行CSV」「Amazon精算TSV」など複数形式に
渡るので、まずフォーマットを検出してから適切なパーサやルールを適用するための「フォーマット検出器」です。

具体的には以下を決定する。
- 適用すべきルールYAML（列名ゆれの吸収定義など）
- 使うべきパーサ（RawRecord 生成ロジック）

また、実務上は同じCSV/TSVでも文字コード（UTF-8 / CP932 等）が混在しやすく、
文字化けしたままヘッダ解釈やテンプレマッチを行うと誤判定・誤パースにつながる。
そのため本モジュールは、まずエンコーディングを推定して正しくデコードし、
先頭行（ヘッダ）の列名を元にテンプレートマッチングを行っている。

システム全体での立ち位置:
    GUIの「変換（帳簿作成）」実行 → pipeline.run → detector.detect → DetectionResult
    → registry.get(source_kind) でパーサ解決 → parse/normalize… と後段へ渡す。
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from src.core.models import (
    DetectionResult,
    EncodingDetectionError,
    FormatNotMatchedError,
)
# TODO: ヘッダ列名のマッチ数でフォーマット判定するので、列名や表記ゆれがあると別YAMLが当たる可能性があります

# Amazon TSV の必須列 (これがあれば Amazon と判定)
_AMAZON_REQUIRED_COLUMNS = {"settlement-id", "amount-type", "amount-description", "amount"}


def _try_decode(raw_bytes: bytes, encodings: list[str]) -> tuple[str, str]:
    """バイト列を指定エンコーディング順で試行し、(デコード文字列, エンコーディング名) を返す"""
    for enc in encodings:
        try:
            text = raw_bytes.decode(enc)
            return text, enc
        except (UnicodeDecodeError, LookupError):
            continue
    raise EncodingDetectionError(
        f"全エンコーディング試行が失敗しました (試行: {encodings})"
    )


def _read_header_line(text: str) -> list[str]:
    """テキストの先頭行をCSV/TSVパースしてヘッダ列名リストを返す"""
    first_line = text.split("\n", 1)[0].strip()
    if not first_line:
        return []

    # タブ区切り判定
    if "\t" in first_line:
        reader = csv.reader(io.StringIO(first_line), delimiter="\t")
    else:
        reader = csv.reader(io.StringIO(first_line))

    for row in reader:
        return [cell.strip() for cell in row if cell.strip()]
    return []


def _match_bank_format(
    header_columns: list[str],
    config: dict[str, Any],
) -> int:
    """銀行フォーマットYAMLの header_aliases とヘッダ列名を包含一致で判定。

    Returns:
        マッチした正規列名の数。0 = マッチしない
    """
    aliases: dict[str, list[str]] = config.get("header_aliases", {})

    required_canonical = {"date"}
    amount_keys = {"amount_out", "amount_in"}

    matched_canonical: set[str] = set()
    header_set = set(header_columns)

    for canonical_name, alias_list in aliases.items():
        for alias in alias_list:
            if alias in header_set:
                matched_canonical.add(canonical_name)
                break

    # date が必ずマッチしていること
    if not required_canonical.issubset(matched_canonical):
        return 0

    # amount_out または amount_in の少なくとも片方がマッチ
    if not matched_canonical & amount_keys:
        return 0

    return len(matched_canonical)


def _match_amazon_format(header_columns: list[str]) -> bool:
    """Amazon TSVの必須列が全て存在するか判定"""
    header_set = set(header_columns)
    return _AMAZON_REQUIRED_COLUMNS.issubset(header_set)


def detect(file_path: str, rule_configs: list[dict[str, Any]]) -> DetectionResult:
    """
    ドキュメント最終確認日: 2026-02-11
    
    GUIで読み込んだファイルのフォーマットを検出する。
    空チェックやエンコーディングを順に試行してデコードを行い、
    ヘッダ列名を抽出してテンプレートマッチングを実施する。(Amazon / 銀行明細)

    Args:
        file_path: 入力ファイルのパス
        rule_configs: ruleset loader で読み込んだYAML設定リスト（各dictは `_config_path` を含み得る）

    Returns:
        DetectionResult: format_id / source_kind / encoding / config_path

    """
    path = Path(file_path)
    if not path.exists():
        raise FormatNotMatchedError(f"ファイルが見つかりません: {file_path}")

    raw_bytes = path.read_bytes()
    if not raw_bytes:
        raise FormatNotMatchedError(f"空ファイルです: {file_path}")

    # エンコーディング検出 (UTF-8 → cp932 → shift_jis)
    text, encoding = _try_decode(raw_bytes, ["utf-8", "cp932", "shift_jis"])

    # ヘッダ行取得
    header_columns = _read_header_line(text)
    if not header_columns:
        raise FormatNotMatchedError(
            f"ヘッダ行が取得できません: {file_path}"
        )

    # Amazon判定 (必須列の存在チェック)
    for config in rule_configs:
        if config.get("source") == "amazon_settlement_report":
            if _match_amazon_format(header_columns):
                return DetectionResult(
                    format_id="amazon_settlement_v1",
                    source_kind="amazon_settlement_report",
                    encoding=encoding,
                    config_path=config.get("_config_path", ""),
                )

    # 銀行フォーマット判定 (header_aliases 包含一致、最多マッチ優先)
    best_match: tuple[int, dict[str, Any] | None] = (0, None)
    for config in rule_configs:
        if config.get("source_kind") == "bank_statement":
            score = _match_bank_format(header_columns, config)
            if score > best_match[0]:
                best_match = (score, config)

    if best_match[1] is not None:
        config = best_match[1]
        return DetectionResult(
            format_id=config["format_id"],
            source_kind="bank_statement",
            encoding=encoding,
            config_path=config.get("_config_path", ""),
        )

    raise FormatNotMatchedError(
        f"フォーマットを判定できません (ヘッダ: {header_columns})"
    )
