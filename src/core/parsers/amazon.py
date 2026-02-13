"""Amazon決済レポートパーサ — TSVをパースし settlement-id 単位でグルーピング・バケット集計"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from typing import Any

from src.core.base_parser import BaseParser
from src.core.models import RawRecord, ValidationError


def _parse_amount(value: str) -> float:
    """金額文字列を float に変換 (パーサ内での集計用)"""
    if not value or not value.strip():
        return 0.0
    cleaned = value.strip().replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _normalize_amount(value: float, mode: str) -> float:
    """normalize モード (RAW/ABS/NEGATE) に応じて金額を変換"""
    if mode == "ABS":
        return abs(value)
    elif mode == "NEGATE":
        return -value
    return value  # RAW


class AmazonParser(BaseParser):
    """
    ドキュメント最終確認日: 2026-02-13

    Amazon決済レポート (TSV) パーサ

    - 工程0: 設定の読み出し（config を解釈）
    - 工程1: TSV読み込み・行解析
    - 工程2: 必須列チェック（ヘッダ検証）なければ空リスト返却
    - 工程3: settlement-id ごとに行をグループ化
    - 工程4: 各 settlement-id グループのヘッダ情報を拾う
    - 工程5: 各行をバケット定義に照らして集計
    - 工程6: 各バケットごとに RawRecord を生成して返す
    - 工程7: records を返す
    """

    def parse(self, file_path: str, config: dict) -> list[RawRecord]:
        encoding = config.get("_encoding", "utf-8")
        key_cfg = config.get("key", {})
        settlement_id_col = key_cfg.get("settlement_id", "settlement-id")
        deposit_date_col = key_cfg.get("deposit_date", "deposit-date")
        total_amount_col = key_cfg.get("total_amount", "total-amount")
        buckets_cfg: dict[str, Any] = config.get("summary_buckets", {})
        ledger_defaults: dict[str, str] = config.get("ledger_defaults", {})
        validations_cfg = config.get("validations", {})
        required_fields: list[str] = validations_cfg.get("require_fields_in_row", [])

        with open(file_path, encoding=encoding, newline="") as f:
            text = f.read()

        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        if not reader.fieldnames:
            return []

        # 必須列チェック
        header_set = set(reader.fieldnames)
        for req in required_fields:
            if req not in header_set:
                return []

        # settlement-id ごとにグループ化
        groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        all_rows: list[dict[str, str]] = []
        for row in reader:
            sid = row.get(settlement_id_col, "").strip()
            if sid:
                groups[sid].append(row)
            all_rows.append(row)

        records: list[RawRecord] = []
        row_counter = 0

        for sid, group_rows in groups.items():
            # ヘッダ行からtotal-amount, deposit-dateを取得 (最初の行にある想定)
            deposit_date = ""
            total_amount_str = ""
            for r in group_rows:
                dd = r.get(deposit_date_col, "").strip()
                ta = r.get(total_amount_col, "").strip()
                if dd:
                    deposit_date = dd
                if ta:
                    total_amount_str = ta

            # バケット集計
            bucket_totals: dict[str, float] = {}
            unmapped_rows: list[dict[str, str]] = []

            for r in group_rows:
                a_type = r.get("amount-type", "").strip()
                a_desc = r.get("amount-description", "").strip()
                amount = _parse_amount(r.get("amount", ""))

                if not a_type and not a_desc:
                    continue

                matched = False
                for bucket_name, bucket_def in buckets_cfg.items():
                    # include マッチ
                    includes = bucket_def.get("include", [])
                    for inc in includes:
                        if (inc.get("amount_type") == a_type
                                and inc.get("amount_description") == a_desc):
                            norm_mode = bucket_def.get("normalize", "RAW")
                            normed = _normalize_amount(amount, norm_mode)
                            bucket_totals[bucket_name] = (
                                bucket_totals.get(bucket_name, 0.0) + normed
                            )
                            matched = True
                            break

                    # formula マッチ
                    formula = bucket_def.get("formula")
                    if formula and not matched:
                        norm_mode = bucket_def.get("normalize", "RAW")
                        for add_item in formula.get("add", []):
                            if (add_item.get("amount_type") == a_type
                                    and add_item.get("amount_description") == a_desc):
                                normed = _normalize_amount(amount, norm_mode)
                                bucket_totals[bucket_name] = (
                                    bucket_totals.get(bucket_name, 0.0) + normed
                                )
                                matched = True
                                break
                        for sub_item in formula.get("subtract", []):
                            if (sub_item.get("amount_type") == a_type
                                    and sub_item.get("amount_description") == a_desc):
                                normed = _normalize_amount(amount, norm_mode)
                                bucket_totals[bucket_name] = (
                                    bucket_totals.get(bucket_name, 0.0) - normed
                                )
                                matched = True
                                break

                    if matched:
                        break

                if not matched and (a_type or a_desc):
                    unmapped_rows.append(r)

            # 各バケットを RawRecord として返す
            for bucket_name, total in bucket_totals.items():
                row_counter += 1
                amount_int = int(round(total))

                fields: dict[str, Any] = {
                    "date": deposit_date,
                    "settlement_id": sid,
                    "bucket_name": bucket_name,
                    "amount": str(amount_int),
                    "total_amount": total_amount_str,
                }

                records.append(
                    RawRecord(
                        source_kind="amazon_settlement_report",
                        format_id="amazon_settlement_v1",
                        row_number=row_counter,
                        fields=fields,
                        raw_line={"settlement_id": sid, "bucket": bucket_name},
                    )
                )

            # unmapped バケット (集約)
            if unmapped_rows:
                row_counter += 1
                unmapped_total = sum(
                    _parse_amount(r.get("amount", "")) for r in unmapped_rows
                )
                fields = {
                    "date": deposit_date,
                    "settlement_id": sid,
                    "bucket_name": "unmapped",
                    "amount": str(int(round(unmapped_total))),
                    "unmapped_count": str(len(unmapped_rows)),
                    "total_amount": total_amount_str,
                }
                records.append(
                    RawRecord(
                        source_kind="amazon_settlement_report",
                        format_id="amazon_settlement_v1",
                        row_number=row_counter,
                        fields=fields,
                        raw_line={"settlement_id": sid, "bucket": "unmapped"},
                    )
                )

        return records
