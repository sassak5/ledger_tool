"""
ドキュメント最終更新日: 2026-02-14

**このモジュールの役割**
- “パーサの共通契約” を定義する抽象基底クラス（ABC）です
- 目的は「パイプライン側は具体的な実装（Amazon/銀行など）を知らずに、`parse` を呼べる」状態を作ることです

**@abstractmethod の意味（このモジュール内での効き方）**
- `@abstractmethod` により `parse` は “必ずサブクラスが実装すべきメソッド” になります
- その結果、`parse` を実装していないサブクラスはインスタンス化できず、実装漏れを早期に防げます

"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.models import RawRecord


class BaseParser(ABC):
    """全パーサが実装する共通インターフェース。

    pipeline / normalizer はこのインターフェースのみに依存する。
    """

    @abstractmethod # 関数実装漏れを “実行前に” 機械的に検出できる
    def parse(self, file_path: str, config: dict) -> list[RawRecord]:
        """ファイルをパースして RawRecord のリストを返す。

        Args:
            file_path: 入力ファイルのパス
            config: YAMLから読み込んだ設定辞書

        Returns:
            パース結果のリスト (型変換は normalizer が担当)
        """
        ...
