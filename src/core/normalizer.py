"""
ドキュメント最終更新: 2026-02-15

このモジュールは、パイプライン全体の中で「入力ソースごとにバラバラなレコード表現」を、
後段が共通に扱える `NormalizedTransaction` へ揃える役割を担う。(メイン関数はnormalize)

システム全体での立ち位置（上流→下流）:
    detector → parser → normalizer → validator → ledger_generator → exporter

- 上流（parser）は、CSV/TSV 等を読み取り `RawRecord`（fields が文字列中心）を生成する。
- 本モジュール（normalizer）は、日付パース・金額数値化・空白圧縮・入出金方向の統一などの
  「型変換/表現統一」をここで一元管理し、`NormalizedTransaction` を生成する。
- 下流（validator / ledger_generator）は、ソース依存の差を意識せずに検証や仕訳生成を行える。

GUI操作から見た役割:
    GUIの「変換（帳簿作成）」実行 → `src/core/pipeline.py` が処理を統括 →
    パース後に本モジュールが呼ばれ、仕訳確認タブに表示される候補（LedgerDraft）の“元データ”
    となる `NormalizedTransaction` を作る工程。

"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from src.core.models import (
    NormalizedTransaction,
    RawRecord,
    ValidationError,
)

# 日付パースで試行するフォーマット
_DATE_FORMATS = ["%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d"]

# source_kind → source_type のマッピング
_SOURCE_TYPE_MAP = {
    "bank_statement": "bank",
    "amazon_settlement_report": "amazon",
    "credit_card_statement": "creditcard",
}

# format_id → source_name のマッピング (簡易)
_SOURCE_NAME_MAP = {
    "mufj_table_v1": "mufj",
    "aichibank_table_v1": "aichi",
    "amazon_settlement_v1": "amazon_settlement",
}


def _parse_date(value: str) -> str | None:
    """日付文字列を YYYY-MM-DD に正規化。失敗時は None"""
    if not value or not value.strip():
        return None
    v = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(v, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_int(value: str) -> int | None:
    """金額文字列を整数に変換。空→0、カンマ・通貨記号除去。失敗時は None"""
    if not value or not value.strip():
        return 0
    v = value.strip()
    # 通貨記号除去
    v = v.replace("¥", "").replace("円", "")
    # カンマ除去
    v = v.replace(",", "")
    # 括弧負値 "(500)" → "-500"
    m = re.match(r"^\((.+)\)$", v)
    if m:
        v = "-" + m.group(1)
    try:
        return int(float(v))
    except (ValueError, OverflowError):
        return None


def _collapse_spaces(text: str) -> str:
    """全角・半角の空白を1つの半角スペースに圧縮"""
    return re.sub(r"[\s\u3000]+", " ", text).strip()


def normalize_bank(
    record: RawRecord,
    config: dict[str, Any],
) -> tuple[NormalizedTransaction | None, list[ValidationError]]:
    """銀行明細の RawRecord を NormalizedTransaction に変換"""
    errors: list[ValidationError] = []
    fields = record.fields
    source_name = _SOURCE_NAME_MAP.get(record.format_id, record.format_id)
    row_id = f"{source_name}_{record.row_number}"

    # 日付パース
    date_raw = fields.get("date", "")
    date = _parse_date(str(date_raw))
    if date is None:
        errors.append(ValidationError(
            row_id=row_id, level="error", field="date",
            message=f"日付が読めません: {date_raw}", raw_value=str(date_raw),
        ))
        return None, errors

    # 金額パース
    amount_out_raw = str(fields.get("amount_out", ""))
    amount_in_raw = str(fields.get("amount_in", ""))
    amount_out = _parse_int(amount_out_raw)
    amount_in = _parse_int(amount_in_raw)

    if amount_out is None:
        errors.append(ValidationError(
            row_id=row_id, level="error", field="amount_out",
            message=f"金額を数値化できません: {amount_out_raw}",
            raw_value=amount_out_raw,
        ))
        return None, errors
    if amount_in is None:
        errors.append(ValidationError(
            row_id=row_id, level="error", field="amount_in",
            message=f"金額を数値化できません: {amount_in_raw}",
            raw_value=amount_in_raw,
        ))
        return None, errors

    # 0以上を保証 (abs)
    amount_out = abs(amount_out)
    amount_in = abs(amount_in)

    # 摘要
    summary = _collapse_spaces(str(fields.get("summary", "")))
    detail_field = fields.get("summary_detail", fields.get("description", ""))
    details = _collapse_spaces(str(detail_field)) if detail_field else summary

    # 残高
    balance_raw = str(fields.get("balance", ""))
    balance = _parse_int(balance_raw) if balance_raw.strip() else None

    # メモ
    memo = str(fields.get("memo", "")).strip()

    # extra (テンプレ固有フィールド)
    extra: dict[str, Any] = {}
    for key in ("float_flag", "io_flag"):
        if key in fields:
            extra[key] = fields[key]

    txn = NormalizedTransaction(
        source_type="bank",
        source_name=source_name,
        row_id=row_id,
        date=date,
        summary=summary,
        details=details,
        amount_out=amount_out,
        amount_in=amount_in,
        balance=balance,
        memo=memo,
        extra=extra,
        raw=record.raw_line,
    )
    return txn, errors


def normalize_amazon(
    record: RawRecord,
    config: dict[str, Any],
) -> tuple[NormalizedTransaction | None, list[ValidationError]]:
    """Amazon決済レポートの RawRecord を NormalizedTransaction に変換"""
    errors: list[ValidationError] = []
    fields = record.fields
    row_id = f"amazon_settlement_{record.row_number}"

    # 日付
    date_raw = fields.get("date", "")
    date = _parse_date(str(date_raw))
    if date is None:
        errors.append(ValidationError(
            row_id=row_id, level="error", field="date",
            message=f"日付が読めません: {date_raw}", raw_value=str(date_raw),
        ))
        return None, errors

    # バケット名 → 摘要
    bucket_name = str(fields.get("bucket_name", ""))
    summary = bucket_name
    details = f"settlement: {fields.get('settlement_id', '')}"

    # 金額 (バケット集計済みの値)
    amount_raw = str(fields.get("amount", "0"))
    amount = _parse_int(amount_raw)
    if amount is None:
        errors.append(ValidationError(
            row_id=row_id, level="error", field="amount",
            message=f"金額を数値化できません: {amount_raw}",
            raw_value=amount_raw,
        ))
        return None, errors

    # 符号で入出金を判定
    if amount >= 0:
        amount_in = amount
        amount_out = 0
    else:
        amount_in = 0
        amount_out = abs(amount)

    # unmapped バケットは warn
    if bucket_name == "unmapped":
        unmapped_count = fields.get("unmapped_count", "0")
        errors.append(ValidationError(
            row_id=row_id, level="warn", field="unmapped_bucket",
            message=f"未知のamount_description ({unmapped_count}件, 合計: ¥{amount_raw})",
            raw_value=amount_raw,
        ))

    extra: dict[str, Any] = {
        "settlement_id": fields.get("settlement_id", ""),
        "bucket_name": bucket_name,
    }

    # total-amount 突合 (ここでは記録のみ、validator でチェック可能)
    total_amount_raw = fields.get("total_amount", "")
    if total_amount_raw:
        extra["total_amount"] = total_amount_raw

    txn = NormalizedTransaction(
        source_type="amazon",
        source_name="amazon_settlement",
        row_id=row_id,
        date=date,
        summary=summary,
        details=details,
        amount_out=amount_out,
        amount_in=amount_in,
        balance=None,
        memo="",
        extra=extra,
        raw=record.raw_line,
    )
    return txn, errors


def normalize(
    records: list[RawRecord],
    config: dict[str, Any],
) -> tuple[list[NormalizedTransaction], list[ValidationError]]:
    """
    ドキュメント最終確認日: 2026-02-12
    
    normalizer.normalize（正規化）: 
    「入力レコードの形・表現を揃えて、後段が扱える共通フォーマットに変換」する工程です。

    - 入力: RawRecord 群（パーサが吐いたままの値。日付が文字列だったり、金額が 1,234 みたいな表記だったり）
    - 出力: NormalizedTransaction 群 + 正規化中に見つかったエラー/警告
    - 例: 日付文字列→YYYY-MM-DD に統一、金額のカンマ除去して数値化、入金/出金の向きを amount_in/amount_out に振り分け…など

    source_kind に応じて変換ロジックを分岐する。
    """
    transactions: list[NormalizedTransaction] = []
    all_errors: list[ValidationError] = []

    for record in records:
        if record.source_kind == "bank_statement":
            txn, errs = normalize_bank(record, config)
        elif record.source_kind == "amazon_settlement_report":
            txn, errs = normalize_amazon(record, config)
        else:
            source_name = record.format_id
            row_id = f"{source_name}_{record.row_number}"
            errs = [ValidationError(
                row_id=row_id, level="error", field="source_kind",
                message=f"未対応の source_kind: {record.source_kind}",
                raw_value=record.source_kind,
            )]
            txn = None

        all_errors.extend(errs)
        if txn is not None:
            transactions.append(txn)

    return transactions, all_errors
