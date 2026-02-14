"""仕訳候補生成 — NormalizedTransaction から LedgerDraft を生成する"""

from __future__ import annotations

from typing import Any

from src.core.models import (
    LedgerDraft,
    NormalizedTransaction,
    ValidationError,
)

# --- 科目推定キーワード (MVPはハードコード) ---
# 摘要に含まれるキーワード → 借方科目
_EXPENSE_KEYWORDS: list[tuple[str, str]] = [
    ("振込手数料", "支払手数料"),
    ("手数料", "支払手数料"),
    ("利息", "支払利息"),
    ("家賃", "地代家賃"),
    ("水道", "水道光熱費"),
    ("電気", "水道光熱費"),
    ("ガス", "水道光熱費"),
    ("通信", "通信費"),
    ("保険", "保険料"),
]

# Amazon バケット名 → (借方科目, 貸方科目) のデフォルト
_AMAZON_BUCKET_ACCOUNTS: dict[str, tuple[str, str]] = {
    "商品代金": ("売掛金", "売上高"),
    "配送料": ("売掛金", "売上高"),
    "税金": ("売掛金", "仮受消費税"),
    "Amazon手数料": ("支払手数料", "売掛金"),
    "FBA手数料_マイナス": ("支払手数料", "売掛金"),
    "FBA手数料_プラス": ("売掛金", "支払手数料"),
    "プロモーション割引額": ("売上値引", "売掛金"),
}


def _guess_expense_account(summary: str, details: str) -> str | None:
    """摘要テキストからキーワードマッチで経費科目を推定"""
    text = f"{summary} {details}"
    for keyword, account in _EXPENSE_KEYWORDS:
        if keyword in text:
            return account
    return None


def _generate_bank_ledger(
    txn: NormalizedTransaction,
) -> tuple[LedgerDraft | None, list[ValidationError]]:
    """銀行トランザクションの仕訳生成"""
    errors: list[ValidationError] = []

    if txn.amount_out == 0 and txn.amount_in == 0:
        errors.append(ValidationError(
            row_id=txn.row_id, level="warn",
            field="amount", message="金額が両方0です。仕訳をスキップします",
            raw_value="out=0, in=0",
        ))
        return None, errors

    description = f"{txn.summary} {txn.details}".strip()
    if len(description) > 100:
        description = description[:100]

    tags = ["bank"]

    if txn.amount_in > 0:
        # 入金: 借方=普通預金 / 貸方=売上高(仮)
        debit_account = "普通預金"
        credit_account = "売上高"
        amount = txn.amount_in
    else:
        # 出金: 借方=経費科目 / 貸方=普通預金
        guessed = _guess_expense_account(txn.summary, txn.details)
        if guessed:
            debit_account = guessed
        else:
            debit_account = "未分類"
            errors.append(ValidationError(
                row_id=txn.row_id, level="warn",
                field="debit_account",
                message="科目を推定できません。デフォルト科目 '未分類' を仮割当て",
                raw_value=description,
            ))
        credit_account = "普通預金"
        amount = txn.amount_out

    # 摘要に手数料系キーワードがあればタグ追加
    if "手数料" in description:
        tags.append("fee")
    if "振替" in description:
        tags.append("transfer")

    draft = LedgerDraft(
        date=txn.date,
        debit_account=debit_account,
        debit_amount=amount,
        credit_account=credit_account,
        credit_amount=amount,
        description=description,
        partner="",
        source_row_id=txn.row_id,
        tags=tags,
    )
    return draft, errors


def _generate_amazon_ledger(
    txn: NormalizedTransaction,
) -> tuple[LedgerDraft | None, list[ValidationError]]:
    """Amazonトランザクションの仕訳生成"""
    errors: list[ValidationError] = []
    bucket_name = txn.extra.get("bucket_name", "")

    if txn.amount_out == 0 and txn.amount_in == 0:
        errors.append(ValidationError(
            row_id=txn.row_id, level="warn",
            field="amount", message="金額が両方0です。仕訳をスキップします",
            raw_value="out=0, in=0",
        ))
        return None, errors

    # バケット別のデフォルト科目
    accounts = _AMAZON_BUCKET_ACCOUNTS.get(bucket_name)
    if accounts:
        debit_account, credit_account = accounts
    else:
        debit_account = "未分類"
        credit_account = "売掛金"
        if bucket_name != "unmapped":
            errors.append(ValidationError(
                row_id=txn.row_id, level="warn",
                field="debit_account",
                message=f"科目を推定できません (バケット: {bucket_name})。デフォルト科目を仮割当て",
                raw_value=bucket_name,
            ))

    amount = max(txn.amount_in, txn.amount_out)
    description = f"{bucket_name} ({txn.details})"
    if len(description) > 100:
        description = description[:100]

    tags = ["amazon"]
    if "手数料" in bucket_name:
        tags.append("fee")

    draft = LedgerDraft(
        date=txn.date,
        debit_account=debit_account,
        debit_amount=amount,
        credit_account=credit_account,
        credit_amount=amount,
        description=description,
        partner="Amazon.co.jp",
        source_row_id=txn.row_id,
        tags=tags,
    )
    return draft, errors


def generate(
    transactions: list[NormalizedTransaction],
) -> tuple[list[LedgerDraft], list[ValidationError]]:
    """有効な NormalizedTransaction から LedgerDraft を生成する"""
    drafts: list[LedgerDraft] = []
    all_errors: list[ValidationError] = []

    for txn in transactions:
        try:
            if txn.source_type == "bank":
                draft, errs = _generate_bank_ledger(txn)
            elif txn.source_type == "amazon":
                draft, errs = _generate_amazon_ledger(txn)
            else:
                # 将来: creditcard 等
                draft, errs = _generate_bank_ledger(txn)

            all_errors.extend(errs)
            if draft is not None:
                drafts.append(draft)

        except Exception as e:
            all_errors.append(ValidationError(
                row_id=txn.row_id, level="error",
                field="ledger_generation",
                message=f"仕訳生成に失敗しました: {e}",
                raw_value="",
            ))

    return drafts, all_errors
