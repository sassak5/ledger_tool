"""銀行明細パーサ — YAML駆動でCSVをパースし RawRecord を返す (型変換はしない)"""

from __future__ import annotations

import csv
import io
from typing import Any

from src.core.base_parser import BaseParser
from src.core.models import RawRecord, ValidationError


def _build_column_map(
    header_row: list[str],
    header_aliases: dict[str, list[str]],
) -> dict[str, str]:
    """
    ドキュメント最終確認日: 2026-02-13

    CSVのヘッダ行にある「実際の列名」を、
    内部で使う「正規列名（canonical）」へ
    対応付ける辞書を作る。

    例:

    入力:
    - header_row:["取引日", "摘要", "支払金額","預り金額", "残高"]
    - header_aliases:
      正規列名ごとの別名候補
      （YAML 由来を想定）

    出力:
    - { 実際の列名(alias):
        正規列名(canonical) }

    趣旨としては「列名ゆれ吸収」
    """
    col_map: dict[str, str] = {}
    for canonical, aliases in header_aliases.items():
        for alias in aliases:
            if alias in header_row:
                col_map[alias] = canonical
                break
    return col_map


def _is_skip_row(row_values: list[str]) -> bool:
    """空行・合計行などスキップすべき行かを判定する"""
    # 全セルが空
    if all(v.strip() == "" for v in row_values):
        return True
    # 先頭セルが「合計」を含む
    first = row_values[0].strip() if row_values else ""
    if "合計" in first:
        return True
    return False


class BankParser(BaseParser):
    """
    ドキュメント最終確認日: 2026-02-13

    銀行明細CSVパーサ
    - 工程0: 設定の読み出し（config を解釈）
    - 工程1: CSV読み込み・行解析
    - 工程2: ヘッダ行検出・列名マッピング
    - 工程3: “列名マッピング” を作る（ここが要点）
    - 工程4: 各行を RawRecord に変換して返す
    - 工程5: recordsにRawRecordを追加して返す
    """

    def parse(self, file_path: str, config: dict) -> list[RawRecord]:
        encoding = config.get("_encoding", "utf-8")
        header_aliases: dict[str, list[str]] = config.get("header_aliases", {})
        format_id: str = config.get("format_id", "unknown")
        source_kind: str = config.get("source_kind", "bank_statement")
        table_cfg = config.get("table", {})
        trim_ws: bool = table_cfg.get("trim_whitespace", True)

        with open(file_path, encoding=encoding, newline="") as f:
            text = f.read()

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)

        if not rows:
            return []

        # ヘッダ行 (1始まり → index 0)
        header_row_idx = table_cfg.get("header_row", 1) - 1
        if header_row_idx >= len(rows):
            return []

        header_row = rows[header_row_idx]
        if trim_ws:
            header_row = [h.strip() for h in header_row]

        # 列名マッピング
        col_map = _build_column_map(header_row, header_aliases)

        records: list[RawRecord] = []

        for i, row in enumerate(rows[header_row_idx + 1 :], start=header_row_idx + 2):
            if trim_ws:
                row = [cell.strip() for cell in row]

            if _is_skip_row(row):
                continue

            # 元の列名 → 値の辞書
            raw_line: dict[str, str] = {}
            for idx, val in enumerate(row):
                if idx < len(header_row):
                    raw_line[header_row[idx]] = val

            # 正規列名 → 値の辞書
            fields: dict[str, Any] = {}
            for original_col, canonical_name in col_map.items():
                fields[canonical_name] = raw_line.get(original_col, "")

            records.append(
                RawRecord(
                    source_kind=source_kind,
                    format_id=format_id,
                    row_number=i,
                    fields=fields,
                    raw_line=raw_line,
                )
            )

        return records
