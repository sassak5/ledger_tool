"""
ドキュメント最終確認日: 2026-02-12

データモデル定義 + 例外クラス階層の専用モジュール

データモデル（1行概要）:
- RawRecord: パーサが抽出した「正規化前」の中間レコード。
- DetectionResult: フォーマット検出の結果（source_kind / format_id / encoding / config_path）。
- NormalizedTransaction: 全モジュール共通の「正規化済み」取引データ。
- LedgerDraft: 取引から生成された仕訳候補（借方/貸方/金額など）。
- ValidationError: 処理中に発生したエラー/警告の集約表現。
- SourceFileInfo: 入力ファイル単位の件数・エラー/警告件数などの情報。
- ProcessingSummary: パイプライン実行全体のサマリ（期間・件数・合計など）。
- PipelineResult: GUI表示/出力用にまとめたパイプラインの最終結果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# データモデル
# ---------------------------------------------------------------------------

@dataclass
class RawRecord:
    """パーサが返す正規化前の中間データ。

    - source_kind: 入力の種別（どのパーサ/ルール系か）の識別に使う。
    - format_id: フォーマットID（どのテンプレ/定義に合致したか）の識別に使う。
    - row_number: 元ファイル上の行番号（エラー表示や追跡）に使う。
    - fields: パース済みフィールド（主に文字列のまま）を正規化処理へ渡す。
    - raw_line: 元行データを保持し、デバッグ/エラー出力の根拠として使う。
    """
    source_kind: str            # "bank_statement" / "amazon_settlement_report"
    format_id: str              # "mufj_table_v1" etc.
    row_number: int             # 元ファイル上の行番号 (1始まり)
    fields: dict[str, Any]      # パース済みフィールド (値は文字列のまま)
    raw_line: dict[str, str]    # 元行データそのまま


@dataclass
class DetectionResult:
    """detector が返すフォーマット検出結果。

    - format_id: 合致したフォーマットID（ログ/集計や追跡）に使う。
    - source_kind: ソース種別（どのパーサを使うか）を決めるキーに使う。
    - encoding: 入力ファイルを読む文字コード指定としてパーサへ渡す。
    - config_path: 適用するルールYAMLのパス（設定ロードと再現性）に使う。
    """
    format_id: str      # "mufj_table_v1" etc.
    source_kind: str    # "bank_statement" / "amazon_settlement_report"
    encoding: str       # "utf-8" / "cp932" etc.
    config_path: str    # マッチしたYAMLファイルのパス


@dataclass
class NormalizedTransaction:
    """正規化済みトランザクション（全モジュール共通）。

    - source_type: 大分類（bank/amazon 等）で集計や処理分岐に使う。
    - source_name: 具体的なソース名（mufj/aichi 等）で識別・集計に使う。
    - row_id: 取引1件の一意識別子としてエラー紐付けや参照に使う。
    - date: 取引日（YYYY-MM-DD）として期間集計や仕訳日付に使う。
    - summary: 短い摘要として一覧表示や仕訳摘要の基礎に使う。
    - details: 詳細摘要として補足情報や検索性向上に使う。
    - amount_out: 出金額（0以上）として支出合計や仕訳金額に使う。
    - amount_in: 入金額（0以上）として収入合計や仕訳金額に使う。
    - balance: 残高（あれば）として整合チェックや参考表示に使う。
    - memo: 人手メモ/補足としてGUIや出力にそのまま残す。
    - extra: ソース固有の追加情報（将来拡張/デバッグ）を保持する。
    - raw: 元データ断片（根拠）を保持し、追跡可能性を上げる。
    """
    source_type: str                    # "bank" / "amazon" / "creditcard"
    source_name: str                    # "mufj" / "aichi" / "amazon_settlement"
    row_id: str                         # "{source_name}_{行番号}"
    date: str                           # "YYYY-MM-DD"
    summary: str                        # 摘要 (短)
    details: str                        # 摘要内容 (長)
    amount_out: int                     # 出金 (0以上)
    amount_in: int                      # 入金 (0以上)
    balance: int | None                 # 差引残高 (なければ None)
    memo: str                           # メモ
    extra: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class LedgerDraft:
    """仕訳候補。

    - date: 仕訳日付として会計ソフト出力に使う。
    - debit_account: 借方勘定科目として仕訳の科目欄に使う。
    - debit_amount: 借方金額として仕訳金額に使う。
    - credit_account: 貸方勘定科目として仕訳の科目欄に使う。
    - credit_amount: 貸方金額として仕訳金額に使う。
    - description: 摘要として仕訳説明に使う。
    - partner: 取引先として補助情報/摘要補完に使う。
    - source_row_id: 元取引（NormalizedTransaction.row_id 等）への参照として追跡に使う。
    - tags: 任意タグ（分類/将来拡張）として出力やフィルタに使う。
    """
    date: str               # "YYYY-MM-DD"
    debit_account: str      # 借方勘定科目
    debit_amount: int       # 借方金額
    credit_account: str     # 貸方勘定科目
    credit_amount: int      # 貸方金額
    description: str        # 摘要
    partner: str            # 取引先
    source_row_id: str      # 元データ参照
    tags: list[str] = field(default_factory=list)


@dataclass
class ValidationError:
    """バリデーションエラー/警告（最終的にGUIやcsvにて出力）。

    - row_id: 問題の紐付け先（取引IDやファイルパス等）として追跡に使う。
    - level: 重大度（error/warn）として除外判定や表示色分けに使う。
    - field: 問題が起きた項目名として修正箇所の特定に使う。
    - message: 人間向けメッセージとしてGUI/レポートに出す。
    - raw_value: 元値（根拠）としてデバッグと再現性確保に使う。
    """
    row_id: str         # 問題行の識別子
    level: str          # "error" / "warn"
    field: str          # 問題フィールド名
    message: str        # 人間向けメッセージ
    raw_value: str = "" # 問題の元値


@dataclass
class SourceFileInfo:
    """入力ファイルごとの情報（サマリ/GUI表示用）。

    - path: 入力ファイルのパスとして表示・追跡に使う。
    - format_id: 検出されたフォーマットIDとして集計や追跡に使う。
    - source_kind: ソース種別として集計や処理系の識別に使う。
    - row_count: そのファイルから読めた行数として処理量の把握に使う。
    - error_count: error 件数として品質状況の把握に使う。
    - warn_count: warn 件数として注意喚起に使う。
    """
    path: str
    format_id: str
    source_kind: str
    row_count: int
    error_count: int
    warn_count: int


@dataclass
class ProcessingSummary:
    """パイプライン実行サマリ（実行結果の集計）。

    - period_start: 対象期間の開始日として表示・出力に使う。
    - period_end: 対象期間の終了日として表示・出力に使う。
    - total_count: 正規化/検証を通過した件数として処理結果の指標に使う。
    - total_in: 入金合計として集計表示に使う。
    - total_out: 出金合計として集計表示に使う。
    - ledger_count: 生成した仕訳候補件数として結果指標に使う。
    - error_count: error 総数として失敗状況の把握に使う。
    - warn_count: warn 総数として注意喚起に使う。
    - source_files: ファイル別集計として入力ごとの状況表示に使う。
    - run_at: 実行日時として出力フォルダ/ログの説明に使う。
    """
    period_start: str               # "YYYY-MM-DD"
    period_end: str                 # "YYYY-MM-DD"
    total_count: int                # 正規化成功件数
    total_in: int                   # 入金合計
    total_out: int                  # 出金合計
    ledger_count: int               # 仕訳候補件数
    error_count: int
    warn_count: int
    source_files: list[SourceFileInfo] = field(default_factory=list)
    run_at: str = ""                # "YYYY-MM-DD HH:MM:SS"


@dataclass
class PipelineResult:
    """パイプライン実行の全結果（GUI表示/出力用）。

    - summary: 全体サマリとしてGUIヘッダやレポートに使う。
    - drafts: 仕訳候補一覧として出力（smart_import 等）に使う。
    - errors: エラー/警告一覧としてレポート出力やGUI表示に使う。
    - transactions: 正規化取引一覧として中間成果物出力や後段処理に使う。
    """
    summary: ProcessingSummary
    drafts: list[LedgerDraft] = field(default_factory=list)
    errors: list[ValidationError] = field(default_factory=list)
    transactions: list[NormalizedTransaction] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 例外クラス階層
# ---------------------------------------------------------------------------

class TaxToolError(Exception):
    """基底例外"""


class DetectionError(TaxToolError):
    """フォーマット検出の基底"""


class EncodingDetectionError(DetectionError):
    """エンコーディング判定失敗"""


class FormatNotMatchedError(DetectionError):
    """テンプレート不一致"""


class ParseError(TaxToolError):
    """パースの基底(未使用)"""


class DateParseError(ParseError):
    """日付パース失敗(未使用)"""


class AmountParseError(ParseError):
    """金額パース失敗(未使用)"""


class NormalizationError(TaxToolError):
    """正規化変換失敗(未使用)"""


class UnknownSourceKindError(TaxToolError):
    """未登録の source_kind"""


class ExportError(TaxToolError):
    """出力失敗(未使用)"""


class RuleSetValidationError(TaxToolError):
    """YAMLスキーマ検証失敗"""
