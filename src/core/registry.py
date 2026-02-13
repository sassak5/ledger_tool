"""パーサレジストリ — source_kind をキーにパーサクラスを登録・解決する"""

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
