"""
ドキュメント最終更新: 2026-02-15

このモジュールは、パイプライン全体の中で「検出された source_kind に対応するパーサを選ぶ」ための
解決機構（レジストリ）を提供する。

システム全体での立ち位置（上流→下流）:
    detector → registry(+parsers) → normalizer → validator → ledger_generator → exporter

- detector は入力ファイルから source_kind を推定する（例: bank_statement / amazon_settlement_report）。
- registry は source_kind をキーに、対応するパーサ実装（BaseParser派生）を取得して返す。
- 実際のパース処理（RawRecord生成）は、取得したパーサの parse() が担当する。

GUI操作から見た挙動:
    GUIの「変換（帳簿作成）」実行 → `src/core/pipeline.py` が処理を統括し、
    `src.core.parsers.register_parsers()` を呼ぶことで既知パーサが registry に登録される。
    その後、検出結果の source_kind に対して `registry.get(source_kind)` でパーサを解決し、
    ファイルを RawRecord 群へ変換して正規化へ渡す。

補足:
    未登録の source_kind を解決しようとすると UnknownSourceKindError を送出する。
"""

from __future__ import annotations

from typing import Type

from src.core.base_parser import BaseParser
from src.core.models import UnknownSourceKindError


class ParserRegistry:
    """パーサの登録と取得を管理するレジストリ"""

    def __init__(self) -> None:
        self._parsers: dict[str, Type[BaseParser]] = {}

    def register(self, source_kind: str, parser_cls: Type[BaseParser]) -> None:
        self._parsers[source_kind] = parser_cls

    def get(self, source_kind: str) -> BaseParser:
        cls = self._parsers.get(source_kind)
        if cls is None:
            raise UnknownSourceKindError(
                f"未登録の source_kind: '{source_kind}'"
            )
        return cls()


# グローバルレジストリ (起動時に各パーサが登録する)
registry = ParserRegistry()
