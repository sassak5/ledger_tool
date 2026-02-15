"""
ドキュメント最終更新: 2026-02-15

このモジュールは、パイプライン全体の中で「正規化された取引が、必須項目や整合性ルールを
満たしているかチェック」し、問題のある行を次工程（仕訳生成）へ渡さないための品質ゲート。

- 本モジュール（validator）は、必須フィールド（date等）の存在や、入出金の整合性をチェックし、
  通過した取引（valid_txns）と問題行（ValidationError）に分離する。
注意:
    検証ルールは現状コードで固定（必須項目・整合チェック程度）。
    YAMLの validations セクションは将来拡張の余地として定義されているが、まだ本格活用されていない。
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

    # TODO: validatorは必須日付・入出金の簡易整合くらいで、YAMLの validations をほぼ使っていません

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
