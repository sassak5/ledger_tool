"""
ルールセット読込 — rules/*.yml を読み込み、基本検証(型確認、キー確認)を行う
-   load_yaml(path)
    指定された YAML を yaml.safe_load で読み込み、ルートが dict であることを確認して返します。
    
-   validate_bank_format(config, path)
    銀行用ルール（source_kind == "bank_statement"）の必須キーが揃っているかを検証します。
    
-   validate_amazon_format(config, path)
    Amazon用ルール（source == "amazon_settlement_report"）の必須キー（_AMAZON_REQUIRED_KEYS）と、summary_buckets が dict であることを確認します。

-   load_all_rules(rules_dir): メイン関数
    rules_dir がディレクトリであることを確認し、配下の *.yml をファイル名順に読みます。
    各 YAML について load_yaml() → config["_config_path"] = str(yml_path) を付与（デバッグ用メタ情報）。
    その後、source_kind / source を見て銀行用・Amazon用の検証関数へ振り分けます（将来拡張のコメントもあり）。
    最終的に 検証済み config の list を返します。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.core.models import RuleSetValidationError


# 銀行フォーマットYAMLの必須キー
_BANK_REQUIRED_KEYS = {"version", "format_id", "source_kind", "header_aliases"}

# AmazonサマリYAMLの必須キー
_AMAZON_REQUIRED_KEYS = {"version", "source", "key", "summary_buckets"}


def load_yaml(path: str | Path) -> dict[str, Any]:
    """単一のYAMLファイルを読み込んで辞書で返す"""
    path = Path(path)
    if not path.exists():
        raise RuleSetValidationError(f"YAMLファイルが見つかりません: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise RuleSetValidationError(f"YAMLのルートが辞書ではありません: {path}")
    return data


def validate_bank_format(config: dict[str, Any], path: str) -> None:
    """銀行フォーマットYAMLの基本検証"""
    missing = _BANK_REQUIRED_KEYS - config.keys()
    if missing:
        raise RuleSetValidationError(
            f"必須キーが不足しています ({path}): {missing}"
        )
    # header_aliases が辞書であること
    ha = config.get("header_aliases")
    if not isinstance(ha, dict):
        raise RuleSetValidationError(
            f"header_aliases が辞書ではありません ({path})"
        )
    # エイリアス値がリストであること
    for key, aliases in ha.items():
        if not isinstance(aliases, list):
            raise RuleSetValidationError(
                f"header_aliases['{key}'] がリストではありません ({path})"
            )


def validate_amazon_format(config: dict[str, Any], path: str) -> None:
    """AmazonサマリYAMLの基本検証"""
    missing = _AMAZON_REQUIRED_KEYS - config.keys()
    if missing:
        raise RuleSetValidationError(
            f"必須キーが不足しています ({path}): {missing}"
        )
    buckets = config.get("summary_buckets")
    if not isinstance(buckets, dict):
        raise RuleSetValidationError(
            f"summary_buckets が辞書ではありません ({path})"
        )


def load_all_rules(rules_dir: str | Path) -> list[dict[str, Any]]:
    """rules/ 配下の全YAMLを読み込み、検証済みリストで返す。

    ドキュメント最終確認日: 2026-02-09

    工程:
        1. rules_dir を Path 化する
        2. rules_dir の存在/ディレクトリ性を検証する（NGなら例外）
        3. rules_dir 配下の *.yml を列挙し、ファイル名順にソートする
        4. 各YAMLについて load_yaml() で読み込む（ルートが dict であることを検証）
        5. 読み込んだ設定にメタ情報として _config_path を付与する(目的はデバック用)
        6. source_kind / source に応じて必須キー及び形式を検証する（NGなら例外）
        7. 検証済みの設定辞書をリストに追加し、最後にそのリストを返す
    """
    rules_dir = Path(rules_dir)
    if not rules_dir.is_dir():
        raise RuleSetValidationError(f"rulesディレクトリが見つかりません: {rules_dir}")

    configs: list[dict[str, Any]] = []
    for yml_path in sorted(rules_dir.glob("*.yml")):
        config = load_yaml(yml_path)
        config["_config_path"] = str(yml_path)

        # ソース種別で検証を分岐
        if config.get("source_kind") == "bank_statement":
            validate_bank_format(config, str(yml_path))
        elif config.get("source") == "amazon_settlement_report":
            validate_amazon_format(config, str(yml_path))
        # 将来: credit_card_statement 等を追加

        configs.append(config)

    return configs
