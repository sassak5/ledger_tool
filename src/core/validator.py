"""バリデーション — NormalizedTransaction を検証し有効行とエラーに分離する

検証ルールはコードで固定。YAMLは「変換ルール」の唯一の真実。
"""

from __future__ import annotations

from src.core.models import NormalizedTransaction, ValidationError


def validate(
    transactions: list[NormalizedTransaction],
) -> tuple[list[NormalizedTransaction], list[ValidationError]]:
    """
    ドキュメント最終確認日: 2026-02-12

    validator.validate（検証）: 「正規化された取引が、必須項目や整合性ルールを
    満たしているかチェックして、通ったものだけ次へ進める」工程です。

    - 入力: NormalizedTransaction 群（すでに型・形式がある程度揃っている前提）
    - 出力: valid_txns（通過した取引） + エラー/警告（不備の指摘）
    - 例: 必須項目が空でないか、金額が負でないか、型/範囲/ルール違反がないか…など

    error レベル → 有効行リストから除外
    warn レベル → 有効行リストに残る
    """
    valid: list[NormalizedTransaction] = []
    errors: list[ValidationError] = []

    for txn in transactions:
        row_errors: list[ValidationError] = []
        has_error = False

        # --- 必須フィールド: date ---
        if not txn.date or not txn.date.strip():
            row_errors.append(ValidationError(
                row_id=txn.row_id, level="error", field="date",
                message="日付がnullです", raw_value=str(txn.date),
            ))
            has_error = True

        # --- 入出金整合 ---
        if txn.amount_out > 0 and txn.amount_in > 0:
            row_errors.append(ValidationError(
                row_id=txn.row_id, level="warn",
                field="amount_out, amount_in",
                message="支払と預りが同時に入っています（要確認）",
                raw_value=f"out={txn.amount_out}, in={txn.amount_in}",
            ))

        if txn.amount_out == 0 and txn.amount_in == 0:
            row_errors.append(ValidationError(
                row_id=txn.row_id, level="warn",
                field="amount_out, amount_in",
                message="金額が両方0です（要確認）",
                raw_value="out=0, in=0",
            ))

        errors.extend(row_errors)

        if not has_error:
            valid.append(txn)

    return valid, errors
