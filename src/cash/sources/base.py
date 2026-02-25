"""データソース共通インターフェース (Protocol)。

全てのデータソース（手入力・SP-API・CSV取込等）はこの Protocol を満たすように実装する。
Protocol なので明示的な継承は不要 — 構造的部分型として型チェックされる。
"""

from __future__ import annotations

from typing import Protocol

from src.cash.models import CashEntry, CashValidationError


class EntrySource(Protocol):
    """全てのデータソースが満たすべきインターフェース。

    - source_kind: ソース識別子としてCashEntry.sourceフィールドに記録する。
    - fetch: 指定期間のエントリを取得する。
    - validate_entry: エントリのバリデーションを行い、エラー/警告リストを返す。
    """

    @property
    def source_kind(self) -> str:
        """ソース識別子。"manual" / "sp_api" / "csv_import" / "ledger_ref" """
        ...

    def fetch(self, date_from: str, date_to: str) -> list[CashEntry]:
        """指定期間のエントリを取得する。

        Args:
            date_from: 開始日 (YYYY-MM-DD)
            date_to: 終了日 (YYYY-MM-DD)

        Returns:
            CashEntry のリスト
        """
        ...

    def validate_entry(self, entry: CashEntry) -> list[CashValidationError]:
        """エントリのバリデーション。

        Args:
            entry: 検証対象の CashEntry

        Returns:
            エラー/警告のリスト。空リスト = OK
        """
        ...
