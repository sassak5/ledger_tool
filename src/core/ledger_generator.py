"""仕訳候補生成 — NormalizedTransaction から LedgerDraft を生成する

設定は rules/ledger_mapping.yml から読み込む。
ハードコード定数は持たず、全ての科目名・キーワード・デフォルト値を
LedgerMappingConfig 経由で参照する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.core.models import (
    LedgerDraft,
    NormalizedTransaction,
    ValidationError,
)
from src.core.ruleset.loader import load_yaml

# NOTE: ここだけデータクラス置いたりyml読み込み走らせたり少々混在
# - 将来、何か増えるなら移転

# ---------------------------------------------------------------------------
# YAML 設定をパースして保持するデータクラス
# ---------------------------------------------------------------------------

@dataclass
class _KeywordRule:
    """摘要キーワード → 科目 or タグ の 1 ルール"""
    contains: list[str]
    debit_account: str = ""
    credit_account: str = ""
    tag: str = ""


@dataclass
class LedgerMappingConfig:
    """ledger_mapping.yml をパースした結果を保持する設定オブジェクト"""

    # 共通
    description_max_length: int = 100

    # --- bank ---
    bank_base_tags: list[str] = field(default_factory=lambda: ["bank"])
    bank_tag_keywords: list[_KeywordRule] = field(default_factory=list)

    # bank inflow
    bank_inflow_debit: str = "普通預金"
    bank_inflow_credit: str = "売上高"
    bank_inflow_overrides: list[_KeywordRule] = field(default_factory=list)

    # bank outflow
    bank_outflow_credit: str = "普通預金"
    bank_outflow_unknown_debit: str = "未分類"
    bank_outflow_keyword_accounts: list[_KeywordRule] = field(default_factory=list)

    # --- amazon ---
    amazon_default_partner: str = "Amazon.co.jp"
    amazon_base_tags: list[str] = field(default_factory=lambda: ["amazon"])
    amazon_tag_keywords: list[_KeywordRule] = field(default_factory=list)
    amazon_bucket_accounts: dict[str, tuple[str, str]] = field(default_factory=dict)
    amazon_unknown_debit: str = "未分類"
    amazon_unknown_credit: str = "売掛金"


def _parse_keyword_rules(raw_list: list[dict[str, Any]]) -> list[_KeywordRule]:
    """YAML のキーワードルールリストを _KeywordRule に変換"""
    rules: list[_KeywordRule] = []
    for item in raw_list:
        rules.append(_KeywordRule(
            contains=item.get("contains", []),
            debit_account=item.get("debit_account", ""),
            credit_account=item.get("credit_account", ""),
            tag=item.get("tag", ""),
        ))
    return rules


def load_mapping_config(yaml_path: str | Path) -> LedgerMappingConfig:
    """ledger_mapping.yml を読み込み LedgerMappingConfig を返す"""
    data = load_yaml(yaml_path)

    cfg = LedgerMappingConfig()

    # --- 共通 ---
    desc_cfg = data.get("description", {})
    cfg.description_max_length = desc_cfg.get("max_length", 100)

    # --- bank ---
    bank = data.get("bank", {})
    cfg.bank_base_tags = bank.get("base_tags", ["bank"])
    cfg.bank_tag_keywords = _parse_keyword_rules(bank.get("tag_keywords", []))

    inflow = bank.get("inflow", {})
    cfg.bank_inflow_debit = inflow.get("debit_account", "普通預金")
    cfg.bank_inflow_credit = inflow.get("credit_account", "売上高")
    cfg.bank_inflow_overrides = _parse_keyword_rules(inflow.get("overrides", []))

    outflow = bank.get("outflow", {})
    cfg.bank_outflow_credit = outflow.get("credit_account", "普通預金")
    cfg.bank_outflow_unknown_debit = outflow.get("unknown_debit_account", "未分類")
    cfg.bank_outflow_keyword_accounts = _parse_keyword_rules(
        outflow.get("keyword_accounts", [])
    )

    # --- amazon ---
    amazon = data.get("amazon", {})
    cfg.amazon_default_partner = amazon.get("default_partner", "Amazon.co.jp")
    cfg.amazon_base_tags = amazon.get("base_tags", ["amazon"])
    cfg.amazon_tag_keywords = _parse_keyword_rules(amazon.get("tag_keywords", []))
    cfg.amazon_unknown_debit = amazon.get("unknown_debit_account", "未分類")
    cfg.amazon_unknown_credit = amazon.get("unknown_credit_account", "売掛金")

    # bucket_accounts: { "商品代金": ["売掛金", "売上高"] } → dict[str, tuple[str,str]]
    raw_buckets = amazon.get("bucket_accounts", {})
    for bucket_name, pair in raw_buckets.items():
        if isinstance(pair, list) and len(pair) == 2:
            cfg.amazon_bucket_accounts[bucket_name] = (pair[0], pair[1])

    return cfg


# ---------------------------------------------------------------------------
# 科目推定ヘルパー
# ---------------------------------------------------------------------------

def _guess_expense_account(
    summary: str, details: str, rules: list[_KeywordRule],
) -> str | None:
    """摘要テキストからキーワードマッチで経費科目を推定"""
    text = f"{summary} {details}"
    for rule in rules:
        for keyword in rule.contains:
            if keyword in text:
                return rule.debit_account
    return None


def _match_inflow_override(
    summary: str, details: str, overrides: list[_KeywordRule],
) -> str | None:
    """入金例外ルール（ATM入金等）にマッチするか判定"""
    text = f"{summary} {details}"
    for rule in overrides:
        for keyword in rule.contains:
            if keyword in text:
                return rule.credit_account
    return None


def _collect_tags(
    text: str,
    base_tags: list[str],
    tag_rules: list[_KeywordRule],
) -> list[str]:
    """base_tags をコピーし、キーワードマッチした tag を追加して返す"""
    tags = list(base_tags)
    for rule in tag_rules:
        for keyword in rule.contains:
            if keyword in text:
                if rule.tag and rule.tag not in tags:
                    tags.append(rule.tag)
                break  # この rule は 1 回マッチすれば十分
    return tags


# ---------------------------------------------------------------------------
# 仕訳生成
# ---------------------------------------------------------------------------

def _generate_bank_ledger(
    txn: NormalizedTransaction,
    cfg: LedgerMappingConfig,
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
    if len(description) > cfg.description_max_length:
        description = description[:cfg.description_max_length]

    tags = _collect_tags(description, cfg.bank_base_tags, cfg.bank_tag_keywords)

    if txn.amount_in > 0:
        # 入金: デフォルト
        debit_account = cfg.bank_inflow_debit
        credit_account = cfg.bank_inflow_credit
        amount = txn.amount_in

        # 入金例外（ATM等）
        override = _match_inflow_override(
            txn.summary, txn.details, cfg.bank_inflow_overrides,
        )
        if override:
            credit_account = override
    else:
        # 出金: キーワードマッチで経費科目推定
        guessed = _guess_expense_account(
            txn.summary, txn.details, cfg.bank_outflow_keyword_accounts,
        )
        if guessed:
            debit_account = guessed
        else:
            debit_account = cfg.bank_outflow_unknown_debit
            errors.append(ValidationError(
                row_id=txn.row_id, level="warn",
                field="debit_account",
                message="科目を推定できません。デフォルト科目 '未分類' を仮割当て",
                raw_value=description,
            ))
        credit_account = cfg.bank_outflow_credit
        amount = txn.amount_out

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
    cfg: LedgerMappingConfig,
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
    accounts = cfg.amazon_bucket_accounts.get(bucket_name)
    if accounts:
        debit_account, credit_account = accounts
    else:
        debit_account = cfg.amazon_unknown_debit
        credit_account = cfg.amazon_unknown_credit
        if bucket_name != "unmapped":
            errors.append(ValidationError(
                row_id=txn.row_id, level="warn",
                field="debit_account",
                message=f"科目を推定できません (バケット: {bucket_name})。デフォルト科目を仮割当て",
                raw_value=bucket_name,
            ))

    amount = max(txn.amount_in, txn.amount_out)
    description = f"{bucket_name} ({txn.details})"
    if len(description) > cfg.description_max_length:
        description = description[:cfg.description_max_length]

    tags = _collect_tags(bucket_name, cfg.amazon_base_tags, cfg.amazon_tag_keywords)

    draft = LedgerDraft(
        date=txn.date,
        debit_account=debit_account,
        debit_amount=amount,
        credit_account=credit_account,
        credit_amount=amount,
        description=description,
        partner=cfg.amazon_default_partner,
        source_row_id=txn.row_id,
        tags=tags,
    )
    return draft, errors


def generate(
    transactions: list[NormalizedTransaction],
    cfg: LedgerMappingConfig,
) -> tuple[list[LedgerDraft], list[ValidationError]]:
    """validator.pyで行検査した有効な NormalizedTransaction から LedgerDraft を生成する

    Args:
        transactions: 正規化済みトランザクション
        cfg: ledger_mapping.yml から読み込んだ設定
    """
    drafts: list[LedgerDraft] = []
    all_errors: list[ValidationError] = []

    for txn in transactions:
        try:
            if txn.source_type == "bank":
                draft, errs = _generate_bank_ledger(txn, cfg)
            elif txn.source_type == "amazon":
                draft, errs = _generate_amazon_ledger(txn, cfg)
            else:
                # 将来: creditcard 等
                draft, errs = _generate_bank_ledger(txn, cfg)

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
